"""Wake adapter: 3-clap listener in a background thread.

The desktop UI can later add the "Maya Maya Maya" loop; the headless server
only needs clap events on `/ws/events`. A listen window is bounded by
`POST /wake/listen` (max 300 s) and stops immediately on request.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any

from custom.config import load_settings
from custom.tools import voice, voice_stt

from app.services.voice_service import VoiceError


class WakeAdapter:
    """WakePort implementation (clap events + honest status + name detection)."""

    def __init__(self) -> None:
        settings = load_settings()
        wake_cfg = settings.get("wake")
        if not isinstance(wake_cfg, dict):
            wake_cfg = {}
        self._enabled = bool(wake_cfg.get("enabled", True))
        self._name_enabled = self._enabled and bool(voice_stt.available().get("en-in"))

        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._listening = False
        self._expires_at = 0.0
        self._events: deque[dict[str, Any]] = deque(maxlen=50)

        # Name-wake state
        self._name_stop_event = threading.Event()
        self._name_thread: threading.Thread | None = None

        # Listen seconds for name-wake loop (from voice settings)
        voice_cfg = settings.get("voice")
        if not isinstance(voice_cfg, dict):
            voice_cfg = {}
        stt = voice_cfg.get("stt")
        if not isinstance(stt, dict):
            stt = {}
        self._listen_seconds = max(1, min(15, int(stt.get("listen_seconds", 6))))

    # -- port ---------------------------------------------------------

    def status(self) -> dict[str, Any]:
        with self._lock:
            listening = self._listening and time.time() < self._expires_at
        return {
            "listening": bool(listening),
            "clap": self._enabled,
            "name": self._name_enabled,
        }

    def listen(self, seconds: int) -> float:
        seconds = max(1, min(300, int(seconds)))
        with self._lock:
            self._stop_listener_locked()
            stop = threading.Event()
            self._stop_event = stop
            self._listening = True
            self._expires_at = time.time() + seconds
            thread = threading.Thread(
                target=self._run,
                args=(seconds, stop),
                name="maya-wake",
                daemon=True,
            )
            self._thread = thread
            thread.start()
            return self._expires_at

    def stop(self) -> None:
        with self._lock:
            self._stop_listener_locked()

    def drain_events(self) -> list[dict[str, Any]]:
        with self._lock:
            events = list(self._events)
            self._events.clear()
        return events

    # -- internals ----------------------------------------------------

    def _stop_listener_locked(self) -> None:
        self._stop_event.set()
        self._listening = False
        thread = self._thread
        self._thread = None
        if thread is not None and thread.is_alive():
            thread.join(timeout=3.0)

    def _run(self, seconds: int, stop: threading.Event) -> None:
        try:
            from custom.tools import voice_clap
        except Exception as exc:  # noqa: BLE001 - optional dependency
            self._push({"type": "wake_error", "reason": f"clap listener unavailable: {exc}"})
            self._mark_stopped(stop)
            return

        deadline = time.monotonic() + seconds

        def _on_trigger() -> None:
            self._push({"type": "wake", "source": "clap", "ts": int(time.time())})

        while not stop.is_set() and time.monotonic() < deadline:
            remaining = int(deadline - time.monotonic())
            if remaining <= 0:
                break
            result = voice_clap.listen(
                once=False,
                max_seconds=float(remaining),
                should_stop=stop.is_set,
                on_trigger=_on_trigger,
            )
            reason = str(result.get("reason") or "")
            if "mic open failed" in reason or "listener error" in reason:
                self._push({"type": "wake_error", "reason": reason})
                break

        self._mark_stopped(stop)

    def _mark_stopped(self, stop: threading.Event) -> None:
        with self._lock:
            if self._stop_event is stop:
                self._listening = False

    def _name_wake_loop(self) -> None:
        """Continuously listen for the wake phrase 'Maya Maya Maya'."""
        try:
            while not self._name_stop_event.is_set():
                try:
                    text, error = voice_stt.listen(seconds=self._listen_seconds, lang="en-in")
                    if error:
                        continue
                    text_lower = (text or "").lower().strip()
                    if voice.check_wake(text_lower):
                        self._push({"type": "name_wake", "source": "phrase", "ts": int(time.time())})
                        try:
                            reply = voice.wake_reply()
                            self.speak(reply)
                        except VoiceError:
                            pass
                        time.sleep(8.0)
                        continue
                except VoiceError as ve:
                    self._push({"type": "wake_error", "reason": f"name: {ve}"})
                    time.sleep(1.0)
                except Exception as exc:  # noqa: BLE001 - unexpected, keep alive
                    self._push({"type": "wake_error", "reason": f"name loop error: {exc}"})
                    time.sleep(1.0)
        finally:
            self._name_stop_event.clear()

    def start_name_wake(self) -> None:
        """Begin the background loop that checks for the wake phrase."""
        with self._lock:
            if self._name_thread is not None and self._name_thread.is_alive():
                return
            self._name_stop_event.clear()
            self._name_thread = threading.Thread(
                target=self._name_wake_loop,
                name="maya-name-wake",
                daemon=True,
            )
            self._name_thread.start()

    def stop_name_wake(self) -> None:
        """Stop the name-wake loop."""
        with self._lock:
            if self._name_thread is not None and self._name_thread.is_alive():
                self._name_stop_event.set()
                self._name_thread.join(timeout=5.0)
                self._name_thread = None

    def _push(self, event: dict[str, Any]) -> None:
        self._events.append(event)
