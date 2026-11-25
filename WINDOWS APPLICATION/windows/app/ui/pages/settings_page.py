"""Settings page — appearance + startup (Phase 2).

Every save goes through `SettingsRepository`: validate, timestamped backup,
ruamel round-trip write. The page never edits YAML itself.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.services import autostart_service
from app.services.bluetooth_remote_client import reset_bluetooth_client
from app.services.phone_remote_client import reset_phone_remote_client
from app.services.server_service import shared_server_service
from app.services.wan_remote_client import reset_wan_client
from app.settings_repository import SettingsError, SettingsRepository
from app.ui.theme import MODES, ThemeManager
from app.ui.workers import ServerStartWorker

logger = logging.getLogger("maya.ui.settings")


def _card(title: str, hint: str = "") -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(20, 18, 20, 18)
    layout.setSpacing(10)

    heading = QLabel(title)
    heading.setObjectName("sectionTitle")
    layout.addWidget(heading)
    if hint:
        note = QLabel(hint)
        note.setObjectName("emptyHint")
        note.setWordWrap(True)
        layout.addWidget(note)
    return frame, layout


class SettingsPage(QScrollArea):
    """Scrollable settings form; emits `theme_changed` after a successful save."""

    theme_changed = Signal(str)
    settings_saved = Signal(dict)

    def __init__(
        self,
        repository: SettingsRepository,
        theme: ThemeManager | None = None,
        *,
        server_factory: Callable[[], Any] | None = None,
    ) -> None:
        super().__init__()
        self._repository = repository
        self._theme = theme
        self._server_factory = server_factory or shared_server_service
        self._server_start_worker: ServerStartWorker | None = None
        self.setWidgetResizable(True)
        self.setObjectName("settingsPage")

        body = QWidget()
        body.setObjectName("pageBody")
        self._layout = QVBoxLayout(body)
        self._layout.setContentsMargins(24, 20, 24, 24)
        self._layout.setSpacing(16)

        self._build_appearance()
        self._build_startup()
        self._build_phone_remote()
        self._build_bluetooth_remote()
        self._build_wan_remote()
        self._build_server()
        self._build_footer()

        self._layout.addStretch(1)
        self.setWidget(body)
        self._load()

    # -- sections -----------------------------------------------------

    def _build_appearance(self) -> None:
        card, layout = _card("Appearance", "Theme changes apply immediately after saving.")

        row = QHBoxLayout()
        row.setSpacing(12)
        theme_label = QLabel("Theme")
        theme_label.setMinimumWidth(160)
        self._theme_combo = QComboBox()
        for label, mode in (("Dark", "dark"), ("Light", "light"), ("System", "system")):
            self._theme_combo.addItem(label, mode)
        row.addWidget(theme_label)
        row.addWidget(self._theme_combo, 1)
        layout.addLayout(row)

        self._layout.addWidget(card)

    def _build_startup(self) -> None:
        card, layout = _card(
            "Startup & background",
            "Window/tray behaviour is stored in settings.yaml. Autostart is "
            "installed by the tray phase (Task Scheduler).",
        )

        self._close_to_tray = QCheckBox("Closing the window keeps Maya running in the tray")
        self._minimize_to_tray = QCheckBox("Minimize to the tray instead of the taskbar")
        self._start_minimized = QCheckBox("Start minimized")
        self._autostart = QCheckBox("Start Maya when Windows starts")
        self._autostart.setChecked(autostart_service.is_autostart_enabled())
        self._autostart.toggled.connect(self._on_autostart_toggled)

        for widget in (
            self._close_to_tray,
            self._minimize_to_tray,
            self._start_minimized,
            self._autostart,
        ):
            layout.addWidget(widget)

        self._layout.addWidget(card)

    def _on_autostart_toggled(self, checked: bool) -> None:
        ok = autostart_service.enable_autostart() if checked else autostart_service.disable_autostart()
        self._autostart.setChecked(autostart_service.is_autostart_enabled())
        if not ok:
            self._autostart.setToolTip("Could not update the Windows startup entry.")

    # -- phone server -------------------------------------------------
    def _build_server(self) -> None:
        card, layout = _card(
            "Phone server",
            "LAN-only FastAPI server on port 8420 for the Maya phone app. "
            "Start it here, or run `maya --headless`.",
        )

        self._server = None  # resolved from the app-wide shared instance
        self._server_status = QLabel("Status: Stopped")
        self._server_status.setObjectName("emptyHint")
        layout.addWidget(self._server_status)

        row = QHBoxLayout()
        row.setSpacing(8)
        self._server_start_btn = QPushButton("Start server")
        self._server_start_btn.setFixedHeight(32)
        self._server_start_btn.clicked.connect(self._on_server_start)
        row.addWidget(self._server_start_btn)

        self._server_stop_btn = QPushButton("Stop server")
        self._server_stop_btn.setFixedHeight(32)
        self._server_stop_btn.setEnabled(False)
        self._server_stop_btn.clicked.connect(self._on_server_stop)
        row.addWidget(self._server_stop_btn)

        self._server_pin_btn = QPushButton("New pairing PIN")
        self._server_pin_btn.setFixedHeight(32)
        self._server_pin_btn.setEnabled(False)
        self._server_pin_btn.clicked.connect(self._on_server_pin)
        row.addWidget(self._server_pin_btn)
        layout.addLayout(row)

        self._server_pin_label = QLabel("Pairing PIN: —")
        self._server_pin_label.setObjectName("cardLabel")
        self._server_pin_label.setWordWrap(True)
        layout.addWidget(self._server_pin_label)

        self._server_auto = QCheckBox("Start phone server with Maya")
        self._server_auto.setChecked(bool(self._repository.get("server.auto_start", False)))
        self._server_auto.toggled.connect(self._on_server_auto_toggled)
        layout.addWidget(self._server_auto)

        self._layout.addWidget(card)

    # -- phone remote -------------------------------------------------
    def _build_phone_remote(self) -> None:
        card, layout = _card(
            "Phone Remote",
            "Allow this laptop to control a paired phone (screen view, input, files). "
            "Requires the phone app to have 'Allow laptop control' enabled.",
        )

        self._phone_remote_enable = QCheckBox("Allow laptop to control paired phone")
        self._phone_remote_enable.setChecked(bool(self._repository.get("phone_remote.enabled", False)))
        self._phone_remote_enable.toggled.connect(self._on_phone_remote_toggled)
        layout.addWidget(self._phone_remote_enable)

        self._phone_remote_status = QLabel("Status: Disabled")
        self._phone_remote_status.setObjectName("emptyHint")
        layout.addWidget(self._phone_remote_status)

        self._layout.addWidget(card)

    def _on_phone_remote_toggled(self, checked: bool) -> None:
        """Update setting and reset client."""
        try:
            self._repository.update({"phone_remote.enabled": bool(checked)})
        except SettingsError as exc:
            self._phone_remote_status.setText(f"Status: Error — {exc}")
            return
        reset_phone_remote_client()
        self._refresh_phone_remote_state()

    def _refresh_phone_remote_state(self) -> None:
        enabled = bool(self._repository.get("phone_remote.enabled", False))
        self._phone_remote_enable.setChecked(enabled)
        if enabled:
            self._phone_remote_status.setText("Status: Enabled — pair phone and open Phone Remote tab")
        else:
            self._phone_remote_status.setText("Status: Disabled")

    # -- bluetooth remote ---------------------------------------------
    def _build_bluetooth_remote(self) -> None:
        card, layout = _card(
            "Bluetooth Remote",
            "Control paired phone via Bluetooth PAN (no WiFi needed). "
            "Requires phone Bluetooth tethering + PAN profile.",
        )

        self._bluetooth_remote_enable = QCheckBox("Enable Bluetooth remote control")
        self._bluetooth_remote_enable.setChecked(bool(self._repository.get("bluetooth_remote.enabled", False)))
        self._bluetooth_remote_enable.toggled.connect(self._on_bluetooth_remote_toggled)
        layout.addWidget(self._bluetooth_remote_enable)

        self._bluetooth_remote_status = QLabel("Status: Disabled")
        self._bluetooth_remote_status.setObjectName("emptyHint")
        layout.addWidget(self._bluetooth_remote_status)

        self._layout.addWidget(card)

    def _on_bluetooth_remote_toggled(self, checked: bool) -> None:
        """Update setting and reset client."""
        try:
            self._repository.update({"bluetooth_remote.enabled": bool(checked)})
        except SettingsError as exc:
            self._bluetooth_remote_status.setText(f"Status: Error — {exc}")
            return
        reset_bluetooth_client()
        self._refresh_bluetooth_remote_state()

    def _refresh_bluetooth_remote_state(self) -> None:
        enabled = bool(self._repository.get("bluetooth_remote.enabled", False))
        self._bluetooth_remote_enable.setChecked(enabled)
        if enabled:
            self._bluetooth_remote_status.setText("Status: Enabled — pair phone via Bluetooth, enable PAN tethering")
        else:
            self._bluetooth_remote_status.setText("Status: Disabled")

    # -- wan remote ---------------------------------------------------
    def _build_wan_remote(self) -> None:
        card, layout = _card(
            "Internet / WAN Remote",
            "Control phone over internet via self-hosted relay server. "
            "Requires TLS certificates and relay deployment.",
        )

        self._wan_remote_enable = QCheckBox("Enable Internet/WAN remote control")
        self._wan_remote_enable.setChecked(bool(self._repository.get("wan_remote.enabled", False)))
        self._wan_remote_enable.toggled.connect(self._on_wan_remote_toggled)
        layout.addWidget(self._wan_remote_enable)

        # Relay URL
        relay_row = QHBoxLayout()
        relay_row.setSpacing(8)
        relay_label = QLabel("Relay URL:")
        relay_label.setMinimumWidth(120)
        self._wan_relay_url = QComboBox()
        self._wan_relay_url.setEditable(True)
        self._wan_relay_url.addItems(["wss://relay.example.com:443", "wss://your-relay:8443"])
        current_url = str(self._repository.get("wan_remote.relay_url", ""))
        if current_url:
            self._wan_relay_url.setCurrentText(current_url)
        relay_row.addWidget(relay_label)
        relay_row.addWidget(self._wan_relay_url, 1)
        layout.addLayout(relay_row)

        # Cert path
        cert_row = QHBoxLayout()
        cert_row.setSpacing(8)
        cert_label = QLabel("Cert path:")
        cert_label.setMinimumWidth(120)
        self._wan_cert_path = QComboBox()
        self._wan_cert_path.setEditable(True)
        self._wan_cert_path.addItems(["MAYA AI/security/certs/wan_cert.pem"])
        current_cert = str(self._repository.get("wan_remote.cert_path", ""))
        if current_cert:
            self._wan_cert_path.setCurrentText(current_cert)
        cert_row.addWidget(cert_label)
        cert_row.addWidget(self._wan_cert_path, 1)
        layout.addLayout(cert_row)

        # Key path
        key_row = QHBoxLayout()
        key_row.setSpacing(8)
        key_label = QLabel("Key path:")
        key_label.setMinimumWidth(120)
        self._wan_key_path = QComboBox()
        self._wan_key_path.setEditable(True)
        self._wan_key_path.addItems(["MAYA AI/security/certs/wan_key.pem"])
        current_key = str(self._repository.get("wan_remote.key_path", ""))
        if current_key:
            self._wan_key_path.setCurrentText(current_key)
        key_row.addWidget(key_label)
        key_row.addWidget(self._wan_key_path, 1)
        layout.addLayout(key_row)

        self._wan_remote_status = QLabel("Status: Disabled")
        self._wan_remote_status.setObjectName("emptyHint")
        layout.addWidget(self._wan_remote_status)

        self._layout.addWidget(card)

    def _on_wan_remote_toggled(self, checked: bool) -> None:
        """Update setting and reset client."""
        try:
            self._repository.update({
                "wan_remote.enabled": bool(checked),
                "wan_remote.relay_url": self._wan_relay_url.currentText(),
                "wan_remote.cert_path": self._wan_cert_path.currentText(),
                "wan_remote.key_path": self._wan_key_path.currentText(),
            })
        except SettingsError as exc:
            self._wan_remote_status.setText(f"Status: Error — {exc}")
            return
        reset_wan_client()
        self._refresh_wan_remote_state()

    def _refresh_wan_remote_state(self) -> None:
        enabled = bool(self._repository.get("wan_remote.enabled", False))
        self._wan_remote_enable.setChecked(enabled)
        if enabled:
            self._wan_remote_status.setText("Status: Enabled — configure relay URL + certs, then connect")
        else:
            self._wan_remote_status.setText("Status: Disabled")

    # -- phone server -------------------------------------------------

    def showEvent(self, event) -> None:  # noqa: N802 - Qt signature
        self._refresh_server_state()
        super().showEvent(event)

    def shutdown(self) -> None:
        """Wait for a pending start before the page is destroyed (QThread safety)."""
        worker = self._server_start_worker
        if worker is not None and worker.isRunning():
            worker.wait(5000)
        self._server_start_worker = None

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt signature
        self.shutdown()
        super().closeEvent(event)

    def _refresh_server_state(self) -> None:
        """Match the card to the real server state (e.g. auto-started)."""
        if self._is_server_starting():
            return  # a worker owns the labels until it reports back
        try:
            svc = self._server_instance()
            running = bool(getattr(svc, "running", False))
        except Exception:  # noqa: BLE001 - never block the page
            running = False
            svc = None
        if running and svc is not None:
            self._server_status.setText(
                f"Status: Running on {svc.host}:{svc.bound_port or svc.port}"
            )
            self._server_start_btn.setEnabled(False)
            self._server_stop_btn.setEnabled(True)
            self._server_pin_btn.setEnabled(True)
        else:
            self._server_status.setText("Status: Stopped")
            self._server_start_btn.setEnabled(True)
            self._server_stop_btn.setEnabled(False)
            self._server_pin_btn.setEnabled(False)

    def _on_server_auto_toggled(self, checked: bool) -> None:
        """Persist the checkbox immediately (no Start click required)."""
        try:
            self._repository.update({"server.auto_start": bool(checked)})
        except SettingsError as exc:
            self._server_status.setText(f"Status: Error — {exc}")

    def _is_server_starting(self) -> bool:
        worker = self._server_start_worker
        return worker is not None and worker.isRunning()

    def _server_instance(self):
        """The app-wide server instance (shared with auto-start)."""
        if self._server is None:
            self._server = self._server_factory()
        return self._server

    def _on_server_start(self) -> None:
        """Queue the server boot on a worker thread and return immediately."""
        if self._is_server_starting():
            return

        try:
            svc = self._server_instance()
        except Exception as exc:  # noqa: BLE001 - report, never crash
            self._server_status.setText(f"Status: Error — {exc}")
            self._server_start_btn.setEnabled(True)
            return

        self._server_status.setText("Status: Starting...")
        self._server_start_btn.setEnabled(False)
        self._server_stop_btn.setEnabled(False)
        self._server_pin_btn.setEnabled(False)

        worker = ServerStartWorker(svc, self)
        worker.finished_ok.connect(self._on_server_started)
        worker.failed.connect(self._on_server_start_failed)
        worker.finished.connect(self._release_server_start_worker)
        self._server_start_worker = worker
        try:
            worker.start()
        except Exception as exc:  # noqa: BLE001 - thread pool refusal is rare
            self._server_start_worker = None
            self._server_status.setText(f"Status: Error — {exc}")
            self._server_start_btn.setEnabled(True)
            worker.deleteLater()

    def _on_server_started(self, address: str) -> None:
        """Worker reported success (UI thread): show the real address."""
        self._server_status.setText(f"Status: Running on {address or 'this laptop'}")
        self._server_start_btn.setEnabled(False)
        self._server_stop_btn.setEnabled(True)
        self._server_pin_btn.setEnabled(True)
        # persist auto_start (the checkbox is the user's intent, not the server)
        try:
            self._repository.update({"server.auto_start": self._server_auto.isChecked()})
        except SettingsError as exc:
            logger.warning("Could not persist server.auto_start: %s", exc)

    def _on_server_start_failed(self, message: str) -> None:
        """Worker reported an error (UI thread): show it and allow a retry."""
        self._server_status.setText(f"Status: Error — {message}")
        self._server_start_btn.setEnabled(True)
        self._server_stop_btn.setEnabled(False)
        self._server_pin_btn.setEnabled(False)

    def _release_server_start_worker(self) -> None:
        """QThread finished (UI thread): drop the reference and free the thread."""
        worker = self._server_start_worker
        self._server_start_worker = None
        if worker is not None:
            worker.deleteLater()

    def _on_server_stop(self) -> None:
        if self._is_server_starting():
            return  # let the pending start report back first
        svc = self._server
        self._server_start_btn.setEnabled(False)
        self._server_stop_btn.setEnabled(False)
        self._server_pin_btn.setEnabled(False)
        self._server_status.setText("Status: Stopping...")
        if svc is not None:
            try:
                svc.stop()
            except Exception:  # noqa: BLE001 - stop must never crash the page
                pass
        self._server = None
        self._server_status.setText("Status: Stopped")
        self._server_pin_label.setText("Pairing PIN: —")
        self._server_start_btn.setEnabled(True)

    def _on_server_pin(self) -> None:
        svc = self._server
        if svc is None or not svc.running:
            self._server_pin_label.setText("Pairing PIN: start server first")
            return
        try:
            pin, expires_at = svc.pairing.generate_pin()
            import time
            minutes = max(1, int((expires_at - time.time()) / 60))
            self._server_pin_label.setText(f"Pairing PIN: {pin}  (valid ~{minutes} min)")
        except Exception as exc:  # noqa: BLE001
            self._server_pin_label.setText(f"Pairing PIN: error — {exc}")

    def _build_footer(self) -> None:
        row = QHBoxLayout()
        row.setSpacing(12)

        self._save_button = QPushButton("Save settings")
        self._save_button.setObjectName("primaryButton")
        self._save_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._save_button.clicked.connect(self.save)

        self._backups_button = QPushButton("Open backups folder")
        self._backups_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._backups_button.clicked.connect(self._open_backups)

        self._status = QLabel("")
        self._status.setObjectName("formStatus")
        self._status.setWordWrap(True)

        row.addWidget(self._save_button)
        row.addWidget(self._backups_button)
        row.addWidget(self._status, 1)
        self._layout.addLayout(row)

    # -- data ---------------------------------------------------------

    def _load(self) -> None:
        current = str(self._repository.get("ui.theme", "system")).lower()
        index = self._theme_combo.findData(current if current in MODES else "system")
        self._theme_combo.setCurrentIndex(max(0, index))

        self._close_to_tray.setChecked(bool(self._repository.get("ui.close_to_tray", True)))
        self._minimize_to_tray.setChecked(
            bool(self._repository.get("ui.minimize_to_tray", True))
        )
        self._start_minimized.setChecked(bool(self._repository.get("ui.start_minimized", False)))
        self._refresh_phone_remote_state()
        self._refresh_bluetooth_remote_state()
        self._refresh_wan_remote_state()

    def _changes(self) -> dict[str, Any]:
        return {
            "ui.theme": str(self._theme_combo.currentData()),
            "ui.close_to_tray": self._close_to_tray.isChecked(),
            "ui.minimize_to_tray": self._minimize_to_tray.isChecked(),
            "ui.start_minimized": self._start_minimized.isChecked(),
        }

    # -- actions ------------------------------------------------------

    def save(self) -> bool:
        changes = self._changes()
        try:
            backup = self._repository.update(changes)
        except SettingsError as exc:
            self._set_status(str(exc), "error")
            return False

        if backup is None:
            self._set_status("No changes to save.", "neutral")
        else:
            self._set_status(f"Saved. Backup: {backup.name}", "ok")
            self.settings_saved.emit(changes)
            self._load()

        self.theme_changed.emit(changes["ui.theme"])
        return True

    def _open_backups(self) -> None:
        folder = self._repository.backup_dir
        Path(folder).mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _set_status(self, text: str, state: str) -> None:
        self._status.setText(text)
        self._status.setProperty("state", state)
        self._status.style().unpolish(self._status)
        self._status.style().polish(self._status)

    # -- test seams ---------------------------------------------------

    def set_theme_choice(self, mode: str) -> None:
        index = self._theme_combo.findData(mode)
        if index >= 0:
            self._theme_combo.setCurrentIndex(index)

    def set_startup_choices(
        self,
        *,
        close_to_tray: bool,
        minimize_to_tray: bool,
        start_minimized: bool,
    ) -> None:
        self._close_to_tray.setChecked(close_to_tray)
        self._minimize_to_tray.setChecked(minimize_to_tray)
        self._start_minimized.setChecked(start_minimized)

    @property
    def status_text(self) -> str:
        return self._status.text()
