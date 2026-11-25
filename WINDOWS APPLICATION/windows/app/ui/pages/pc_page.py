"""PC control page — grid of actions, command builder, file tools, activity log, and phone request queue (Phase 5)."""

from __future__ import annotations

from collections import deque
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.services.control_service import ControlService

# UI label -> server action id (the phone API and ControlService use the ids).
ACTION_IDS: dict[str, str] = {
    "Open app": "app.open",
    "Close app": "app.close",
    "Read file": "file.read",
    "Edit file": "file.write",
    "Delete file": "file.delete",
    "Run command": "cmd.run",
    "Lock workstation": "system.lock",
    "Sleep": "system.sleep",
    "Shutdown": "system.shutdown",
    "Set volume": "system.volume",
    "Mute/unmute": "system.mute",
    "Screenshot": "system.screenshot",
    "Clipboard get": "clipboard.get",
    "Clipboard set": "clipboard.set",
    "Notify": "notify",
    "WhatsApp message": "whatsapp.message",
}


class ConfirmDialog(QDialog):
    """Modal dialog: [Cancel] [Allow] for destructive actions."""

    allow_clicked = Signal()
    cancel_clicked = Signal()

    def __init__(self, action: str, risk: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Confirmation")
        self.setFixedSize(400, 180)
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(12)

        text = f'Maya wants to: <b>{action}</b><br/>Risk: {risk}'
        label = QLabel(text)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(label)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(20)

        self._btn_allow = QPushButton("Allow")
        self._btn_allow.setFixedSize(100, 36)
        self._btn_allow.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_allow.clicked.connect(self._on_allow)

        self._btn_cancel = QPushButton("Cancel")
        self._btn_cancel.setFixedSize(100, 36)
        self._btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_cancel.clicked.connect(self._on_cancel)

        btn_layout.addStretch(1)
        btn_layout.addWidget(self._btn_cancel)
        btn_layout.addWidget(self._btn_allow)
        btn_layout.addStretch(1)

        layout.addStretch(1)
        layout.addLayout(btn_layout)

    def _on_allow(self) -> None:
        self.allow_clicked.emit()
        self.close()

    def _on_cancel(self) -> None:
        self.cancel_clicked.emit()
        self.close()


class PCPage(QWidget):
    """Maya PC control page: grid of actions, command builder, file tools, log."""

    action_performed = Signal(str, str)  # action, result

    def __init__(self, control: ControlService | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._control = control or ControlService()
        self._audit_log: deque[str] = deque(maxlen=50)
        self._pending_params: dict[str, Any] = {}
        self._pending_action_id: str = ""

        self._build_ui()
        self._update_audit_view()

    # -- ui -----------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # --- Top control row ---
        top = QHBoxLayout()
        top.setContentsMargins(24, 16, 24, 8)
        top.setSpacing(12)

        # Quick action grid selector
        self._action_combo = QComboBox()
        self._action_combo.addItems([
            "Open app",
            "Close app",
            "Read file",
            "Edit file",
            "Delete file",
            "Run command",
            "Lock workstation",
            "Sleep",
            "Shutdown",
            "Set volume",
            "Mute/unmute",
            "Screenshot",
            "Clipboard get",
            "Clipboard set",
            "Notify",
            "WhatsApp message",
        ])
        self._action_combo.setFixedWidth(200)

        # Run button
        self._run_button = QPushButton("Run")
        self._run_button.setFixedSize(80, 36)
        self._run_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._run_button.clicked.connect(self._on_run)

        top.addWidget(QLabel("Action:"))
        top.addWidget(self._action_combo)
        top.addWidget(self._run_button)

        layout.addLayout(top)

        # --- Action grid ---
        # Dynamic grid of quick-action buttons (populated from the combo selection)
        self._grid = QGridLayout()
        self._grid.setContentsMargins(24, 8, 24, 8)
        self._grid.setSpacing(8)
        layout.addLayout(self._grid, 1)

        # --- Activity log ---
        left = QVBoxLayout()
        left.setContentsMargins(24, 0, 12, 0)
        left.setSpacing(6)

        self._log_label = QLabel("Activity log (last 50)")
        self._log_label.setObjectName("emptyHint")
        left.addWidget(self._log_label)

        self._log_view = QPlainTextEdit()
        self._log_view.setReadOnly(True)
        self._log_view.setMaximumHeight(180)
        self._log_view.setPlainText("")
        left.addWidget(self._log_view)

        left.addStretch(1)
        layout.addLayout(left, 0)

        # Connect audit signal (ControlService writes to its own log;
        # PCPage also keeps a local view).
        self.action_performed.connect(self._on_action_performed)

    # -- behaviour ----------------------------------------------------

    def _on_run(self) -> None:
        action = str(self._action_combo.currentText())
        params: dict[str, Any] = {}

        if action == "Open app":
            name, ok = self._show_input("Application name", "e.g. notepad.exe")
            if ok and name:
                params["name"] = name
        elif action == "Close app":
            name, ok = self._show_input("Application name", "e.g. chrome")
            if ok and name:
                params["name"] = name
        elif action == "Read file":
            path, ok = self._show_input("File path", "e.g. C:\\notes.txt")
            if ok and path:
                params["path"] = path
        elif action == "Edit file":
            path, ok1 = self._show_input("File path", "e.g. C:\\notes.txt")
            if ok1 and path:
                content, ok2 = self._show_multiline("Edit content", "New file content")
                if ok2:
                    params["path"] = path
                    params["content"] = content
        elif action == "Delete file":
            path, ok = self._show_input("File path", "e.g. C:\\temp\\old.txt")
            if ok and path:
                params["path"] = path
        elif action == "Run command":
            cmd, ok = self._show_input("Command", "e.g. dir or ipconfig")
            if ok and cmd:
                params["command"] = cmd
        elif action == "Lock workstation":
            # No params; confirm dialog
            self._show_confirm("Lock workstation", "This will lock the Windows workstation. Continue?")
            return
        elif action == "Sleep":
            self._show_confirm("Put computer to sleep", "This will sleep the computer. Continue?")
            return
        elif action == "Shutdown":
            self._show_confirm("Shut down computer", "This will shut down the computer. Continue?")
            return
        elif action == "Set volume":
            level, ok1 = self._show_input("Volume level (0-100)", "e.g. 75")
            if ok1 and level:
                try:
                    params["level"] = max(0, min(100, int(level)))
                except ValueError:
                    self.action_performed.emit(action, "Error: volume must be a number 0-100")
                    return
        elif action == "Mute/unmute":
            self._show_confirm("Toggle mute", "Toggle system audio mute?")
            return
        elif action == "Screenshot":
            self._show_confirm("Take screenshot", "Capture screen and save to screenshots folder?")
            return
        elif action == "Clipboard get":
            self._show_confirm("Read clipboard", "Read and display system clipboard?")
            return
        elif action == "Clipboard set":
            text, ok1 = self._show_input("Text to copy", "e.g. Hello Maya")
            if ok1 and text:
                params["text"] = text
        elif action == "Notify":
            title, ok1 = self._show_input("Notification title", "e.g. Maya")
            if ok1 and title:
                body, ok2 = self._show_input("Notification body", "e.g. Task completed")
                if ok2:
                    params["title"] = title
                    params["body"] = body
        elif action == "WhatsApp message":
            number, ok1 = self._show_input(
                "WhatsApp number (country code, digits)", "e.g. 919876543210"
            )
            if not (ok1 and number):
                return
            text, ok2 = self._show_multiline("WhatsApp message", "Type the message")
            if not (ok2 and text.strip()):
                return
            params["number"] = number
            params["text"] = text.strip()
            self._show_confirm(
                f"Send WhatsApp to {number}",
                "WhatsApp opens with this message prefilled; you press Send.",
                params,
                "whatsapp.message",
            )
            return

        # Execute the action
        try:
            result = self._control.execute(ACTION_IDS.get(action, action), params)
            self.action_performed.emit(action, str(result.get("message", result)))
        except (RuntimeError, KeyError, OSError) as e:
            self.action_performed.emit(action, f"Error: {e}")

    def _show_input(self, label: str, placeholder: str) -> tuple[str, bool]:
        """Simple input dialog (placeholder; real app would use QInputDialog)."""
        from PySide6.QtWidgets import QInputDialog
        text, ok = QInputDialog.getText(self, label, label, QLineEdit.EchoMode.Normal, placeholder)
        return (text or ""), ok

    def _show_multiline(self, label: str, placeholder: str) -> tuple[str, bool]:
        """Simple multiline input dialog."""
        from PySide6.QtWidgets import (
            QDialog,
            QLabel,
            QPlainTextEdit,
            QPushButton,
            QVBoxLayout,
        )
        d = QDialog(self)
        d.setWindowTitle(label)
        d.setFixedSize(400, 300)
        layout = QVBoxLayout(d)
        note = QLabel(placeholder)
        plain = QPlainTextEdit()
        plain.setPlainText(placeholder)
        layout.addWidget(note)
        layout.addWidget(plain)
        btns = QHBoxLayout()
        btn_accept = QPushButton("OK")
        btn_cancel = QPushButton("Cancel")
        btn_accept.clicked.connect(d.accept)
        btn_cancel.clicked.connect(d.reject)
        btns.addWidget(btn_cancel)
        btns.addWidget(btn_accept)
        layout.addLayout(btns)
        if d.exec() == QDialog.Accepted:
            return (plain.toPlainText() or ""), True
        return ("", False)

    def _show_confirm(
        self,
        action: str,
        risk: str,
        params: dict[str, Any] | None = None,
        action_id: str | None = None,
    ) -> None:
        """Show a ConfirmDialog; if Allow → execute, if Cancel → do nothing."""
        self._pending_params = dict(params or {})
        self._pending_action_id = action_id or ACTION_IDS.get(action, action)
        d = ConfirmDialog(action, risk, self)
        d.allow_clicked.connect(lambda: self._execute_after_confirm(action))
        d.cancel_clicked.connect(self._on_confirm_cancelled)
        d.show()

    def _on_confirm_cancelled(self) -> None:
        self._pending_params = {}
        self._pending_action_id = ""

    def _execute_after_confirm(self, action: str) -> None:
        """Execute the action after the user confirmed."""
        params = self._pending_params
        action_id = self._pending_action_id or ACTION_IDS.get(action, action)
        self._pending_params = {}
        self._pending_action_id = ""
        try:
            result = self._control.execute(action_id, params)
            self.action_performed.emit(action, str(result.get("message", result)))
        except (RuntimeError, KeyError, OSError) as e:
            self.action_performed.emit(action, f"Error: {e}")

    def _on_action_performed(self, action: str, result: str) -> None:
        """Called from ControlService after an action completes."""
        self._audit_log.append(f"{action}: {result}")
        self._update_audit_view()

    # -- audit log ----------------------------------------------------

    def _update_audit_view(self) -> None:
        lines = [f"{i+1}. {entry}" for i, entry in enumerate(self._audit_log)]
        self._log_view.setPlainText("\n".join(lines[-50:]))