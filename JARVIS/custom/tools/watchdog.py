"""Session watchdog — unattended-session protection for Maya.

Maya cannot silently identify a face (Windows Hello always needs a gesture),
so this watchdog implements the checks that are possible offline:

* **idle auto-lock** — lock the session after N minutes without keyboard or
  mouse input (Windows ``GetLastInputInfo``);
* **session expiry** — lock N minutes after the last successful unlock, so a
  session cannot stay open forever;
* **voice re-check** — optionally ask for the enrolled spoken phrase every N
  minutes and lock on failure.

Everything is local. The watchdog never starts itself: the user runs
``maya security watchdog``. It only locks (a protective action); unlocking
still needs the normal PIN / face / voice factors.
"""

from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from ..config import load_settings
from . import biometrics, voice_stt
from .security import SecurityManager, security as default_security


DEFAULT_IDLE_MINUTES = 5
DEFAULT_CHECK_SECONDS = 15
DEFAULT_VOICE_SECONDS = 5
CONFIG_KEYS = (
    "idle_lock_minutes",
    "max_session_minutes",
    "voice_check_minutes",
    "check_seconds",
    "voice_seconds",
)


# ── Configuration ──────────────────────────────────────────────────────────

def _number(value: Any, default: float, minimum: float = 0.0) -> float:
    """Return a finite float >= ``minimum``, or ``default``."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number != number or number in (float("inf"), float("-inf")):
        return default
    return max(minimum, number)


def watchdog_config(overrides: Optional[Dict[str, Any]] = None) -> Dict[str, float]:
    """Read ``security.watchdog`` from settings.yaml and apply CLI overrides."""
    raw: Dict[str, Any] = {}
    try:
        security_cfg = load_settings().get("security", {})
        if isinstance(security_cfg, dict):
            candidate = security_cfg.get("watchdog", {})
            if isinstance(candidate, dict):
                raw = candidate
    except Exception:  # pragma: no cover - config must never crash the watchdog
        raw = {}

    overrides = overrides or {}
    defaults = {
        "idle_lock_minutes": DEFAULT_IDLE_MINUTES,
        "max_session_minutes": 0.0,
        "voice_check_minutes": 0.0,
        "check_seconds": float(DEFAULT_CHECK_SECONDS),
        "voice_seconds": float(DEFAULT_VOICE_SECONDS),
    }

    cfg: Dict[str, float] = {}
    for key, default in defaults.items():
        value = overrides.get(key)
        if value is None:
            value = raw.get(key)
        cfg[key] = _number(value, default)

    cfg["check_seconds"] = max(1.0, cfg["check_seconds"])
    cfg["voice_seconds"] = max(2.0, min(30.0, cfg["voice_seconds"]))
    return cfg


# ── Idle detection ─────────────────────────────────────────────────────────

class _LastInputInfo(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]


def _windows_idle_seconds() -> Optional[float]:
    try:
        info = _LastInputInfo()
        info.cbSize = ctypes.sizeof(_LastInputInfo)
        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
            return None
        current = int(ctypes.windll.kernel32.GetTickCount64())
    except (AttributeError, OSError, ValueError):
        return None
    elapsed_ms = (current - int(info.dwTime)) & 0xFFFFFFFF
    return elapsed_ms / 1000.0


def idle_seconds() -> Optional[float]:
    """Seconds since the last keyboard/mouse input, or ``None`` if unknown."""
    if os.name == "nt":
        return _windows_idle_seconds()
    return None


# ── Voice re-check ─────────────────────────────────────────────────────────

def voice_ready() -> Dict[str, Any]:
    """Check that a voice challenge can actually run on this laptop."""
    status = biometrics.voice_status()
    if not status.get("enrolled"):
        return {
            "ok": False,
            "code": "not_enrolled",
            "error": "No voice password is set up.",
        }
    if biometrics.require_speaker() and not biometrics.speaker_available():
        return {
            "ok": False,
            "code": "speaker_missing",
            "error": "The vosk-spk speaker model is missing.",
        }
    return {"ok": True, "code": "ready", "error": None}


def voice_challenge(seconds: int | float = DEFAULT_VOICE_SECONDS) -> Dict[str, Any]:
    """Record one short sample and verify phrase + voiceprint. Deletes audio."""
    wav, peak = voice_stt.record(int(seconds))
    try:
        if peak < voice_stt.SILENCE_PEAK:
            return {"ok": False, "code": "no_signal", "error": "No microphone signal."}
        transcript = biometrics.transcribe_wav(wav)
        try:
            vector = biometrics.speaker_vector(wav)
        except RuntimeError:
            vector = None
    finally:
        Path(wav).unlink(missing_ok=True)
    return biometrics.voice_verify(transcript, vector)


# ── Watchdog ───────────────────────────────────────────────────────────────

def _fmt_minutes(minutes: float) -> str:
    return f"{minutes:g}"


class SessionWatchdog:
    """Evaluate idle/session/voice rules and lock when one is violated."""

    def __init__(
        self,
        manager: Optional[SecurityManager] = None,
        cfg: Optional[Dict[str, Any]] = None,
        idle_provider: Optional[Callable[[], Optional[float]]] = None,
        voice_provider: Optional[Callable[[float], Dict[str, Any]]] = None,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        self.manager = manager or default_security
        self.cfg = cfg if cfg is not None else watchdog_config()
        self._idle = idle_provider or idle_seconds
        self._voice = voice_provider or voice_challenge
        self._clock = clock or time.time
        self._last_voice: Optional[float] = None
        self._session_marker: Optional[float] = None

    # -- helpers ------------------------------------------------------
    def _safe_idle(self) -> Optional[float]:
        try:
            return self._idle()
        except Exception:  # pragma: no cover - platform probe must not crash
            return None

    def idle_available(self) -> bool:
        """False when idle locking is requested but this desktop cannot report it."""
        if float(self.cfg["idle_lock_minutes"]) <= 0:
            return True
        return self._safe_idle() is not None

    def _lock(self, reason: str, message: str) -> Dict[str, Any]:
        self.manager.lock()
        self.manager.record_unauthorized(f"Watchdog: {message}")
        return {"action": "locked", "reason": reason, "message": message}

    # -- one evaluation ----------------------------------------------
    def tick(self) -> Dict[str, Any]:
        self.manager.reload()
        if not self.manager.is_locked():
            return {
                "action": "idle",
                "reason": "no_pin",
                "message": "No PIN set. Use 'maya security set-pin <pin>' first.",
            }
        if self.manager.is_session_locked():
            return {
                "action": "idle",
                "reason": "already_locked",
                "message": "Maya is already locked.",
            }

        now = self._clock()
        status = self.manager.status()
        last_unlock = status.get("last_unlock") or {}
        unlocked_at = float(last_unlock.get("time", 0) or 0)

        # A fresh unlock resets the voice-challenge timer.
        if unlocked_at != self._session_marker:
            self._session_marker = unlocked_at
            self._last_voice = now

        idle: Optional[float] = None
        idle_limit = float(self.cfg["idle_lock_minutes"])
        if idle_limit > 0:
            idle = self._safe_idle()
            if idle is not None and idle >= idle_limit * 60:
                return self._lock(
                    "idle",
                    f"locked after {_fmt_minutes(idle_limit)} min without input.",
                )

        session_limit = float(self.cfg["max_session_minutes"])
        if session_limit > 0 and unlocked_at:
            age = now - unlocked_at
            if age >= session_limit * 60:
                return self._lock(
                    "session",
                    f"session expired after {_fmt_minutes(session_limit)} min. "
                    "Unlock again to continue.",
                )

        voice_limit = float(self.cfg["voice_check_minutes"])
        if voice_limit > 0:
            due = self._last_voice is None or (now - self._last_voice) >= voice_limit * 60
            if due:
                ready = voice_ready()
                self._last_voice = now
                if not ready["ok"]:
                    return {
                        "action": "skipped",
                        "reason": "voice_unavailable",
                        "error": ready.get("error"),
                        "idle": idle,
                    }
                try:
                    result = self._voice(self.cfg["voice_seconds"])
                except Exception as exc:  # fail closed: the check was requested
                    return self._lock("voice", f"voice re-check failed ({exc}).")
                if not result.get("ok"):
                    return self._lock(
                        "voice",
                        f"voice re-check failed: {result.get('error') or 'mismatch'}.",
                    )
                return {
                    "action": "voice_ok",
                    "reason": "voice_verified",
                    "message": "Voice re-check passed.",
                    "idle": idle,
                }

        return {"action": "ok", "reason": None, "message": None, "idle": idle}

    # -- summary ------------------------------------------------------
    def summary(self) -> str:
        cfg = self.cfg
        idle = (
            f"idle lock {_fmt_minutes(cfg['idle_lock_minutes'])} min"
            if cfg["idle_lock_minutes"] > 0
            else "idle lock off"
        )
        session = (
            f"session {_fmt_minutes(cfg['max_session_minutes'])} min"
            if cfg["max_session_minutes"] > 0
            else "session off"
        )
        voice = (
            f"voice every {_fmt_minutes(cfg['voice_check_minutes'])} min"
            if cfg["voice_check_minutes"] > 0
            else "voice off"
        )
        return f"{idle} | {session} | {voice} | every {_fmt_minutes(cfg['check_seconds'])}s"
