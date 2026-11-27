"""Windows-app facade for the local-first internet P2P session.

Every state-changing action passes through an explicit owner confirmation.
No cloud endpoint, no auto-connect, no autonomous command execution.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import threading
from pathlib import Path
from typing import Any, Callable

from custom.config import load_settings
from custom.tools.p2p import (
    P2PError,
    P2PSession,
    chunk_file,
)

logger = logging.getLogger("maya.p2p")

ConfirmCallback = Callable[[str, dict[str, Any]], bool]


def _settings() -> dict[str, Any]:
    try:
        return load_settings()
    except Exception:  # pragma: no cover - config must never break UI
        return {}


def _error(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, P2PError):
        return {"ok": False, "code": exc.code, "error": exc.message}
    return {"ok": False, "code": "p2p_error", "error": str(exc)}


class P2PService:
    """Owns one WebRTC session and a dedicated asyncio loop."""

    def __init__(self, session: P2PSession | None = None) -> None:
        self._session = session
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._confirm: ConfirmCallback | None = None
        self._incoming: list[dict[str, Any]] = []
        self._pending_lock = threading.Lock()
        self._pending_controls: list[dict[str, Any]] = []

    # -- loop ---------------------------------------------------------

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        if self._loop is None or self._loop.is_closed():
            self._loop = asyncio.new_event_loop()
            self._thread = threading.Thread(
                target=self._run_loop,
                args=(self._loop,),
                name="maya-p2p",
                daemon=True,
            )
            self._thread.start()
        return self._loop

    @staticmethod
    def _run_loop(loop: asyncio.AbstractEventLoop) -> None:
        asyncio.set_event_loop(loop)
        loop.run_forever()

    def _run(self, coro: Any, timeout: float = 30.0) -> Any:
        loop = self._ensure_loop()
        return asyncio.run_coroutine_threadsafe(coro, loop).result(timeout)

    def _session_obj(self) -> P2PSession:
        if self._session is None:
            self._session = P2PSession(settings=_settings())
        self._session.on_message = self._on_message
        return self._session

    def _allowed(self, action: str, details: dict[str, Any], confirm: ConfirmCallback | None) -> bool:
        callback = confirm or self._confirm
        if callback is None:
            logger.warning("P2P action %s refused: no confirmation callback", action)
            return False
        try:
            return bool(callback(action, details))
        except Exception as exc:  # noqa: BLE001 - refusal is always safe
            logger.warning("P2P confirmation failed: %s", exc)
            return False

    def _on_message(self, channel: str, payload: dict[str, Any]) -> None:
        self._incoming.append({"channel": channel, "payload": payload})
        if channel != "control":
            return
        if str(payload.get("action", "")) != "input":
            return
        with self._pending_lock:
            if len(self._pending_controls) >= 32:  # bounded queue; never auto-apply
                self._pending_controls.pop(0)
            self._pending_controls.append(
                {"action": "remote_input", "details": dict(payload)}
            )

    def pending_controls(self) -> list[dict[str, Any]]:
        """Queued remote control requests. Nothing here runs until approved."""
        with self._pending_lock:
            return [dict(item) for item in self._pending_controls]

    def approve_next_control(self, confirm: ConfirmCallback | None = None) -> dict[str, Any]:
        """Apply the oldest queued control request only after explicit approval."""
        with self._pending_lock:
            if not self._pending_controls:
                return {
                    "ok": False,
                    "code": "no_pending",
                    "error": "No pending control request",
                }
            item = dict(self._pending_controls[0])
        action = str(item.get("action") or "remote_input")
        details = dict(item.get("details") or {})
        if not self._allowed(action, details, confirm):
            return {"ok": False, "code": "denied", "error": "Owner did not allow control"}
        try:
            from app.services.remote_service import InputAdapter

            events = details.get("events")
            if isinstance(events, list):
                InputAdapter().apply(events)
            with self._pending_lock:
                if self._pending_controls:
                    self._pending_controls.pop(0)
            return {"ok": True, "action": action}
        except Exception as exc:  # noqa: BLE001
            return _error(exc)

    def deny_next_control(self) -> dict[str, Any]:
        with self._pending_lock:
            if not self._pending_controls:
                return {
                    "ok": False,
                    "code": "no_pending",
                    "error": "No pending control request",
                }
            self._pending_controls.pop(0)
        return {"ok": True}

    @staticmethod
    def _enabled() -> bool:
        cfg = _settings().get("p2p", {})
        return bool(isinstance(cfg, dict) and cfg.get("enabled", False))

    # -- public API ----------------------------------------------------

    def status(self) -> dict[str, Any]:
        cfg = _settings().get("p2p", {})
        if not isinstance(cfg, dict):
            cfg = {}
        turn = cfg.get("turn", {})
        relay = bool(isinstance(turn, dict) and turn.get("enabled") and turn.get("host"))
        state = self._session.state if self._session is not None else "new"
        return {
            "ok": True,
            "enabled": bool(cfg.get("enabled", False)),
            "state": state,
            "connected": state == "connected",
            "relay": relay,
            "device_id": self._session.identity.device_id if self._session is not None else "",
            "incoming": len(self._incoming),
            "pending_controls": len(self.pending_controls()),
        }

    def create_offer(self) -> dict[str, Any]:
        if not self._enabled():
            return {"ok": False, "code": "disabled", "error": "Internet P2P is disabled"}
        try:
            payload = self._run(self._session_obj().create_offer())
            return {"ok": True, "payload": payload}
        except Exception as exc:  # noqa: BLE001
            return _error(exc)

    def accept_offer(self, text: str) -> dict[str, Any]:
        if not self._enabled():
            return {"ok": False, "code": "disabled", "error": "Internet P2P is disabled"}
        try:
            answer = self._run(self._session_obj().accept_offer(str(text or "")))
            return {"ok": True, "payload": answer}
        except Exception as exc:  # noqa: BLE001
            return _error(exc)

    def accept_answer(self, text: str) -> dict[str, Any]:
        if not self._enabled():
            return {"ok": False, "code": "disabled", "error": "Internet P2P is disabled"}
        try:
            self._run(self._session_obj().accept_answer(str(text or "")))
            return {"ok": True, "state": self._session_obj().state}
        except Exception as exc:  # noqa: BLE001
            return _error(exc)

    def send_chat(self, text: str, confirm: ConfirmCallback | None = None) -> dict[str, Any]:
        details = {"text": str(text or "")[:200]}
        if not self._allowed("chat", details, confirm):
            return {"ok": False, "code": "denied", "error": "Owner did not allow chat"}
        try:
            self._session_obj().send("chat", {"text": str(text or "")})
            return {"ok": True}
        except Exception as exc:  # noqa: BLE001
            return _error(exc)

    def send_file(self, path: str | Path, confirm: ConfirmCallback | None = None) -> dict[str, Any]:
        source = Path(path).expanduser()
        details = {"name": source.name, "path": str(source)}
        if not self._allowed("file_send", details, confirm):
            return {"ok": False, "code": "denied", "error": "Owner did not allow file transfer"}
        try:
            chunks = list(chunk_file(source, source.name + str(source.stat().st_size)))
            for frame in chunks:
                self._session_obj().send("files", {"frame": base64.b64encode(frame).decode("ascii")})
            return {"ok": True, "chunks": len(chunks)}
        except Exception as exc:  # noqa: BLE001
            return _error(exc)

    def screen_frame(self, confirm: ConfirmCallback | None = None) -> dict[str, Any]:
        """Capture one JPEG frame and send it on the `screen` channel."""
        if not self._allowed("screen_view", {}, confirm):
            return {"ok": False, "code": "denied", "error": "Owner did not allow screen view"}
        try:
            from app.services.remote_service import ScreenAdapter

            frame = ScreenAdapter().capture()
            self._session_obj().send(
                "screen",
                {
                    "type": "frame",
                    "data_b64": base64.b64encode(frame.data).decode("ascii"),
                    "media_type": frame.media_type,
                    "width": frame.width,
                    "height": frame.height,
                },
            )
            return {"ok": True, "width": frame.width, "height": frame.height}
        except Exception as exc:  # noqa: BLE001
            return _error(exc)

    def close(self) -> dict[str, Any]:
        try:
            if self._session is not None:
                self._run(self._session.close(), timeout=10.0)
            if self._loop is not None and self._loop.is_running():
                self._loop.call_soon_threadsafe(self._loop.stop)
            self._loop = None
            self._thread = None
            return {"ok": True}
        except Exception as exc:  # noqa: BLE001
            return _error(exc)


_service: P2PService | None = None
_service_lock = threading.Lock()


def get_p2p_service() -> P2PService:
    """Process-wide singleton. Never auto-connects."""
    global _service
    with _service_lock:
        if _service is None:
            _service = P2PService()
        return _service


def reset_p2p_service() -> None:
    global _service
    with _service_lock:
        if _service is not None:
            try:
                _service.close()
            except Exception:  # noqa: BLE001
                pass
        _service = None


__all__ = ["P2PService", "get_p2p_service", "reset_p2p_service"]
