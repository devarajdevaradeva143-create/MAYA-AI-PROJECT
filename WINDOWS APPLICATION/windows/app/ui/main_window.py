"""Main window: sidebar + header + stacked pages (plan section 11.1)."""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.main import APP_TITLE, DEFAULT_HEIGHT, DEFAULT_WIDTH
from app.services.chat_service import ChatService
from app.services.control_service import ControlService
from app.services.engine_service import EngineAdapter
from app.services.security_service import SecurityService
from app.services.voice_service import VoiceAdapter
from app.services.wake_service import WakeAdapter
from app.settings_repository import SettingsRepository
from app.ui.pages.chat_page import ChatPage
from app.ui.pages.monitor_page import MonitorPage
from app.ui.pages.pc_page import PCPage
from app.ui.pages.phone_remote_page import PhoneRemotePage
from app.ui.pages.security_page import SecurityPage
from app.ui.pages.settings_page import SettingsPage
from app.ui.pages.teacher_page import TeacherPage
from app.ui.pages.voice_page import VoicePage
from app.ui.sidebar import NAV_ITEMS, Sidebar
from app.ui.theme import DEFAULT_MODE, HEADER_HEIGHT, ThemeManager
from app.ui.widgets.empty_state import PlaceholderPage

MIN_WIDTH = 980
MIN_HEIGHT = 640

PAGE_HINTS: dict[str, tuple[str, str]] = {
    "chat": ("💬", "Streaming chat with Maya and the English Teacher arrives in Phase 3."),
    "voice": ("🎤", "Push-to-talk, TTS and wake words arrive in Phase 4."),
    "pc": ("🖥️", "Apps, files, commands and permissions arrive in Phase 5."),
    "monitor": ("📊", "CPU / RAM / GPU / battery cards arrive in Phase 6."),
    "phone_remote": ("📱", "Control paired phone: screen view, input, files arrive in Phase 12."),
    "teacher": ("📚", "Grammar, vocabulary and pronunciation coaching arrive in Phase 7."),
    "security": ("🔒", "PIN lock, Windows Hello and the watchdog arrive in Phase 8."),
}


def _make_intelligence_bridge():
    """Best-effort: load the MAYA INTELLIGENCE bridge; None on failure."""
    try:
        from custom.intelligence_bridge import IntelligenceBridge

        bridge = IntelligenceBridge()
        return bridge if bridge.available else None
    except Exception:
        return None


