"""Settings page — appearance + startup (Phase 2).

Every save goes through `SettingsRepository`: validate, timestamped backup,
ruamel round-trip write. The page never edits YAML itself.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QImage, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.services import autostart_service
from app.services.bluetooth_remote_client import reset_bluetooth_client
from app.services.cloud_service import CloudAdapter
from app.services.engine_service import EngineAdapter
from app.services.model_service import ModelService
from app.services.phone_remote_client import reset_phone_remote_client
from app.services.p2p_service import get_p2p_service
import io
import json
import socket

from app.services.server_service import lan_ip, shared_server_service
from app.services.wan_remote_client import reset_wan_client
from app.settings_repository import SettingsError, SettingsRepository
from app.ui.theme import MODES, ThemeManager
from app.ui.widgets import ModelManager
from app.ui.workers import ServerStartWorker

logger = logging.getLogger("maya.ui.settings")


def _flag(value: Any, default: bool = True) -> bool:
    """Read a boolean setting, even when the YAML holds a quoted string."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "on", "1"}:
            return True
        if lowered in {"false", "no", "off", "0"}:
            return False
    return default


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

    # Engine probes run off the UI thread and report back through these.
    _engine_health = Signal(bool, str, str)  # ok, model, error
    _engine_progress = Signal(dict)  # one pull chunk
    _engine_fix_done = Signal(bool)  # engine started?

    def __init__(
        self,
        repository: SettingsRepository,
        theme: ThemeManager | None = None,
        *,
        server_factory: Callable[[], Any] | None = None,
        cloud: Any | None = None,
        engine: Any | None = None,
        model_service: ModelService | None = None,
    ) -> None:
        super().__init__()
        self._repository = repository
        self._theme = theme
        self._cloud = cloud or CloudAdapter()
        self._server_factory = server_factory or shared_server_service
        self._engine = engine
        self._model_service = model_service
        self._engine_health_running = False
        self._server_start_worker: ServerStartWorker | None = None
        self._engine_health.connect(self._apply_engine_health)
        self._engine_progress.connect(self._apply_engine_progress)
        self._engine_fix_done.connect(self._apply_engine_fix_done)
        self.setWidgetResizable(True)
        self.setObjectName("settingsPage")

        body = QWidget()
        body.setObjectName("pageBody")
        self._layout = QVBoxLayout(body)
        self._layout.setContentsMargins(24, 20, 24, 24)
        self._layout.setSpacing(16)

        self._build_engines()
        self._build_appearance()
        self._build_startup()
        self._build_phone_remote()
        self._build_bluetooth_remote()
        self._build_wan_remote()
        self._build_p2p()
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

    # -- AI engine (local + cloud) -------------------------------------
    @staticmethod
    def _make_switch(checked: bool) -> QPushButton:
        """A small On/Off push button used by the engine switches."""
        button = QPushButton()
        button.setCheckable(True)
        button.setChecked(checked)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setFixedSize(76, 32)
        SettingsPage._paint_switch(button, checked)
        return button

    @staticmethod
    def _paint_switch(button: QPushButton, checked: bool) -> None:
        button.setText("On" if checked else "Off")
        button.setObjectName("switchOn" if checked else "switchOff")
        button.setToolTip("On — click to switch off" if checked else "Off — click to switch on")
        button.style().unpolish(button)
        button.style().polish(button)

    def _build_engines(self) -> None:
        card, layout = _card(
            "AI Engine",
            "Pick who answers. Lemonade runs on this laptop. When Lemonade is off "
            "(or fails) Gemini answers instead — no extra click. Switch either "
            "on or off; use whichever you prefer.",
        )

        # Local engine row
        local_row = QHBoxLayout()
        local_row.setSpacing(12)
        local_label = QLabel("Lemonade (local engine)")
        local_label.setMinimumWidth(180)
        self._engine_status = QLabel("Status: —")
        self._engine_status.setObjectName("emptyHint")
        self._engine_status.setWordWrap(True)
        self._engine_enable = self._make_switch(_flag(self._repository.get("engine.enabled", True)))
        self._engine_enable.toggled.connect(self._on_engine_toggled)
        local_row.addWidget(local_label)
        local_row.addWidget(self._engine_status, 1)
        local_row.addWidget(self._engine_enable)
        layout.addLayout(local_row)

        # Model info row
        model_row = QHBoxLayout()
        model_row.setSpacing(12)
        self._model_name_label = QLabel("Model: —")
        self._model_name_label.setMinimumWidth(180)
        self._model_name_label.setObjectName("emptyHint")
        model_row.addWidget(self._model_name_label)
        layout.addLayout(model_row)

        # Backend badge row
        backend_row = QHBoxLayout()
        backend_row.setSpacing(12)
        self._backend_label = QLabel("Backend: —")
        self._backend_label.setMinimumWidth(180)
        self._backend_label.setObjectName("emptyHint")
        backend_row.addWidget(self._backend_label)
        layout.addLayout(backend_row)

        # Action buttons row
        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        action_row.addStretch(1)

        self._engine_download_btn = QPushButton("Download")
        self._engine_download_btn.setFixedHeight(32)
        self._engine_download_btn.clicked.connect(self._on_engine_download)
        self._engine_download_btn.setVisible(False)
        action_row.addWidget(self._engine_download_btn)

        self._engine_fix_btn = QPushButton("Fix")
        self._engine_fix_btn.setFixedHeight(32)
        self._engine_fix_btn.clicked.connect(self._on_engine_fix)
        self._engine_fix_btn.setVisible(False)
        action_row.addWidget(self._engine_fix_btn)

        layout.addLayout(action_row)

        # Model Manager
        self._model_manager = ModelManager(
            self._repository, model_service=self._model_service, parent=self
        )
        self._model_manager.model_changed.connect(self._on_model_changed)
        layout.addWidget(self._model_manager)

        cloud_row = QHBoxLayout()
        cloud_row.setSpacing(12)
        cloud_label = QLabel("Gemini (cloud AI)")
        cloud_label.setMinimumWidth(180)
        self._cloud_status = QLabel("Status: —")
        self._cloud_status.setObjectName("emptyHint")
        self._cloud_status.setWordWrap(True)
        self._cloud_enable = self._make_switch(_flag(self._repository.get("cloud.enabled", True)))
        self._cloud_enable.toggled.connect(self._on_cloud_toggled)
        cloud_row.addWidget(cloud_label)
        cloud_row.addWidget(self._cloud_status, 1)
        cloud_row.addWidget(self._cloud_enable)
        layout.addLayout(cloud_row)

        key_row = QHBoxLayout()
        key_row.setSpacing(8)
        key_label = QLabel("API key")
        key_label.setMinimumWidth(160)
        self._cloud_key_input = QLineEdit()
        self._cloud_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._cloud_key_input.setPlaceholderText("Paste a Gemini API key (AIza…)")
        self._cloud_key_button = QPushButton("Save key")
        self._cloud_key_button.setFixedHeight(32)
        self._cloud_key_button.clicked.connect(self._on_cloud_key_save)
        key_row.addWidget(key_label)
        key_row.addWidget(self._cloud_key_input, 1)
        key_row.addWidget(self._cloud_key_button)
        layout.addLayout(key_row)

        prompt_label = QLabel("Gemini prompt")
        prompt_label.setMinimumWidth(160)
        prompt_row = QHBoxLayout()
        prompt_row.setSpacing(8)
        self._cloud_prompt_input = QPlainTextEdit()
        self._cloud_prompt_input.setPlaceholderText(
            "Instruction sent with every Gemini request (empty = Gemini's default)."
        )
        self._cloud_prompt_input.setFixedHeight(76)
        self._cloud_prompt_save = QPushButton("Save prompt")
        self._cloud_prompt_save.setFixedHeight(32)
        self._cloud_prompt_save.clicked.connect(self._on_cloud_prompt_save)
        prompt_row.addWidget(prompt_label)
        prompt_row.addWidget(self._cloud_prompt_input, 1)
        prompt_row.addWidget(self._cloud_prompt_save)
        layout.addLayout(prompt_row)

        hint = QLabel(
            'Get a key: <a href="https://aistudio.google.com/app/apikey">'
            "aistudio.google.com/app/apikey</a>"
        )
        hint.setOpenExternalLinks(True)
        hint.setObjectName("emptyHint")
        layout.addWidget(hint)

        self._layout.addWidget(card)

    def _on_engine_toggled(self, checked: bool) -> None:
        try:
            self._repository.update({"engine.enabled": bool(checked)})
        except SettingsError as exc:
            self._revert_switch(self._engine_enable, not checked)
            self._engine_status.setText(f"Status: Error — {exc}")
            return
        self._paint_switch(self._engine_enable, checked)
        self._refresh_engine_state()
        self._sync_switch_hint()
        self.settings_saved.emit({"engine.enabled": bool(checked)})

    def _on_model_changed(self, model_id: str) -> None:
        """Called when user sets a new default model from ModelManager."""
        self._refresh_engine_state()
        self.settings_saved.emit({"engine.model": model_id})

    @staticmethod
    def _revert_switch(button: QPushButton, checked: bool) -> None:
        """Put the switch back when the setting could not be written."""
        button.blockSignals(True)
        button.setChecked(checked)
        button.blockSignals(False)
        SettingsPage._paint_switch(button, checked)

    def _refresh_engine_state(self) -> None:
        enabled = _flag(self._repository.get("engine.enabled", True))
        self._engine_enable.blockSignals(True)
        self._engine_enable.setChecked(enabled)
        self._engine_enable.blockSignals(False)
        self._paint_switch(self._engine_enable, enabled)

        model = str(self._repository.get("engine.model", "") or "")
        self._model_name_label.setText(f"Model: {model}" if model else "Model: —")

        if not enabled:
            self._engine_download_btn.setVisible(False)
            self._engine_fix_btn.setVisible(False)
            self._backend_label.setText("Backend: —")
            if self._cloud_off():
                self._engine_status.setText(
                    "Status: Off — Gemini is off too, so chat cannot answer. Turn one on."
                )
            else:
                self._engine_status.setText("Status: Off — chat answers with Gemini (cloud).")
            return

        host = str(self._repository.get("engine.host", "") or "localhost")
        detail = f" · {model}" if model else ""
        self._engine_status.setText(f"Status: On · {host}{detail}")

        # Check engine health and model availability in background
        self._check_engine_health(model)

    def _check_engine_health(self, model: str) -> None:
        """Probe the engine off the UI thread; the result arrives as a signal."""
        if self._engine_health_running:
            return
        self._engine_health_running = True
        engine = self._engine if self._engine is not None else EngineAdapter()

        def worker() -> None:
            try:
                health = engine.health()
                ok = bool(
                    health.get("ok", health.get("status") in {"ok", "healthy", "ready"})
                )
                models = [str(m) for m in (health.get("models") or [])]
                missing = "not downloaded" if ok and model and model not in models else ""
                self._engine_health.emit(ok, model, missing)
            except Exception as exc:  # noqa: BLE001 - shown in the status label
                self._engine_health.emit(False, model, str(exc))

        threading.Thread(target=worker, name="maya-engine-health", daemon=True).start()

    def _apply_engine_health(self, ok: bool, model: str, error: str) -> None:
        """Render the health probe result (UI thread)."""
        self._engine_health_running = False
        if not _flag(self._repository.get("engine.enabled", True)):
            return

        if not ok:
            self._engine_status.setText("Status: Engine offline")
            self._engine_fix_btn.setVisible(True)
            self._engine_download_btn.setVisible(False)
            self._backend_label.setText("Backend: Unknown")
            return

        backend = "FLM (NPU)" if "FLM" in model.upper() else "llama.cpp (GPU)"
        self._backend_label.setText(f"Backend: {backend}")

        if error:
            self._engine_status.setText("Status: Model not downloaded")
            self._engine_download_btn.setVisible(True)
            self._engine_fix_btn.setVisible(False)
            return

        host = str(self._repository.get("engine.host", "") or "localhost")
        self._engine_status.setText(f"Status: Ready · {host}")
        self._engine_download_btn.setVisible(False)
        self._engine_fix_btn.setVisible(False)

    def _on_engine_download(self) -> None:
        """Download the configured model in the background."""
        model = str(self._repository.get("engine.model", "") or "")
        if not model:
            return
        self._engine_download_btn.setEnabled(False)
        self._engine_download_btn.setText("Downloading...")
        self._engine_status.setText(f"Status: Downloading {model}...")

        service = self._model_service
        if service is None:
            host = str(self._repository.get("engine.host", "http://localhost:13305"))
            service = ModelService(host=host)

        def worker() -> None:
            try:
                for chunk in service.pull(model):
                    self._engine_progress.emit(chunk)
            except Exception as exc:  # noqa: BLE001 - shown in the status label
                self._engine_progress.emit({"status": "error", "message": str(exc)})

        threading.Thread(target=worker, name="maya-model-download", daemon=True).start()

    def _apply_engine_progress(self, chunk: dict[str, Any]) -> None:
        """Render one download progress chunk (UI thread)."""
        status = str(chunk.get("status", ""))
        if status == "downloading":
            message = str(chunk.get("message", "") or "").strip()
            if message:
                self._engine_status.setText(f"Status: {message}")
        elif status == "completed":
            self._engine_status.setText("Status: Download complete — checking...")
            self._engine_download_btn.setEnabled(True)
            self._engine_download_btn.setText("Download")
            self._refresh_engine_state()
        elif status in {"error", "cancelled"}:
            message = str(chunk.get("message", status) or status)
            self._engine_status.setText(f"Status: Download failed — {message}")
            self._engine_download_btn.setEnabled(True)
            self._engine_download_btn.setText("Download")

    def _on_engine_fix(self) -> None:
        """Start the local engine in the background."""
        self._engine_fix_btn.setEnabled(False)
        self._engine_fix_btn.setText("Fixing...")
        self._engine_status.setText("Status: Starting engine...")

        def worker() -> None:
            try:
                host = str(self._repository.get("engine.host", "http://localhost:13305"))
                from app.services.engine_bootstrap import ensure_engine

                self._engine_fix_done.emit(ensure_engine(host))
            except Exception:  # noqa: BLE001 - reported as a failed start
                self._engine_fix_done.emit(False)

        threading.Thread(target=worker, name="maya-engine-fix", daemon=True).start()

    def _apply_engine_fix_done(self, ok: bool) -> None:
        """Render the engine-start result (UI thread)."""
        self._engine_fix_btn.setEnabled(True)
        self._engine_fix_btn.setText("Fix")
        if ok:
            self._refresh_engine_state()
        else:
            self._engine_status.setText("Status: Engine start failed")

    def _on_cloud_toggled(self, checked: bool) -> None:
        try:
            self._repository.update({"cloud.enabled": bool(checked)})
        except SettingsError as exc:
            self._revert_switch(self._cloud_enable, not checked)
            self._cloud_status.setText(f"Status: Error — {exc}")
            return
        self._paint_switch(self._cloud_enable, checked)
        self._refresh_cloud_state()
        self._sync_switch_hint()
        self.settings_saved.emit({"cloud.enabled": bool(checked)})

    def _sync_switch_hint(self) -> None:
        """Point at the abandoned engine when both switches are off."""
        if not self._cloud_off():
            return
        self._refresh_engine_state()

    def _on_cloud_key_save(self) -> None:
        key = self._cloud_key_input.text().strip()
        if not key:
            self._cloud_status.setText("Status: Enter a key first.")
            return
        result = self._cloud.save_api_key(key)
        if not result.get("ok"):
            self._cloud_status.setText(f"Status: Error — {result.get('error') or 'key not saved'}")
            return
        self._cloud_key_input.clear()
        self._refresh_cloud_state()
        self._cloud_status.setText("Status: Key saved to .env (value never shown).")

    def _on_cloud_prompt_save(self) -> None:
        prompt = self._cloud_prompt_input.toPlainText().strip()
        try:
            self._repository.update({"cloud.system_prompt": prompt})
        except SettingsError as exc:
            self._cloud_status.setText(f"Status: Error — {exc}")
            return
        self._refresh_cloud_state()
        self._cloud_status.setText(
            "Status: Prompt saved." if prompt else "Status: Prompt cleared — Gemini's default is used."
        )
        self.settings_saved.emit({"cloud.system_prompt": prompt})

    def _cloud_off(self) -> bool:
        try:
            return not _flag(self._repository.get("cloud.enabled", True))
        except Exception:  # noqa: BLE001 - a broken config must not block the page
            return False

    def _refresh_cloud_state(self) -> None:
        status = self._cloud.status()
        # The page owns the switch; the adapter only reports key/model state.
        enabled = _flag(self._repository.get("cloud.enabled", True))
        self._cloud_enable.blockSignals(True)
        self._cloud_enable.setChecked(enabled)
        self._cloud_enable.blockSignals(False)
        self._paint_switch(self._cloud_enable, enabled)
        if not enabled:
            self._cloud_status.setText("Status: Disabled — Gemini will not answer.")
            return
        if not status.get("configured"):
            self._cloud_status.setText("Status: No API key saved — paste one above.")
            return
        preview = status.get("key_preview") or ""
        model = status.get("model") or ""
        self._cloud_status.setText(
            f"Status: Ready · key {preview or 'saved'} · model {model}"
        )

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

        self._server_qr_btn = QPushButton("Show QR code")
        self._server_qr_btn.setFixedHeight(32)
        self._server_qr_btn.setEnabled(False)
        self._server_qr_btn.clicked.connect(self._on_server_qr)
        row.addWidget(self._server_qr_btn)
        layout.addLayout(row)

        self._server_pin_label = QLabel("Pairing PIN: —")
        self._server_pin_label.setObjectName("cardLabel")
        self._server_pin_label.setWordWrap(True)
        layout.addWidget(self._server_pin_label)

        self._server_qr_label = QLabel()
        self._server_qr_label.setAlignment(Qt.AlignCenter)
        self._server_qr_label.setMinimumHeight(200)
        self._server_qr_label.hide()
        layout.addWidget(self._server_qr_label)

        self._server_qr_status = QLabel("")
        self._server_qr_status.setObjectName("cardLabel")
        self._server_qr_status.setWordWrap(True)
        layout.addWidget(self._server_qr_status)

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
        self._wan_remote_enable.setChecked(bool(self._repository.get("server.wan.enabled", False)))
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
        current_url = str(self._repository.get("server.wan.relay_url", ""))
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
        current_cert = str(self._repository.get("server.wan.cert_path", ""))
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
        current_key = str(self._repository.get("server.wan.key_path", ""))
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
                "server.wan.enabled": bool(checked),
                "server.wan.relay_url": self._wan_relay_url.currentText(),
                "server.wan.cert_path": self._wan_cert_path.currentText(),
                "server.wan.key_path": self._wan_key_path.currentText(),
            })
        except SettingsError as exc:
            self._wan_remote_status.setText(f"Status: Error — {exc}")
            return
        reset_wan_client()
        self._refresh_wan_remote_state()

    def _refresh_wan_remote_state(self) -> None:
        enabled = bool(self._repository.get("server.wan.enabled", False))
        self._wan_remote_enable.setChecked(enabled)
        if enabled:
            self._wan_remote_status.setText("Status: Enabled — configure relay URL + certs, then connect")
        else:
            self._wan_remote_status.setText("Status: Disabled")

    # -- internet p2p -------------------------------------------------
    def _build_p2p(self) -> None:
        card, layout = _card(
            "Internet P2P",
            "Direct WebRTC from anywhere. Manual QR/code only. No cloud data server.",
        )
        self._p2p_enable = QCheckBox("Enable Internet P2P")
        self._p2p_enable.setChecked(bool(self._repository.get("p2p.enabled", False)))
        self._p2p_enable.toggled.connect(self._on_p2p_toggled)
        layout.addWidget(self._p2p_enable)

        row = QHBoxLayout()
        row.setSpacing(8)
        self._p2p_offer_btn = QPushButton("Create offer QR")
        self._p2p_offer_btn.clicked.connect(self._on_p2p_offer)
        self._p2p_answer_btn = QPushButton("Paste answer")
        self._p2p_answer_btn.clicked.connect(self._on_p2p_answer)
        self._p2p_close_btn = QPushButton("Disconnect")
        self._p2p_close_btn.clicked.connect(self._on_p2p_close)
        row.addWidget(self._p2p_offer_btn)
        row.addWidget(self._p2p_answer_btn)
        row.addWidget(self._p2p_close_btn)
        layout.addLayout(row)

        control_row = QHBoxLayout()
        control_row.setSpacing(8)
        self._p2p_pending_label = QLabel("Pending controls: 0")
        self._p2p_pending_label.setObjectName("emptyHint")
        self._p2p_approve_btn = QPushButton("Approve input")
        self._p2p_approve_btn.clicked.connect(self._on_p2p_approve)
        self._p2p_deny_btn = QPushButton("Deny input")
        self._p2p_deny_btn.clicked.connect(self._on_p2p_deny)
        control_row.addWidget(self._p2p_pending_label)
        control_row.addWidget(self._p2p_approve_btn)
        control_row.addWidget(self._p2p_deny_btn)
        layout.addLayout(control_row)

        self._p2p_status = QLabel("Status: Disabled")
        self._p2p_status.setObjectName("emptyHint")
        self._p2p_status.setWordWrap(True)
        layout.addWidget(self._p2p_status)

        self._p2p_qr_label = QLabel()
        self._p2p_qr_label.setAlignment(Qt.AlignCenter)
        self._p2p_qr_label.setMinimumHeight(180)
        self._p2p_qr_label.hide()
        layout.addWidget(self._p2p_qr_label)

        self._p2p_text = QPlainTextEdit()
        self._p2p_text.setReadOnly(True)
        self._p2p_text.setMaximumHeight(64)
        self._p2p_text.hide()
        layout.addWidget(self._p2p_text)

        self._layout.addWidget(card)
        self._refresh_p2p_state()

    def _on_p2p_toggled(self, checked: bool) -> None:
        try:
            self._repository.update({"p2p.enabled": bool(checked)})
        except SettingsError as exc:
            self._p2p_status.setText(f"Status: Error — {exc}")
            return
        if not checked:
            get_p2p_service().close()
            self._p2p_qr_label.hide()
            self._p2p_text.hide()
        self._refresh_p2p_state()

    def _refresh_p2p_state(self) -> None:
        enabled = bool(self._repository.get("p2p.enabled", False))
        status = get_p2p_service().status()
        mode = "relay" if status.get("relay") else "direct"
        state = str(status.get("state", "new"))
        pending = int(status.get("pending_controls", 0) or 0)
        self._p2p_enable.setChecked(enabled)
        self._p2p_pending_label.setText(f"Pending controls: {pending}")
        self._p2p_approve_btn.setEnabled(pending > 0)
        self._p2p_deny_btn.setEnabled(pending > 0)
        if not enabled:
            self._p2p_status.setText("Status: Disabled")
        else:
            self._p2p_status.setText(f"Status: {state} ({mode}) — device {status.get('device_id', '')}")

    def _on_p2p_offer(self) -> None:
        result = get_p2p_service().create_offer()
        if not result.get("ok"):
            self._p2p_status.setText(f"Status: {result.get('error', result.get('code'))}")
            return
        payload = str(result.get("payload", ""))
        try:
            import qrcode

            image = qrcode.make(payload)
            buf = io.BytesIO()
            image.save(buf, format="PNG")
            qimage = QImage()
            qimage.loadFromData(buf.getvalue(), "PNG")
            self._p2p_qr_label.setPixmap(
                QPixmap.fromImage(qimage).scaled(220, 220, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
            self._p2p_qr_label.show()
        except Exception as exc:  # noqa: BLE001 - QR is display-only
            self._p2p_qr_label.hide()
            self._p2p_status.setText(f"Status: QR error — {exc}")
        self._p2p_text.setPlainText(payload)
        self._p2p_text.show()
        self._p2p_status.setText("Status: offer ready — share QR/code with phone")

    def _on_p2p_answer(self) -> None:
        text, ok = QInputDialog.getMultiLineText(self, "Maya P2P", "Paste the answer from phone:")
        if not ok or not text.strip():
            return
        result = get_p2p_service().accept_answer(text.strip())
        if result.get("ok"):
            self._p2p_status.setText("Status: connected")
        else:
            self._p2p_status.setText(f"Status: {result.get('error', result.get('code'))}")
        self._refresh_p2p_state()

    def _on_p2p_approve(self) -> None:
        pending = get_p2p_service().pending_controls()
        if not pending:
            self._refresh_p2p_state()
            return
        detail = pending[0].get("details", {})
        preview = json.dumps(detail, ensure_ascii=False)[:400]
        answer = QMessageBox.question(
            self,
            "Maya P2P",
            f"Allow this remote input?\n\n{preview}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        allowed = answer == QMessageBox.StandardButton.Yes
        result = get_p2p_service().approve_next_control(
            confirm=lambda _action, _details: allowed
        )
        if result.get("ok"):
            self._p2p_status.setText("Status: remote input approved")
        else:
            self._p2p_status.setText(f"Status: {result.get('error', result.get('code'))}")
        self._refresh_p2p_state()

    def _on_p2p_deny(self) -> None:
        result = get_p2p_service().deny_next_control()
        if result.get("ok"):
            self._p2p_status.setText("Status: remote input denied")
        else:
            self._p2p_status.setText(f"Status: {result.get('error', result.get('code'))}")
        self._refresh_p2p_state()

    def _on_p2p_close(self) -> None:
        get_p2p_service().close()
        self._p2p_qr_label.hide()
        self._p2p_text.hide()
        self._refresh_p2p_state()

    # -- phone server -------------------------------------------------

    def showEvent(self, event) -> None:  # noqa: N802 - Qt signature
        self._refresh_engine_state()
        self._refresh_cloud_state()
        self._refresh_server_state()
        self._refresh_p2p_state()
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
            self._server_qr_btn.setEnabled(True)
        else:
            self._server_status.setText("Status: Stopped")
            self._server_start_btn.setEnabled(True)
            self._server_stop_btn.setEnabled(False)
            self._server_pin_btn.setEnabled(False)
            self._server_qr_btn.setEnabled(False)

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
        self._server_qr_btn.setEnabled(False)

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
        self._server_qr_btn.setEnabled(True)
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
        self._server_qr_btn.setEnabled(False)

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
        self._server_qr_btn.setEnabled(False)
        self._server_status.setText("Status: Stopping...")
        if svc is not None:
            try:
                svc.stop()
            except Exception:  # noqa: BLE001 - stop must never crash the page
                pass
        self._server = None
        self._server_status.setText("Status: Stopped")
        self._server_pin_label.setText("Pairing PIN: —")
        self._server_qr_label.hide()
        self._server_qr_label.clear()
        self._server_qr_status.setText("")
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

    def _on_server_qr(self) -> None:
        svc = self._server
        if svc is None or not svc.running:
            self._server_qr_status.setText("Start the phone server first.")
            self._server_qr_label.hide()
            return
        try:
            host = lan_ip() or (svc.host or "")
            port = int(svc.bound_port or svc.port)
            laptop_name = socket.gethostname() or "Maya-Laptop"
            payload = svc.pairing.generate_qr(host, port, laptop_name)
            import qrcode
            img = qrcode.make(json.dumps(payload, separators=(",", ":")))
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            qimg = QImage()
            qimg.loadFromData(buf.getvalue(), "PNG")
            pixmap = QPixmap.fromImage(qimg)
            self._server_qr_label.setPixmap(
                pixmap.scaled(220, 220, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
            self._server_qr_label.show()
            self._server_qr_status.setText(
                f"Scan this with the Maya phone app (Pairing → Scan QR). "
                "Valid ~2 min, single use."
            )
        except Exception as exc:  # noqa: BLE001
            self._server_qr_label.hide()
            self._server_qr_status.setText(f"QR error — {exc}")

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
        self._refresh_engine_state()
        self._refresh_cloud_state()
        stored_prompt = str(self._repository.get("cloud.system_prompt", "") or "")
        if self._cloud_prompt_input.toPlainText().strip() != stored_prompt.strip():
            self._cloud_prompt_input.setPlainText(stored_prompt)
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
