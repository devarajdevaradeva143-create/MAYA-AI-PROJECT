"""Single-instance lock: a second launch focuses the first window (plan 15.3).

Uses `QLocalServer` (named pipe on Windows). If the lock is taken, the new
process sends "show" and exits; the running app raises its window.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

DEFAULT_KEY = "maya-ai-desktop"
CONNECT_TIMEOUT_MS = 400

logger = logging.getLogger("maya.single_instance")


class SingleInstance(QObject):
    """Owns the local server; `activated` fires when another launch asks to show."""

    activated = Signal()

    def __init__(self, key: str = DEFAULT_KEY, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._key = key
        self._server = QLocalServer(self)
        self._server.newConnection.connect(self._on_new_connection)

    @property
    def key(self) -> str:
        return self._key

    @property
    def is_running(self) -> bool:
        return self._server.isListening()

    def try_acquire(self) -> bool:
        """True when this process owns the lock; False after poking the owner."""
        probe = QLocalSocket()
        probe.connectToServer(self._key)
        if probe.waitForConnected(CONNECT_TIMEOUT_MS):
            probe.write(b"show")
            probe.waitForBytesWritten(CONNECT_TIMEOUT_MS)
            probe.disconnectFromServer()
            return False

        QLocalServer.removeServer(self._key)
        if not self._server.listen(self._key):
            logger.warning("Could not listen on %s: %s", self._key, self._server.errorString())
            return False
        return True

    def close(self) -> None:
        self._server.close()
        QLocalServer.removeServer(self._key)

    def _on_new_connection(self) -> None:
        while self._server.hasPendingConnections():
            connection = self._server.nextPendingConnection()
            if connection is None:
                continue
            connection.readyRead.connect(lambda sock=connection: sock.readAll())
            connection.disconnected.connect(connection.deleteLater)
            self.activated.emit()