class MayaMainWindow(QMainWindow):
    """Seven-section shell; pages replace their placeholders phase by phase."""

    page_changed = Signal(str)

    def __init__(
        self,
        repository: SettingsRepository | None = None,
        theme: ThemeManager | None = None,
        chat: ChatService | None = None,
        security: SecurityService | None = None,
        tray_available: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._repository = repository or SettingsRepository()
        self._chat = chat or ChatService(
            EngineAdapter(), intelligence=_make_intelligence_bridge(),
        )
        self._voice_adapter = VoiceAdapter()
        self._wake_adapter = WakeAdapter()
        self._control = ControlService()
        self._security = security or SecurityService()
        self._tray_available = bool(tray_available)
        app = QApplication.instance()
        if theme is None:
            mode = str(self._repository.get("ui.theme", DEFAULT_MODE))
            theme = ThemeManager(app, mode) if app is not None else None
        self._theme = theme

        self.setWindowTitle(APP_TITLE)
        width = int(self._repository.get("ui.window_width", DEFAULT_WIDTH))
        height = int(self._repository.get("ui.window_height", DEFAULT_HEIGHT))
        self.resize(width, height)
        self.setMinimumSize(MIN_WIDTH, MIN_HEIGHT)

        central = QWidget()
        central.setObjectName("central")
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.sidebar = Sidebar()

        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)
        self._header = self._build_header()

        self.stack = QStackedWidget()
        self.stack.setObjectName("pages")

        right.addWidget(self._header)
        right.addWidget(self.stack, 1)

        root.addWidget(self.sidebar)
        root.addLayout(right, 1)
        self.setCentralWidget(central)

        self._pages: dict[str, int] = {}
        self._titles = {key: label for key, _icon, label in NAV_ITEMS}
        self.set_status("Connecting…", "neutral")

        self.sidebar.navigate.connect(self.navigate)
        self.navigate("chat")

    # -- pages --------------------------------------------------------

    def _build_header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("header")
        header.setFixedHeight(HEADER_HEIGHT)

        layout = QHBoxLayout(header)
        layout.setContentsMargins(24, 0, 24, 0)
        layout.setSpacing(8)

        self._title_label = QLabel("Chat")
        self._title_label.setObjectName("pageTitle")

        self._status_label = QLabel("Starting…")
        self._status_label.setObjectName("statusChip")
        self._status_label.setProperty("state", "neutral")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_label.setFixedHeight(28)

        gear = QPushButton("⚙")
        gear.setObjectName("iconButton")
        gear.setToolTip("Settings")
        gear.setCursor(Qt.CursorShape.PointingHandCursor)
        gear.setFixedSize(36, 36)
        gear.clicked.connect(lambda: self.navigate("settings"))

        layout.addWidget(self._title_label)
        layout.addStretch(1)
        layout.addWidget(self._status_label)
        layout.addWidget(gear)
        return header

    def _create_page(self, key: str) -> QWidget:
        """Build (and wire) one page on demand so startup stays fast."""
        icon = ""
        label = ""
        for k, ic, lab in NAV_ITEMS:
            if k == key:
                icon, label = ic, lab
                break

        if key == "chat":
            page = ChatPage(self._chat, self._chat.engine)
            page.engine_status.connect(self.set_status)
        elif key == "settings":
            page = SettingsPage(self._repository, theme=self._theme)
            page.theme_changed.connect(self._on_theme_changed)
        elif key == "voice":
            page = VoicePage(
                voice=self._voice_adapter,
                wake=self._wake_adapter,
                chat=self._chat,
                repository=self._repository,
            )
        elif key == "pc":
            page = PCPage(control=self._control)
        elif key == "monitor":
            page = MonitorPage()
        elif key == "phone_remote":
            page = PhoneRemotePage(repository=self._repository)
            page.status_changed.connect(self.set_status)
        elif key == "teacher":
            page = TeacherPage(voice=self._voice_adapter)
        elif key == "security":
            page = SecurityPage(security=self._security)
        else:
            hint = PAGE_HINTS.get(key, ("", ""))[1]
            page = PlaceholderPage(icon, label, hint)
        return page

    def _ensure_page(self, key: str) -> int | None:
        if key not in self._pages:
            page = self._create_page(key)
            self._pages[key] = self.stack.addWidget(page)
        return self._pages.get(key)

    # -- tray behaviour ------------------------------------------------
    def closeEvent(self, event) -> None:  # noqa: N802 - Qt signature
        if self._tray_available and bool(self._repository.get("ui.close_to_tray", True)):
            event.ignore()
            self.hide()
            return
        event.accept()

    def changeEvent(self, event) -> None:  # noqa: N802 - Qt signature
        if (
            event.type() == QEvent.Type.WindowStateChange
            and self.isMinimized()
            and self._tray_available
            and bool(self._repository.get("ui.minimize_to_tray", True))
        ):
            event.ignore()
            self.hide()
            return
        super().changeEvent(event)

    def navigate(self, key: str) -> None:
        index = self._ensure_page(key)
        if index is None:
            return
        self.stack.setCurrentIndex(index)
        self.sidebar.button(key).setChecked(True)
        self._title_label.setText(self._titles.get(key, ""))
        self.page_changed.emit(key)

    def page(self, key: str) -> QWidget | None:
        """Widget registered for a nav key (tests / controller wiring)."""
        index = self._ensure_page(key)
        return self.stack.widget(index) if index is not None else None

    # -- status -------------------------------------------------------

    def set_status(self, text: str, state: str = "neutral") -> None:
        """state: neutral | ok | warn | error (styled by the theme)."""
        self._status_label.setText(text)
        self._status_label.setProperty("state", state)
        self._status_label.style().unpolish(self._status_label)
        self._status_label.style().polish(self._status_label)

    @property
    def current_page(self) -> str:
        for key, index in self._pages.items():
            if index == self.stack.currentIndex():
                return key
        return ""

    @property
    def page_title(self) -> str:
        return self._title_label.text()

    @property
    def status_text(self) -> str:
        return self._status_label.text()

    @property
    def status_state(self) -> str:
        return str(self._status_label.property("state"))

    @property
    def theme(self) -> ThemeManager | None:
        return self._theme

    def _on_theme_changed(self, mode: str) -> None:
        if self._theme is not None:
            self._theme.apply(mode)
