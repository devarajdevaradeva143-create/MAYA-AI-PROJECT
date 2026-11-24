"""Modal lock screen shown when a PIN is set and the session is locked."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.services.security_service import SecurityService


class LockScreen(QDialog):
    def __init__(self, security: SecurityService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._security = security
        self.setWindowTitle("Maya is locked")
        self.setModal(True)
        self.setFixedSize(360, 260)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        title = QLabel("Maya is locked")
        title.setObjectName("cardLabel")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        hint = QLabel("Enter your PIN to continue.")
        hint.setObjectName("emptyHint")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(hint)

        self._pin = QLineEdit()
        self._pin.setEchoMode(QLineEdit.EchoMode.Password)
        self._pin.setMaxLength(12)
        self._pin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._pin.setFixedHeight(40)
        self._pin.returnPressed.connect(self._unlock_pin)
        layout.addWidget(self._pin)

        self._msg = QLabel("")
        self._msg.setObjectName("emptyHint")
        self._msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._msg.setWordWrap(True)
        layout.addWidget(self._msg)

        row = QHBoxLayout()
        self._unlock_btn = QPushButton("Unlock")
        self._unlock_btn.setFixedHeight(34)
        self._unlock_btn.clicked.connect(self._unlock_pin)
        row.addWidget(self._unlock_btn)

        self._hello_btn = QPushButton("Windows Hello")
        self._hello_btn.setFixedHeight(34)
        self._hello_btn.clicked.connect(self._unlock_hello)
        row.addWidget(self._hello_btn)
        layout.addLayout(row)

        layout.addStretch(1)

    def _unlock_pin(self) -> None:
        pin = self._pin.text().strip()
        if not pin:
            self._msg.setText("Enter a PIN.")
            return
        msg = self._security.verify_pin(pin)
        self._msg.setText(str(msg))
        if str(msg).lower().startswith("unlocked"):
            self.accept()
        else:
            self._pin.clear()

    def _unlock_hello(self) -> None:
        res = self._security.face_verify()
        ok = bool(res.get("ok")) if isinstance(res, dict) else False
        if ok:
            self._security.unlock("face")
            self.accept()
        else:
            err = res.get("error") if isinstance(res, dict) else res
            self._msg.setText(str(err or "Windows Hello failed."))
