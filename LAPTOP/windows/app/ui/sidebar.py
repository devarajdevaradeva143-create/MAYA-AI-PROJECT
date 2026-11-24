"""Left navigation sidebar (logo, 7 sections, local-only footer)."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
)

from app import __version__
from app.ui.theme import SIDEBAR_WIDTH

NAV_ITEMS: tuple[tuple[str, str, str], ...] = (
    ("chat", "💬", "Chat"),
    ("voice", "🎤", "Voice"),
    ("pc", "🖥️", "PC Control"),
    ("monitor", "📊", "Monitoring"),
    ("phone_remote", "📱", "Phone Remote"),
    ("teacher", "📚", "English Teacher"),
    ("security", "🔒", "Security"),
    ("settings", "⚙️", "Settings"),
)


class Sidebar(QFrame):
    """Vertical nav; emits `navigate(key)` and keeps one item checked."""

    navigate = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("sidebar")
        self.setFixedWidth(SIDEBAR_WIDTH)

        self._buttons: dict[str, QPushButton] = {}
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 20, 14, 16)
        layout.setSpacing(4)

        logo = QLabel("Maya")
        logo.setObjectName("logo")
        hint = QLabel("local · private · yours")
        hint.setObjectName("logoHint")
        layout.addWidget(logo)
        layout.addWidget(hint)
        layout.addSpacing(18)

        for key, icon, label in NAV_ITEMS:
            button = QPushButton(f"{icon}   {label}")
            button.setObjectName("navButton")
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            button.clicked.connect(lambda _checked=False, k=key: self.navigate.emit(k))
            self._group.addButton(button)
            self._buttons[key] = button
            layout.addWidget(button)

        layout.addStretch(1)

        footer = QLabel(f"v{__version__} · LAN only")
        footer.setObjectName("logoHint")
        footer.setAlignment(Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(footer)

    # -- api ----------------------------------------------------------

    def set_active(self, key: str) -> None:
        button = self._buttons.get(key)
        if button is None:
            return
        button.setChecked(True)
        self.navigate.emit(key)

    def button(self, key: str) -> QPushButton:
        return self._buttons[key]

    def keys(self) -> tuple[str, ...]:
        return tuple(self._buttons)
