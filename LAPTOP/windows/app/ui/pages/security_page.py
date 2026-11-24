"""Security page — PIN lock, Windows Hello, voiceprint (Phase 8)."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.services.security_service import SecurityService


class SecurityPage(QWidget):
    """Maya Security page: PIN lock, Windows Hello, voiceprint, audit log."""

    def __init__(
        self,
        security: SecurityService | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._security = security or SecurityService()
        self._attempts = 0
        self._build_ui()
        self._refresh()

    # -- ui -----------------------------------------------------------
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 8)
        layout.setSpacing(12)

        # ---- PIN lock ----
        pin_group = QFrame()
        pin_group.setStyleSheet(
            "QFrame { border: 1px solid #6e5494; border-radius: 8px; "
            "background-color: #2a2a3e; margin: 4px; }"
        )
        pl = QVBoxLayout(pin_group)
        pl.setContentsMargins(12, 10, 12, 10)
        pl.setSpacing(6)

        self._pin_status = QLabel("PIN Lock: Unknown")
        self._pin_status.setObjectName("cardLabel")
        pl.addWidget(self._pin_status)

        row = QHBoxLayout()
        self._set_pin_btn = QPushButton("Set PIN")
        self._set_pin_btn.setFixedHeight(32)
        self._set_pin_btn.clicked.connect(self._on_set_pin)
        row.addWidget(self._set_pin_btn)

        self._change_pin_btn = QPushButton("Change PIN")
        self._change_pin_btn.setFixedHeight(32)
        self._change_pin_btn.clicked.connect(self._on_change_pin)
        row.addWidget(self._change_pin_btn)

        self._lock_now_btn = QPushButton("Lock now")
        self._lock_now_btn.setFixedHeight(32)
        self._lock_now_btn.clicked.connect(self._on_lock_now)
        row.addWidget(self._lock_now_btn)
        pl.addLayout(row)

        self._pin_msg = QLabel("")
        self._pin_msg.setObjectName("emptyHint")
        self._pin_msg.setWordWrap(True)
        pl.addWidget(self._pin_msg)

        layout.addWidget(pin_group, 0)

        # ---- Windows Hello ----
        hello_group = QFrame()
        hello_group.setStyleSheet(
            "QFrame { border: 1px solid #4a90e2; border-radius: 8px; "
            "background-color: #2b2b40; margin: 4px; }"
        )
        hl = QVBoxLayout(hello_group)
        hl.setContentsMargins(12, 10, 12, 10)
        hl.setSpacing(6)

        self._hello_status = QLabel("Windows Hello: unknown")
        self._hello_status.setObjectName("cardLabel")
        hl.addWidget(self._hello_status)

        hrow = QHBoxLayout()
        self._hello_check_btn = QPushButton("Check availability")
        self._hello_check_btn.setFixedHeight(32)
        self._hello_check_btn.clicked.connect(self._on_hello_check)
        hrow.addWidget(self._hello_check_btn)

        self._hello_verify_btn = QPushButton("Verify now")
        self._hello_verify_btn.setFixedHeight(32)
        self._hello_verify_btn.clicked.connect(self._on_hello_verify)
        hrow.addWidget(self._hello_verify_btn)

        self._hello_settings_btn = QPushButton("Open sign-in settings")
        self._hello_settings_btn.setFixedHeight(32)
        self._hello_settings_btn.clicked.connect(self._on_hello_settings)
        hrow.addWidget(self._hello_settings_btn)
        hl.addLayout(hrow)

        self._hello_msg = QLabel("")
        self._hello_msg.setObjectName("emptyHint")
        self._hello_msg.setWordWrap(True)
        hl.addWidget(self._hello_msg)

        layout.addWidget(hello_group, 0)

        # ---- Voiceprint ----
        voice_group = QFrame()
        voice_group.setStyleSheet(
            "QFrame { border: 1px solid #7ed321; border-radius: 8px; "
            "background-color: #2e3e2f; margin: 4px; }"
        )
        vl = QVBoxLayout(voice_group)
        vl.setContentsMargins(12, 10, 12, 10)
        vl.setSpacing(6)

        self._voice_status = QLabel("Voiceprint: unknown")
        self._voice_status.setObjectName("cardLabel")
        vl.addWidget(self._voice_status)

        vrow = QHBoxLayout()
        self._voice_enroll_btn = QPushButton("Enroll voiceprint")
        self._voice_enroll_btn.setFixedHeight(32)
        self._voice_enroll_btn.clicked.connect(self._on_voice_enroll)
        vrow.addWidget(self._voice_enroll_btn)

        self._voice_reset_btn = QPushButton("Reset voiceprint")
        self._voice_reset_btn.setFixedHeight(32)
        self._voice_reset_btn.clicked.connect(self._on_voice_reset)
        vrow.addWidget(self._voice_reset_btn)
        vl.addLayout(vrow)

        self._voice_msg = QLabel("")
        self._voice_msg.setObjectName("emptyHint")
        self._voice_msg.setWordWrap(True)
        vl.addWidget(self._voice_msg)

        layout.addWidget(voice_group, 0)

        # ---- Audit log ----
        audit_label = QLabel("Audit log (last 20)")
        audit_label.setObjectName("emptyHint")
        layout.addWidget(audit_label)

        self._audit_view = QPlainTextEdit()
        self._audit_view.setReadOnly(True)
        self._audit_view.setMaximumHeight(180)
        layout.addWidget(self._audit_view, 1)

        self._refresh()

    # -- behaviour ----------------------------------------------------
    def _refresh(self) -> None:
        self._pin_status.setText(
            "PIN Lock: " + ("Enabled" if self._security.pin_is_set() else "Disabled")
        )
        self._change_pin_btn.setEnabled(self._security.pin_is_set())
        self._lock_now_btn.setEnabled(self._security.pin_is_set())

        vs = self._security.voice_status()
        enrolled = bool(vs.get("enrolled")) if isinstance(vs, dict) else False
        self._voice_status.setText("Voiceprint: " + ("Enrolled" if enrolled else "Not enrolled"))
        err = vs.get("error") if isinstance(vs, dict) else None
        if err:
            self._voice_msg.setText(str(err))

        alerts = self._security.alerts()
        lines = [f"{a.get('timestamp', '')} — {a.get('detail', '')}" for a in alerts[-20:]]
        self._audit_view.setPlainText("\n".join(lines) if lines else "No alerts.")

    def _on_set_pin(self) -> None:
        pin, ok = QInputDialog.getText(
            self, "Set PIN", "New PIN (4+ digits)", QLineEdit.EchoMode.Password
        )
        if not ok or not pin:
            return
        if len(pin) < 4 or not pin.isdigit():
            self._pin_msg.setText("PIN must be at least 4 digits.")
            return
        if self._security.pin_is_set():
            old, ok2 = QInputDialog.getText(
                self, "Current PIN", "Enter current PIN", QLineEdit.EchoMode.Password
            )
            if not ok2:
                return
            msg = self._security.set_pin(pin, old)
        else:
            # confirm
            again, ok3 = QInputDialog.getText(
                self, "Confirm PIN", "Re-enter PIN", QLineEdit.EchoMode.Password
            )
            if not ok3 or again != pin:
                self._pin_msg.setText("PINs do not match.")
                return
            msg = self._security.set_pin(pin)
        self._pin_msg.setText(str(msg))
        self._refresh()

    def _on_change_pin(self) -> None:
        if not self._security.pin_is_set():
            self._pin_msg.setText("No PIN set. Use Set PIN first.")
            return
        old, ok1 = QInputDialog.getText(
            self, "Current PIN", "Enter current PIN", QLineEdit.EchoMode.Password
        )
        if not ok1:
            return
        new, ok2 = QInputDialog.getText(
            self, "New PIN", "New PIN (4+ digits)", QLineEdit.EchoMode.Password
        )
        if not ok2 or not new:
            return
        if len(new) < 4 or not new.isdigit():
            self._pin_msg.setText("PIN must be at least 4 digits.")
            return
        msg = self._security.set_pin(new, old)
        self._pin_msg.setText(str(msg))
        self._refresh()

    def _on_lock_now(self) -> None:
        self._pin_msg.setText(str(self._security.lock()))
        self._refresh()

    def _on_hello_check(self) -> None:
        self._hello_msg.setText("Checking...")
        # run in background to avoid UI freeze (subprocess ~2s)
        self._hello_thread = _HelloCheckThread(self._security)
        self._hello_thread.result.connect(self._on_hello_result)
        self._hello_thread.start()

    def _on_hello_result(self, available: bool, error: str | None) -> None:
        self._hello_status.setText(
            "Windows Hello: " + ("Available" if available else "Not available")
        )
        self._hello_msg.setText(error or ("OK" if available else "Not available"))

    def _on_hello_verify(self) -> None:
        res = self._security.face_verify()
        ok = bool(res.get("ok")) if isinstance(res, dict) else False
        if ok:
            self._security.unlock("face")
            self._hello_msg.setText("Unlocked via Windows Hello.")
        else:
            err = res.get("error") if isinstance(res, dict) else res
            self._hello_msg.setText(str(err or "Verification failed."))
        self._refresh()

    def _on_hello_settings(self) -> None:
        res = self._security.open_face_settings()
        self._hello_msg.setText(
            "Opened Windows Sign-in settings"
            if (isinstance(res, dict) and res.get("ok"))
            else (res.get("error", "Failed") if isinstance(res, dict) else "Failed")
        )

    def _on_voice_enroll(self) -> None:
        from app.ui.voiceprint_wizard import VoiceprintWizard

        wizard = VoiceprintWizard(self._security, self)
        if wizard.exec() == VoiceprintWizard.DialogCode.Accepted:
            self._voice_msg.setText("Voiceprint enrolled.")
        else:
            self._voice_msg.setText("Enrollment cancelled.")
        self._refresh()

    def _on_voice_reset(self) -> None:
        ok = QMessageBox.question(
            self,
            "Reset Voiceprint",
            "Reset the enrolled voiceprint?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ok == QMessageBox.StandardButton.Yes:
            res = self._security.voice_reset()
            self._voice_msg.setText(
                "Reset done." if (isinstance(res, dict) and res.get("ok", True)) else str(res)
            )
            self._refresh()


class _HelloCheckThread(QThread):
    result = Signal(bool, object)

    def __init__(self, security: SecurityService, parent=None) -> None:
        super().__init__(parent)
        self._security = security

    def run(self) -> None:  # noqa: N802 - Qt override
        st = self._security.face_status()
        available = bool(st.get("available")) if isinstance(st, dict) else False
        err = st.get("error") if isinstance(st, dict) else None
        self.result.emit(available, err)
