"""Phone Remote page — live screen view + input controls + file browser (Phase 12)."""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.services.phone_remote_client import get_phone_remote_client
from app.services.server_service import shared_server_service
from app.settings_repository import SettingsRepository

logger = logging.getLogger("maya.ui.phone_remote")


class PhoneRemotePage(QWidget):
    """Phone Remote page: live phone screen + input controls + file browser."""

    status_changed = Signal(str, str)  # text, state

    def __init__(
        self,
        parent: QWidget | None = None,
        repository: SettingsRepository | None = None,
    ) -> None:
        super().__init__(parent)
        self._repository = repository or SettingsRepository()
        self._client: get_phone_remote_client | None = None
        self._confirm_token: str | None = None
        self._confirm_timer: QTimer | None = None
        self._phone_host: str | None = None
        self._pending_download: str | None = None
        self._current_remote_path: str | None = None
        self._allowed_roots: list[str] = []

        self._build_ui()
        self._connect_signals()

        # Start with checking if phone is connected
        self._check_phone_connection()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # --- Session Control ---
        session_frame = QFrame()
        session_frame.setObjectName("card")
        session_layout = QHBoxLayout(session_frame)
        session_layout.setContentsMargins(16, 12, 16, 12)
        session_layout.setSpacing(12)

        self._session_status = QLabel("No session")
        self._session_status.setObjectName("cardTitle")
        session_layout.addWidget(self._session_status)

        session_layout.addStretch(1)

        self._start_btn = QPushButton("Start Session")
        self._start_btn.setObjectName("primaryButton")
        self._start_btn.setFixedHeight(36)
        self._start_btn.clicked.connect(self._on_start_session)
        session_layout.addWidget(self._start_btn)

        self._stop_btn = QPushButton("Stop Session")
        self._stop_btn.setObjectName("dangerButton")
        self._stop_btn.setFixedHeight(36)
        self._stop_btn.setVisible(False)
        self._stop_btn.clicked.connect(self._on_stop_session)
        session_layout.addWidget(self._stop_btn)

        layout.addWidget(session_frame)

        # --- Confirm Dialog (hidden by default) ---
        self._confirm_frame = QFrame()
        self._confirm_frame.setObjectName("card")
        self._confirm_frame.setVisible(False)
        confirm_layout = QVBoxLayout(self._confirm_frame)
        confirm_layout.setContentsMargins(16, 12, 16, 12)
        confirm_layout.setSpacing(8)

        self._confirm_label = QLabel("Phone is asking for permission to allow remote control.")
        self._confirm_label.setObjectName("cardTitle")
        self._confirm_label.setWordWrap(True)
        confirm_layout.addWidget(self._confirm_label)

        self._confirm_timer_label = QLabel("Expires in 60s")
        self._confirm_timer_label.setObjectName("cardSubtitle")
        confirm_layout.addWidget(self._confirm_timer_label)

        confirm_btns = QHBoxLayout()
        confirm_btns.setSpacing(8)
        self._allow_btn = QPushButton("Allow")
        self._allow_btn.setObjectName("primaryButton")
        self._allow_btn.setFixedHeight(36)
        self._allow_btn.clicked.connect(self._on_allow_session)
        confirm_btns.addWidget(self._allow_btn)

        self._deny_btn = QPushButton("Deny")
        self._deny_btn.setObjectName("secondaryButton")
        self._deny_btn.setFixedHeight(36)
        self._deny_btn.clicked.connect(self._on_deny_session)
        confirm_btns.addWidget(self._deny_btn)
        confirm_layout.addLayout(confirm_btns)

        layout.addWidget(self._confirm_frame)

        # --- Main Content (Screen + Controls) ---
        content = QHBoxLayout()
        content.setSpacing(16)

        # Left: Screen view
        screen_section = QVBoxLayout()
        screen_section.setSpacing(8)

        screen_label = QLabel("Phone Screen")
        screen_label.setObjectName("sectionTitle")
        screen_section.addWidget(screen_label)

        self._screen_scroll = QScrollArea()
        self._screen_scroll.setWidgetResizable(True)
        self._screen_scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._screen_scroll.setMinimumHeight(400)

        self._screen_label = QLabel("No active session")
        self._screen_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._screen_label.setObjectName("screenPlaceholder")
        self._screen_label.setMinimumSize(320, 560)
        self._screen_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._screen_scroll.setWidget(self._screen_label)

        # Mouse tracking for input
        self._screen_label.setMouseTracking(True)
        self._screen_label.mousePressEvent = self._on_screen_press
        self._screen_label.mouseMoveEvent = self._on_screen_move
        self._screen_label.mouseReleaseEvent = self._on_screen_release
        self._screen_label.wheelEvent = self._on_screen_wheel

        screen_section.addWidget(self._screen_scroll, 1)

        # On-screen keyboard / key buttons
        keys_row = QHBoxLayout()
        keys_row.setSpacing(8)
        for key_text, key_name in [
            ("Back", "back"), ("Home", "home"), ("Recents", "recents"),
            ("Enter", "enter"), ("Esc", "escape"), ("Tab", "tab"),
            ("↑", "up"), ("↓", "down"), ("←", "left"), ("→", "right"),
            ("Space", "space"), ("Del", "delete"),
        ]:
            btn = QPushButton(key_text)
            btn.setFixedHeight(36)
            btn.clicked.connect(lambda _checked=False, k=key_name: self._send_key(k))
            keys_row.addWidget(btn)
        screen_section.addLayout(keys_row)

        # Type text input
        type_row = QHBoxLayout()
        type_row.setSpacing(8)
        self._type_input = QPushButton("Type Text...")
        self._type_input.setFixedHeight(36)
        self._type_input.clicked.connect(self._on_type_text)
        type_row.addWidget(self._type_input)
        screen_section.addLayout(type_row)

        content.addLayout(screen_section, 2)

        # Right: File Browser
        file_section = QVBoxLayout()
        file_section.setSpacing(8)

        file_label = QLabel("Phone Files")
        file_label.setObjectName("sectionTitle")
        file_section.addWidget(file_label)

        file_toolbar = QHBoxLayout()
        file_toolbar.setSpacing(8)
        self._file_up_btn = QPushButton("↑ Up")
        self._file_up_btn.setFixedHeight(32)
        self._file_up_btn.clicked.connect(self._on_file_up)
        self._file_up_btn.setEnabled(False)
        file_toolbar.addWidget(self._file_up_btn)

        self._file_refresh_btn = QPushButton("↻ Refresh")
        self._file_refresh_btn.setFixedHeight(32)
        self._file_refresh_btn.clicked.connect(self._on_file_refresh)
        self._file_refresh_btn.setEnabled(False)
        file_toolbar.addWidget(self._file_refresh_btn)

        self._file_upload_btn = QPushButton("↑ Upload")
        self._file_upload_btn.setFixedHeight(32)
        self._file_upload_btn.clicked.connect(self._on_file_upload)
        self._file_upload_btn.setEnabled(False)
        file_toolbar.addWidget(self._file_upload_btn)

        file_toolbar.addStretch(1)
        self._file_path_label = QLabel("/")
        self._file_path_label.setObjectName("cardSubtitle")
        file_toolbar.addWidget(self._file_path_label)
        file_section.addLayout(file_toolbar)

        self._file_tree = QTreeWidget()
        self._file_tree.setHeaderLabels(["Name", "Size", "Type"])
        self._file_tree.setColumnWidth(0, 200)
        self._file_tree.setColumnWidth(1, 80)
        self._file_tree.itemDoubleClicked.connect(self._on_file_double_click)
        self._file_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._file_tree.customContextMenuRequested.connect(self._on_file_context_menu)
        file_section.addWidget(self._file_tree, 1)

        content.addLayout(file_section, 1)

        layout.addLayout(content, 1)

    def _connect_signals(self) -> None:
        pass

    def _check_phone_connection(self) -> None:
        """Check if a phone is paired and get its IP."""
        service = shared_server_service()
        if not service.running:
            self._session_status.setText("Phone server not running")
            self._start_btn.setEnabled(False)
            return

        tokens = service.app.state.tokens
        devices = tokens.list_active()
        if not devices:
            self._session_status.setText("No phone paired")
            self._start_btn.setEnabled(False)
            return

        # Use the most recently seen device
        device = max(devices, key=lambda d: d.last_seen)
        self._phone_host = device.host if hasattr(device, 'host') else "127.0.0.1"
        self._session_status.setText(f"Ready: {device.name} ({self._phone_host})")
        self._start_btn.setEnabled(True)

    def _on_start_session(self) -> None:
        """Start a remote session on the phone."""
        if not self._phone_host:
            return

        self._start_btn.setEnabled(False)
        self.status_changed.emit("Starting session…", "warn")

        def _worker():
            try:
                client = get_phone_remote_client(
                    on_frame=self._on_frame_received,
                    on_error=self._on_client_error,
                )
                result = client.start_session(self._phone_host)
                if result.get("status") == "needs_confirmation":
                    self._confirm_token = result["confirm_token"]
                    self._show_confirm_dialog()
                elif result.get("status") == "started":
                    self._on_session_started()
                else:
                    raise RuntimeError(result.get("detail", "Unknown response"))
            except Exception as e:
                logger.error("Start session failed: %s", e)
                self.status_changed.emit(f"Failed: {e}", "error")
                self._start_btn.setEnabled(True)

        threading.Thread(target=_worker, daemon=True).start()

    def _show_confirm_dialog(self) -> None:
        """Show the confirmation dialog with countdown."""
        self._confirm_frame.setVisible(True)
        self._confirm_label.setText("Phone is asking for permission to allow remote control.\nTap 'Allow' on your phone.")
        self._confirm_timer_label.setText("Expires in 60s")

        self._confirm_timer = QTimer()
        self._confirm_timer.timeout.connect(self._update_confirm_timer)
        self._confirm_timer.start(1000)
        self._confirm_remaining = 60

    def _update_confirm_timer(self) -> None:
        self._confirm_remaining -= 1
        if self._confirm_remaining <= 0:
            self._on_deny_session()
        else:
            self._confirm_timer_label.setText(f"Expires in {self._confirm_remaining}s")

    def _on_allow_session(self) -> None:
        """User clicked Allow on laptop (phone user must also allow)."""
        if not self._confirm_token or not self._phone_host:
            return

        self._allow_btn.setEnabled(False)
        self._deny_btn.setEnabled(False)

        def _worker():
            try:
                client = get_phone_remote_client(
                    on_frame=self._on_frame_received,
                    on_error=self._on_client_error,
                )
                client.confirm_session(self._phone_host, self._confirm_token)
                self._on_session_started()
            except Exception as e:
                logger.error("Confirm session failed: %s", e)
                self.status_changed.emit(f"Failed: {e}", "error")
                self._hide_confirm_dialog()
                self._start_btn.setEnabled(True)

        threading.Thread(target=_worker, daemon=True).start()

    def _on_deny_session(self) -> None:
        """User denied or timer expired."""
        self._hide_confirm_dialog()
        self.status_changed.emit("Session denied", "warn")
        self._start_btn.setEnabled(True)

    def _hide_confirm_dialog(self) -> None:
        if self._confirm_timer:
            self._confirm_timer.stop()
            self._confirm_timer = None
        self._confirm_frame.setVisible(False)
        self._confirm_token = None

    def _on_session_started(self) -> None:
        """Session is active, update UI."""
        self._hide_confirm_dialog()
        self._start_btn.setVisible(False)
        self._stop_btn.setVisible(True)
        self._file_up_btn.setEnabled(True)
        self._file_refresh_btn.setEnabled(True)
        self._file_upload_btn.setEnabled(True)
        self._session_status.setText("Session active — Phone screen streaming")
        self.status_changed.emit("Session active", "ok")
        self._load_file_tree("/")

    def _on_stop_session(self) -> None:
        """Stop the remote session."""
        client = get_phone_remote_client()
        client.stop_session()
        self._start_btn.setVisible(True)
        self._stop_btn.setVisible(False)
        self._file_up_btn.setEnabled(False)
        self._file_refresh_btn.setEnabled(False)
        self._file_upload_btn.setEnabled(False)
        self._session_status.setText("Session stopped")
        self._screen_label.setPixmap(QPixmap())
        self._screen_label.setText("No active session")
        self._file_tree.clear()
        self.status_changed.emit("Session stopped", "neutral")

    def _on_frame_received(self, frame_bytes: bytes) -> None:
        """Received a JPEG frame from phone."""
        try:
            image = QImage.fromData(frame_bytes)
            if not image.isNull():
                pixmap = QPixmap.fromImage(image)
                # Scale to fit label while maintaining aspect ratio
                scaled = pixmap.scaled(
                    self._screen_label.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                self._screen_label.setPixmap(scaled)
        except Exception as e:
            logger.warning("Failed to decode frame: %s", e)

    def _on_client_error(self, error: str) -> None:
        """Client reported an error."""
        logger.error("Phone remote client error: %s", error)
        self.status_changed.emit(f"Error: {error}", "error")

    # --- Screen Input Handlers ---
    def _on_screen_press(self, event) -> None:
        if not self._client or not self._client.is_active:
            return
        pos = event.position()
        x = pos.x() / self._screen_label.width()
        y = pos.y() / self._screen_label.height()
        self._client.send_input([{"type": "move", "x": x, "y": y}, {"type": "click", "button": "left"}])

    def _on_screen_move(self, event) -> None:
        if not self._client or not self._client.is_active:
            return
        pos = event.position()
        x = pos.x() / self._screen_label.width()
        y = pos.y() / self._screen_label.height()
        self._client.send_ws_input([{"type": "move", "x": x, "y": y}])

    def _on_screen_release(self, event) -> None:
        pass

    def _on_screen_wheel(self, event) -> None:
        if not self._client or not self._client.is_active:
            return
        delta = event.angleDelta().y()
        self._client.send_input([{"type": "scroll", "dy": -1 if delta > 0 else 1}])

    def _send_key(self, key: str) -> None:
        if not self._client or not self._client.is_active:
            return
        self._client.send_input([{"type": "key", "key": key}])

    def _on_type_text(self) -> None:
        from PySide6.QtWidgets import QInputDialog
        text, ok = QInputDialog.getText(self, "Type Text", "Enter text to send:")
        if ok and text and self._client and self._client.is_active:
            self._client.send_input([{"type": "text", "text": text}])

    # --- File Browser ---
    def _load_file_tree(self, path: str) -> None:
        if not self._client or not self._client.is_active:
            return

        self._current_remote_path = path
        self._file_path_label.setText(path)
        self._file_tree.clear()

        def _worker():
            try:
                result = self._client.list_files(path)
                entries = result.get("entries", [])
                self._populate_file_tree(entries)
            except Exception as e:
                logger.error("Failed to load files: %s", e)
                self.status_changed.emit(f"File error: {e}", "error")

        threading.Thread(target=_worker, daemon=True).start()

    def _populate_file_tree(self, entries: list[dict]) -> None:
        self._file_tree.clear()
        for entry in entries:
            item = QTreeWidgetItem()
            name = entry.get("name", "?")
            is_dir = entry.get("is_dir", False)
            size = entry.get("size")
            item.setText(0, f"{'📁 ' if is_dir else '📄 '}{name}")
            item.setText(1, f"{size} B" if size else "—")
            item.setText(2, "Folder" if is_dir else "File")
            item.setData(0, Qt.ItemDataRole.UserRole, entry.get("path", name))
            self._file_tree.addTopLevelItem(item)
        self._file_tree.resizeColumnToContents(0)

    def _on_file_double_click(self, item: QTreeWidgetItem, column: int) -> None:
        path = item.data(0, Qt.ItemDataRole.UserRole)
        entry_type = item.text(2)
        if entry_type == "Folder":
            self._load_file_tree(path)
        else:
            self._download_file(path)

    def _on_file_up(self) -> None:
        if not self._current_remote_path:
            return
        parent = str(Path(self._current_remote_path).parent)
        if parent == ".":
            parent = "/"
        self._load_file_tree(parent)

    def _on_file_refresh(self) -> None:
        if self._current_remote_path:
            self._load_file_tree(self._current_remote_path)

    def _on_file_upload(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(self, "Select file to upload")
        if not file_path:
            return
        if not self._current_remote_path:
            return

        def _worker():
            try:
                result = self._client.upload_file(file_path, self._current_remote_path)
                self.status_changed.emit(f"Uploaded: {result.get('size', 0)} bytes", "ok")
                self._load_file_tree(self._current_remote_path)
            except Exception as e:
                logger.error("Upload failed: %s", e)
                self.status_changed.emit(f"Upload failed: {e}", "error")

        threading.Thread(target=_worker, daemon=True).start()

    def _download_file(self, remote_path: str) -> None:
        local_name = Path(remote_path).name
        local_path, _ = QFileDialog.getSaveFileName(self, "Save file as", local_name)
        if not local_path:
            return

        def _worker():
            try:
                self._client.download_file(remote_path, local_path)
                self.status_changed.emit(f"Downloaded: {local_path}", "ok")
            except Exception as e:
                logger.error("Download failed: %s", e)
                self.status_changed.emit(f"Download failed: {e}", "error")

        threading.Thread(target=_worker, daemon=True).start()

    def _on_file_context_menu(self, pos) -> None:
        from PySide6.QtWidgets import QMenu
        item = self._file_tree.itemAt(pos)
        if not item:
            return
        menu = QMenu(self)
        path = item.data(0, Qt.ItemDataRole.UserRole)
        entry_type = item.text(2)

        if entry_type == "File":
            download_action = menu.addAction("Download")
            download_action.triggered.connect(lambda: self._download_file(path))
        else:
            open_action = menu.addAction("Open")
            open_action.triggered.connect(lambda: self._load_file_tree(path))

        menu.exec(self._file_tree.mapToGlobal(pos))