"""Phone Remote page — live screen view + input controls + file browser (Phase 12)."""

from __future__ import annotations

import logging
import threading
from pathlib import Path

import requests
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.services.phone_remote_client import get_phone_remote_client
from app.services.server_service import shared_server_service
from app.settings_repository import SettingsRepository

logger = logging.getLogger("maya.ui.phone_remote")


def _describe_remote_error(exc: Exception, host: str | None) -> str:
    """Short, actionable text for phone-side network failures.

    urllib3 renders a connection failure as a paragraph of retry chatter, which
    is useless in the status label.
    """
    target = f"http://{host}:8421" if host else "the phone"

    is_conn = False
    is_timeout = False

    try:
        if isinstance(exc, requests.exceptions.ConnectionError):
            is_conn = True
        if isinstance(exc, requests.exceptions.Timeout):
            is_timeout = True
    except Exception:  # pragma: no cover
        pass
    try:
        import urllib3

        if isinstance(exc, getattr(urllib3.exceptions, "MaxRetryError", ())):
            is_conn = True
        if isinstance(exc, getattr(urllib3.exceptions, "NewConnectionError", ())):
            is_conn = True
        if isinstance(exc, getattr(urllib3.exceptions, "ConnectTimeoutError", ())):
            is_timeout = True
        if isinstance(exc, getattr(urllib3.exceptions, "ReadTimeoutError", ())):
            is_timeout = True
    except Exception:  # pragma: no cover
        pass

    if isinstance(exc, (ConnectionRefusedError, ConnectionResetError, BrokenPipeError)):
        is_conn = True
    if isinstance(exc, TimeoutError):
        is_timeout = True

    text = str(exc).lower()
    if "timed out" in text or "timeout" in text:
        is_timeout = is_timeout or not is_conn
    if (
        "refused" in text
        or "retries exceeded" in text
        or "newconnectionerror" in text
        or "failed to establish" in text
        or "name or service not known" in text
        or "no route to host" in text
    ):
        is_conn = True

    if is_conn:
        return (
            f"No answer from {target} - open the Maya app on the phone and enable "
            "Accessibility + Phone Remote."
        )
    if is_timeout:
        return f"Phone timed out at {target} - check both devices are on the same Wi-Fi."
    return str(exc)


