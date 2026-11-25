"""3-clap wake detection — fully offline.

Ported from the user's earlier PA project (``Laptop/Voice/clap.py``), where the
defaults were tuned against this laptop's microphone array.

Maya is command-only (AGENTS.md rule 7), so the detector **does not launch
anything by default** — it just reports the trigger. ``--launch`` opts in to
opening the chat window.

Settings (``MAYA AI/config/settings.yaml`` -> ``voice.clap``) override the
defaults below; environment variables also work for quick experiments.
"""

from __future__ import annotations

import array
import ctypes
import os
import time
from typing import Callable

from .voice_stt import (
    CALLBACK_NULL,
    WAVE_FORMAT_PCM,
    WAVEHDR,
    WAVEFORMATEX,
    _pick_device,
    _winmm,
)

# ── Tunables (mic-specific; change only after a calibrate run) ─────────────

RATE = 16000
FRAME_MS = 10
FRAME_SAMPLES = RATE * FRAME_MS // 1000      # 160
BUFFER_MS = 100
BUFFER_BYTES = (RATE * BUFFER_MS // 1000) * 2
N_BUFFERS = 6

DEFAULTS = {
    "threshold": 2800,
    "count": 3,
    "min_gap": 0.12,
    "max_gap": 0.9,
    "window": 3.0,
    "cooldown": 8.0,
}

_ENV = {
    "threshold": "MAYA_CLAP_THRESHOLD",
    "count": "MAYA_CLAP_COUNT",
    "min_gap": "MAYA_CLAP_MIN_GAP",
    "max_gap": "MAYA_CLAP_MAX_GAP",
    "window": "MAYA_CLAP_WINDOW",
    "cooldown": "MAYA_CLAP_COOLDOWN",
}


def _config() -> dict:
    """Resolve tunables: env var -> settings.yaml -> default."""
    values = dict(DEFAULTS)
    try:
        from ..config import load_settings

        settings = load_settings()
        cfg = (settings.get("voice", {}) or {}).get("clap", {}) or {}
        for key in values:
            if key in cfg:
                values[key] = cfg[key]
    except Exception:  # pragma: no cover - config must never break voice
        pass

    for key, env in _ENV.items():
        raw = os.environ.get(env)
        if raw:
            values[key] = raw
    return values


# ── Detection logic (pure, unit-testable) ──────────────────────────────────

class ClapDetector:
    """Peak-envelope clap counter. Feed 10 ms frame peaks; True = trigger."""

    def __init__(
        self,
        threshold: int | None = None,
        required: int | None = None,
        min_gap: float | None = None,
        max_gap: float | None = None,
        window: float | None = None,
        cooldown: float | None = None,
    ) -> None:
        cfg = _config()
        self.threshold = int(threshold if threshold is not None else cfg["threshold"])
        self.required = max(2, int(required if required is not None else cfg["count"]))
        self.min_gap = float(min_gap if min_gap is not None else cfg["min_gap"])
        self.max_gap = float(max_gap if max_gap is not None else cfg["max_gap"])
        self.window = float(window if window is not None else cfg["window"])
        self.cooldown = float(cooldown if cooldown is not None else cfg["cooldown"])
        self.above = False
        self.last_clap = 0.0
        self.last_trigger = 0.0
        self.claps: list[float] = []
        self.peak_seen = 0

    def feed(self, peak: int, now: float | None = None) -> bool:
        """Feed one frame peak. Returns True when the clap pattern completes."""
        now = time.monotonic() if now is None else now
        self.peak_seen = max(self.peak_seen, peak)

        if peak < self.threshold:
            self.above = False
            return False
        if self.above:  # still inside the same clap burst
            return False
        self.above = True

        if self.last_clap and now - self.last_clap < self.min_gap:
            return False
        if self.last_clap and now - self.last_clap > self.max_gap:
            self.claps.clear()  # rhythm too slow — restart the count
        self.last_clap = now
        self.claps.append(now)

        cutoff = now - self.window
        self.claps = [t for t in self.claps if t >= cutoff]
        if len(self.claps) >= self.required and (
            not self.last_trigger or now - self.last_trigger >= self.cooldown
        ):
            self.last_trigger = now
            self.claps.clear()
            return True
        return False


def peaks_from_bytes(data: bytes) -> list[int]:
    """Raw int16 PCM bytes -> per-10 ms peak values."""
    usable = len(data) - (len(data) % 2)
    samples = array.array("h")
    samples.frombytes(data[:usable])
    return [
        max(max(samples[i:i + FRAME_SAMPLES]), -min(samples[i:i + FRAME_SAMPLES]))
        for i in range(0, len(samples), FRAME_SAMPLES)
        if samples[i:i + FRAME_SAMPLES]
    ]


# ── Microphone stream ──────────────────────────────────────────────────────

def _open_stream():
    if _winmm is None:
        raise RuntimeError("clap detection is Windows-only right now")
    dev_id, dev_name = _pick_device()
    fmt = WAVEFORMATEX(WAVE_FORMAT_PCM, 1, RATE, RATE * 2, 2, 16, 0)
    hwi = ctypes.c_void_p()
    rc = _winmm.waveInOpen(ctypes.byref(hwi), dev_id, ctypes.byref(fmt), 0, 0, CALLBACK_NULL)
    if rc != 0:
        raise RuntimeError(f"waveInOpen failed (code {rc}) device={dev_name}")
    return hwi, dev_name


def _start_buffers(hwi):
    buffers, headers = [], []
    for _ in range(N_BUFFERS):
        buf = ctypes.create_string_buffer(BUFFER_BYTES)
        hdr = WAVEHDR(
            lpData=ctypes.cast(buf, ctypes.c_char_p),
            dwBufferLength=BUFFER_BYTES,
            dwBytesRecorded=0,
            dwUser=None,
            dwFlags=0,
            dwLoops=0,
            lpNext=None,
            reserved=None,
        )
        if _winmm.waveInPrepareHeader(hwi, ctypes.byref(hdr), ctypes.sizeof(hdr)) != 0:
            raise RuntimeError("waveInPrepareHeader failed")
        if _winmm.waveInAddBuffer(hwi, ctypes.byref(hdr), ctypes.sizeof(hdr)) != 0:
            raise RuntimeError("waveInAddBuffer failed")
        buffers.append(buf)
        headers.append(hdr)
    if _winmm.waveInStart(hwi) != 0:
        raise RuntimeError("waveInStart failed")
    return buffers, headers


def _stop_buffers(hwi, headers) -> None:
    try:
        _winmm.waveInStop(hwi)
        _winmm.waveInReset(hwi)
    finally:
        for hdr in headers:
            _winmm.waveInUnprepareHeader(hwi, ctypes.byref(hdr), ctypes.sizeof(hdr))
        _winmm.waveInClose(hwi)


# ── Public entry points ────────────────────────────────────────────────────

def listen(
    once: bool = False,
    verbose: bool = False,
    on_trigger: Callable[[], None] | None = None,
    max_seconds: float | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> dict:
    """Listen for the clap pattern.

    Returns ``{"triggers": n, "reason": str|None}``. Never launches anything —
    the caller decides what a trigger means.
    """
    try:
        hwi, dev_name = _open_stream()
    except Exception as exc:
        return {"triggers": 0, "reason": f"mic open failed: {exc}", "device": None}

    detector = ClapDetector()
    buffers, headers = _start_buffers(hwi)
    triggers = 0
    started = time.monotonic()
    reason = None
    try:
        while True:
            if should_stop is not None and should_stop():
                reason = "stopped"
                break
            if max_seconds and time.monotonic() - started >= max_seconds:
                reason = "time limit reached"
                break
            did_work = False
            for buf, hdr in zip(buffers, headers):
                if not (hdr.dwFlags & 0x00000001):  # WHDR_DONE
                    continue
                did_work = True
                for peak in peaks_from_bytes(buf.raw[: int(hdr.dwBytesRecorded)]):
                    if detector.feed(peak):
                        triggers += 1
                        if verbose:
                            print(f"clap pattern detected (#{triggers})")
                        if on_trigger:
                            on_trigger()
                        if once:
                            return {"triggers": triggers, "reason": None, "device": dev_name}
                hdr.dwFlags &= ~0x00000001
                hdr.dwBytesRecorded = 0
                if _winmm.waveInAddBuffer(hwi, ctypes.byref(hdr), ctypes.sizeof(hdr)) != 0:
                    raise RuntimeError("waveInAddBuffer re-add failed")
            if not did_work:
                time.sleep(0.01)
    except KeyboardInterrupt:
        reason = "stopped"
    except Exception as exc:
        reason = f"listener error: {exc}"
    finally:
        _stop_buffers(hwi, headers)
    return {"triggers": triggers, "reason": reason, "device": dev_name}


def simulate(claps: int = 3) -> bool:
    """Feed synthetic peaks — proves the pattern logic without a microphone."""
    detector = ClapDetector()
    fired = False
    now = 10.0
    for _ in range(claps):
        detector.feed(100, now=now)   # quiet frame ends the previous burst
        now += 0.05
        fired = detector.feed(5000, now=now) or fired
        now += 0.25
    return fired


def status() -> dict:
    """Honest clap-listener status."""
    cfg = _config()
    return {
        "windows_mic": _winmm is not None,
        "threshold": int(cfg["threshold"]),
        "count": int(cfg["count"]),
        "min_gap": float(cfg["min_gap"]),
        "max_gap": float(cfg["max_gap"]),
        "window": float(cfg["window"]),
        "cooldown": float(cfg["cooldown"]),
        "logic_ok": simulate(),
    }
