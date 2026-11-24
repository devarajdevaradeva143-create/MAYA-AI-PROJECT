"""Qt workers: chat streaming, engine health, monitor snapshots, server start.

Every worker here runs off the UI thread and talks back through signals only
(no widget / Qt call is made from the worker thread).
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThread, Signal

from app.services.chat_service import ChatService


class ChatStreamWorker(QThread):
    """Runs `ChatService.stream` off the UI thread; one worker at a time."""

    chunk = Signal(str)
    completed = Signal(str)
    cancelled = Signal()
    failed = Signal(str, str)  # error type, message

    def __init__(self, chat: ChatService, text: str, parent: Any = None) -> None:
        super().__init__(parent)
        self._chat = chat
        self._text = text

    def run(self) -> None:
        parts: list[str] = []
        try:
            for piece in self._chat.stream(self._text):
                parts.append(piece)
                self.chunk.emit(piece)
        except Exception as exc:  # noqa: BLE001 - surfaced to the page
            self.failed.emit(type(exc).__name__, str(exc))
            return

        if self._chat.was_cancelled:
            self.cancelled.emit()
        else:
            self.completed.emit("".join(parts).strip())

    def stop(self) -> None:
        self._chat.cancel()


class HealthWorker(QThread):
    """Checks the engine without freezing the chat page."""

    result = Signal(bool, str, str)  # ok, detail, model

    def __init__(self, engine: Any, parent: Any = None) -> None:
        super().__init__(parent)
        self._engine = engine

    def run(self) -> None:
        try:
            health = self._engine.health()
        except Exception as exc:  # noqa: BLE001 - health must never crash
            self.result.emit(False, str(exc), "")
            return

        if not isinstance(health, dict):
            self.result.emit(False, "Engine returned an unexpected reply", "")
            return

        ok = bool(health.get("ok", health.get("status") in {"ok", "healthy", "ready"}))
        models = [str(item) for item in health.get("models") or [] if str(item)]
        model = models[0] if models else str(getattr(self._engine, "model", "") or "")
        detail = "Engine ready" if ok else str(health.get("error") or "Engine unreachable")
        self.result.emit(ok, detail, model)


class MonitorSnapshotSignals(QObject):
    """Signals for `MonitorSnapshotWorker` (a QRunnable is not a QObject)."""

    result = Signal(object)  # dict snapshot (payload type: dict[str, Any])
    failed = Signal(str)


class MonitorSnapshotWorker(QRunnable):
    """Runs `MonitorAdapter.snapshot()` in the Qt thread pool.

    The snapshot touches WMI + psutil and can take close to a second, so the
    monitoring page schedules it here instead of freezing the UI thread.
    """

    def __init__(self, monitor: Any) -> None:
        super().__init__()
        self.setAutoDelete(True)
        self.signals = MonitorSnapshotSignals()
        self._monitor = monitor

    def run(self) -> None:
        try:
            snapshot = self._monitor.snapshot()
        except Exception as exc:  # noqa: BLE001 - surfaced to the page
            self.signals.failed.emit(f"{type(exc).__name__}: {exc}")
            return

        if not isinstance(snapshot, dict):
            self.signals.failed.emit("Monitor returned an unexpected snapshot")
            return

        self.signals.result.emit(snapshot)


class ServerStartWorker(QThread):
    """Boots the phone server off the UI thread (uvicorn start takes 1-2 s)."""

    finished_ok = Signal(str)  # "host:port" the server listens on
    failed = Signal(str)  # human-readable error

    def __init__(self, service: Any, parent: Any = None) -> None:
        super().__init__(parent)
        self._service = service

    def run(self) -> None:
        try:
            self._service.start()
        except Exception as exc:  # noqa: BLE001 - surfaced to the page
            detail = str(exc).strip()
            self.failed.emit(f"{type(exc).__name__}: {detail}" if detail else type(exc).__name__)
            return

        try:
            address = f"{self._service.host}:{self._service.bound_port or self._service.port}"
        except Exception:  # noqa: BLE001 - the start itself succeeded
            address = ""
        self.finished_ok.emit(address)