class PhoneRemotePage(QWidget):
    """Phone Remote page: live phone screen + input controls + file browser."""

    status_changed = Signal(str, str)  # text, state
    server_started = Signal()  # background start finished, queued to the GUI thread

    def __init__(
        self,
        parent: QWidget | None = None,
        repository: SettingsRepository | None = None,
    ) -> None:
        super().__init__(parent)
        self._repository = repository or SettingsRepository()
        self._client = None
        self._confirm_token: str | None = None
        self._confirm_timer: QTimer | None = None
        self._phone_host: str | None = None
        self._pending_download: str | None = None
        self._current_remote_path: str | None = None
        self._allowed_roots: list[str] = []
        # Drag tracking: press position is kept so release can decide
        # between a tap (click) and a drag (swipe).
        self._press_pos: tuple[float, float] | None = None
        self._drag_pos: tuple[float, float] | None = None

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
        # A long device/IP hint must not widen the whole page.
        self._session_status.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )
        session_layout.addWidget(self._session_status, 1)

        self._start_server_btn = QPushButton("Start Server")
        self._start_server_btn.setObjectName("secondaryButton")
        self._start_server_btn.setFixedHeight(36)
        self._start_server_btn.setVisible(False)
        self._start_server_btn.clicked.connect(self._on_start_server)
        session_layout.addWidget(self._start_server_btn)

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
        # A splitter keeps both panels usable: the page can be narrower than
        # the sum of the two columns, and the phone-files panel is never cut
        # off at the right edge.
        content = QSplitter(Qt.Orientation.Horizontal)
        content.setChildrenCollapsible(False)
        content.setHandleWidth(12)

        # Left: Screen view
        screen_section = QVBoxLayout()
        screen_section.setContentsMargins(0, 0, 0, 0)
        screen_section.setSpacing(8)

        screen_label = QLabel("Phone Screen")
        screen_label.setObjectName("sectionTitle")
        screen_section.addWidget(screen_label)

        self._screen_scroll = QScrollArea()
        self._screen_scroll.setWidgetResizable(True)
        self._screen_scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._screen_scroll.setMinimumHeight(320)

        self._screen_label = QLabel("No active session")
        self._screen_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._screen_label.setObjectName("screenPlaceholder")
        self._screen_label.setMinimumSize(240, 420)
        self._screen_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._screen_scroll.setWidget(self._screen_label)

        # Mouse tracking for input
        self._screen_label.setMouseTracking(True)
        self._screen_label.mousePressEvent = self._on_screen_press
        self._screen_label.mouseMoveEvent = self._on_screen_move
        self._screen_label.mouseReleaseEvent = self._on_screen_release
        self._screen_label.wheelEvent = self._on_screen_wheel

        screen_section.addWidget(self._screen_scroll, 1)

        # On-screen keyboard / key buttons (2 rows so the row can shrink)
        keys_grid = QGridLayout()
        keys_grid.setContentsMargins(0, 0, 0, 0)
        keys_grid.setHorizontalSpacing(8)
        keys_grid.setVerticalSpacing(8)
        key_defs = [
            ("Back", "back"), ("Home", "home"), ("Recents", "recents"),
            ("Enter", "enter"), ("Esc", "escape"), ("Tab", "tab"),
            ("↑", "up"), ("↓", "down"), ("←", "left"), ("→", "right"),
            ("Space", "space"), ("Del", "delete"),
        ]
        for index, (key_text, key_name) in enumerate(key_defs):
            btn = QPushButton(key_text)
            btn.setFixedHeight(36)
            btn.clicked.connect(lambda _checked=False, k=key_name: self._send_key(k))
            keys_grid.addWidget(btn, index // 6, index % 6)
        for column in range(6):
            keys_grid.setColumnStretch(column, 1)
        screen_section.addLayout(keys_grid)

        # Type text input
        type_row = QHBoxLayout()
        type_row.setSpacing(8)
        self._type_input = QPushButton("Type Text...")
        self._type_input.setFixedHeight(36)
        self._type_input.clicked.connect(self._on_type_text)
        type_row.addWidget(self._type_input)
        screen_section.addLayout(type_row)

        screen_container = QWidget()
        screen_container.setLayout(screen_section)
        screen_container.setMinimumWidth(300)
        content.addWidget(screen_container)

        # Right: File Browser
        file_section = QVBoxLayout()
        file_section.setContentsMargins(0, 0, 0, 0)
        file_section.setSpacing(8)

        file_label = QLabel("Phone Files")
        file_label.setObjectName("sectionTitle")
        file_section.addWidget(file_label)

        self._file_path_label = QLabel("/")
        self._file_path_label.setObjectName("cardSubtitle")
        # On its own row it gets the panel width; deep phone paths must not
        # widen the panel, so the text may clip and the tooltip keeps it whole.
        self._file_path_label.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )
        self._file_path_label.setToolTip("/")
        file_section.addWidget(self._file_path_label)

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
        file_section.addLayout(file_toolbar)

        self._file_tree = QTreeWidget()
        self._file_tree.setHeaderLabels(["Name", "Size", "Type"])
        self._file_tree.setColumnWidth(0, 200)
        self._file_tree.setColumnWidth(1, 80)
        self._file_tree.itemDoubleClicked.connect(self._on_file_double_click)
        self._file_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._file_tree.customContextMenuRequested.connect(self._on_file_context_menu)
        file_section.addWidget(self._file_tree, 1)

        files_container = QWidget()
        files_container.setLayout(file_section)
        content.addWidget(files_container)

        content.setStretchFactor(0, 3)
        content.setStretchFactor(1, 2)
        content.setSizes([640, 360])

        layout.addWidget(content, 1)

    def _connect_signals(self) -> None:
        self.server_started.connect(self._check_phone_connection)

    def showEvent(self, event) -> None:  # noqa: N802 - Qt signature
        # The phone server may have been started (or stopped) while this page
        # was hidden, so refresh the session banner every time it is shown.
        super().showEvent(event)
        self._check_phone_connection()

    def _set_status_text(self, text: str) -> None:
        self._session_status.setText(text)
        self._session_status.setToolTip(text)

    def _check_phone_connection(self) -> None:
        """Check if a phone is paired and get its IP."""
        service = shared_server_service()
        if not service.running:
            self._set_status_text("Phone server not running")
            self._start_server_btn.setEnabled(True)
            self._start_server_btn.setVisible(True)
            self._start_btn.setEnabled(False)
            return

        self._start_server_btn.setVisible(False)
        tokens = service.app.state.tokens
        devices = tokens.list_active()
        if not devices:
            self._set_status_text("No phone paired")
            self._start_btn.setEnabled(False)
            return

        device = max(devices, key=lambda d: getattr(d, "last_seen", 0) or 0)
        host = (getattr(device, "last_ip", "") or "").strip()
        self._phone_host = host or None
        if not host:
            self._set_status_text(
                f"{device.name}: phone IP unknown. Connect phone to laptop once."
            )
            self._start_btn.setEnabled(False)
            return
        self._set_status_text(f"Ready: {device.name} ({host})")
        self._start_btn.setEnabled(True)

    def _on_start_server(self) -> None:
        """Start the shared phone server, then refresh the session banner."""
        self._start_server_btn.setEnabled(False)
        self._set_status_text("Starting phone server…")
        self.status_changed.emit("Starting phone server…", "warn")

        def _worker():
            try:
                shared_server_service().start()
            except Exception as exc:  # noqa: BLE001 - report, never crash the UI
                # Widget state is refreshed on the GUI thread by server_started.
                logger.error("Phone server start failed: %s", exc)
                self.status_changed.emit(f"Phone server failed: {exc}", "error")
                self.server_started.emit()
                return
            self.status_changed.emit("Phone server running", "ok")
            self.server_started.emit()

        threading.Thread(target=_worker, name="maya-server-start", daemon=True).start()

    def _on_start_session(self) -> None:
        """Start a remote session on the phone."""
        if not self._phone_host:
            self._check_phone_connection()
            if not self._phone_host:
                return

        self._start_btn.setEnabled(False)
        self.status_changed.emit("Starting session…", "warn")

        def _worker():
            try:
                self._client = get_phone_remote_client(
                    on_frame=self._on_frame_received,
                    on_error=self._on_client_error,
                )
                result = self._client.start_session(self._phone_host)
                if result.get("status") == "pending":
                    self._confirm_token = result.get("request_id")
                    self._show_confirm_dialog(int(result.get("expires_in", 60)))
                elif result.get("status") == "started":
                    self._on_session_started()
                else:
                    raise RuntimeError(result.get("description") or result.get("detail") or "Unknown response")
            except Exception as e:  # noqa: BLE001 - report, never crash the UI
                friendly = _describe_remote_error(e, self._phone_host)
                logger.error("Start session failed: %s", friendly)
                self.status_changed.emit(friendly, "error")
                self._start_btn.setEnabled(True)

        threading.Thread(target=_worker, daemon=True).start()

    def _show_confirm_dialog(self, expires_in: int = 60) -> None:
        """Show the confirmation dialog with countdown."""
        self._confirm_frame.setVisible(True)
        self._confirm_label.setText("Waiting for phone approval...\nPhone-la 'Allow remote control' accept pannunga.")
        self._confirm_remaining = max(1, int(expires_in))
        self._confirm_timer_label.setText(f"Expires in {self._confirm_remaining}s")
        self._allow_btn.setEnabled(False)
        self._deny_btn.setEnabled(True)
        if self._confirm_timer:
            self._confirm_timer.stop()
        self._confirm_timer = QTimer(self)
        self._confirm_timer.timeout.connect(self._update_confirm_timer)
        self._confirm_timer.start(1000)

    def _update_confirm_timer(self) -> None:
        self._confirm_remaining -= 1
        if self._confirm_remaining <= 0:
            self._on_deny_session()
            return
        self._confirm_timer_label.setText(f"Expires in {self._confirm_remaining}s")
        # Poll phone for approval
        if self._confirm_token and self._phone_host and self._client:
            try:
                status = self._client.get_request_status(self._phone_host, self._confirm_token)
                st = status.get("status")
                if st == "started":
                    self._on_session_started()
                elif st in {"denied", "expired", "not_found", "consumed"}:
                    self.status_changed.emit(f"Session {st}", "warn")
                    self._hide_confirm_dialog()
                    self._start_btn.setEnabled(True)
            except Exception as e:
                logger.debug("poll request status failed: %s", e)

    def _on_allow_session(self) -> None:
        # Approval must happen on the phone; laptop only polls.
        self.status_changed.emit("Phone-la Allow tap pannunga", "warn")

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
        self._allow_btn.setEnabled(True)
        self._deny_btn.setEnabled(True)

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
        self._client = self._client or get_phone_remote_client()
        self._client.stop_session()
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
        text = error or ""
        lower = text.lower()
        if "retries exceeded" in lower or "newconnectionerror" in lower or "refused" in lower:
            text = "No answer from the phone - open the Maya app on the phone and enable Accessibility + Phone Remote."
        logger.error("Phone remote client error: %s", text)
        self.status_changed.emit(f"Error: {text}", "error")

    # --- Screen Input Handlers ---
    def _normalized_pos(self, event) -> tuple[float, float]:
        """Map a widget-space mouse position to normalized screen coords (0.0-1.0)."""
        pos = event.position()
        return (
            min(max(pos.x() / self._screen_label.width(), 0.0), 1.0),
            min(max(pos.y() / self._screen_label.height(), 0.0), 1.0),
        )

    def _on_screen_press(self, event) -> None:
        if not self._client or not self._client.is_active:
            return
        self._press_pos = self._normalized_pos(event)
        self._drag_pos = self._press_pos

    def _on_screen_move(self, event) -> None:
        if not self._client or not self._client.is_active:
            return
        if self._press_pos is None:
            return
        # Button is held: remember the latest point, the swipe is sent on release.
        self._drag_pos = self._normalized_pos(event)

    def _on_screen_release(self, event) -> None:
        if not self._client or not self._client.is_active:
            self._press_pos = None
            self._drag_pos = None
            return

        start = self._press_pos
        end = self._normalized_pos(event) if event is not None else self._drag_pos
        self._press_pos = None
        self._drag_pos = None
        if start is None or end is None:
            return

        dx = end[0] - start[0]
        dy = end[1] - start[1]
        if (dx * dx + dy * dy) ** 0.5 < 0.02:
            # Tap: click at the release point.
            self._client.send_input(
                [{"type": "click", "x": end[0], "y": end[1], "button": "left"}]
            )
        else:
            # Drag: swipe from press point to release point.
            self._client.send_input(
                [
                    {
                        "type": "swipe",
                        "x": start[0],
                        "y": start[1],
                        "x2": end[0],
                        "y2": end[1],
                    }
                ]
            )

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
        self._file_path_label.setToolTip(path)
        self._file_tree.clear()

        def _worker():
            try:
                result = self._client.list_files(path)
                entries = result.get("entries", [])
                self._populate_file_tree(entries)
            except Exception as e:
                friendly = _describe_remote_error(e, self._phone_host)
                logger.error("Failed to load files: %s", friendly)
                self.status_changed.emit(f"File error: {friendly}", "error")

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
                friendly = _describe_remote_error(e, self._phone_host)
                logger.error("Upload failed: %s", friendly)
                self.status_changed.emit(f"Upload failed: {friendly}", "error")

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
                friendly = _describe_remote_error(e, self._phone_host)
                logger.error("Download failed: %s", friendly)
                self.status_changed.emit(f"Download failed: {friendly}", "error")

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