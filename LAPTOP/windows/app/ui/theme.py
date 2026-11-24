"""Maya desktop design tokens + QSS generator (plan section 10).

One palette per theme; `theme: system` follows the OS colour scheme and
switches live. Widgets never hardcode colours: they get their look from the
application stylesheet built here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication

MODES = ("dark", "light", "system")
DEFAULT_MODE = "system"
SIDEBAR_WIDTH = 220
HEADER_HEIGHT = 64
CARD_RADIUS = 18
BUTTON_HEIGHT = 40


@dataclass(frozen=True, slots=True)
class Palette:
    dark: bool
    background: str
    surface: str
    surface_high: str
    primary: str
    secondary: str
    accent: str
    text: str
    text_muted: str
    success: str
    warning: str
    error: str
    border: str

    def rgba(self, token: str, alpha: float) -> str:
        """`rgba(r, g, b, a)` for translucent chips and highlights."""
        color = QColor(getattr(self, token))
        return f"rgba({color.red()}, {color.green()}, {color.blue()}, {alpha:.2f})"


DARK = Palette(
    dark=True,
    background="#0B0B10",
    surface="#14141C",
    surface_high="#1D1D28",
    primary="#B388FF",
    secondary="#64B5F6",
    accent="#FF80AB",
    text="#ECEAF4",
    text_muted="#A8A4B8",
    success="#4ADE80",
    warning="#FBBF24",
    error="#F87171",
    border="#2E2E3C",
)

LIGHT = Palette(
    dark=False,
    background="#F7F6FB",
    surface="#FFFFFF",
    surface_high="#EFEDF7",
    primary="#6C4BC4",
    secondary="#1976D2",
    accent="#D81B60",
    text="#17151F",
    text_muted="#5B5769",
    success="#15803D",
    warning="#B45309",
    error="#B91C1C",
    border="#DAD6E8",
)


def system_is_dark() -> bool:
    """Follow the OS colour scheme; default dark when unavailable."""
    hints = QGuiApplication.styleHints()
    if hints is None:
        return True
    try:
        return hints.colorScheme() == Qt.ColorScheme.Dark
    except (AttributeError, TypeError):
        return True


def palette_for(mode: str) -> Palette:
    normalized = (mode or DEFAULT_MODE).strip().lower()
    if normalized == "light":
        return LIGHT
    if normalized == "dark":
        return DARK
    return DARK if system_is_dark() else LIGHT


def build_qss(palette: Palette, base_font_size: int = 14) -> str:
    """Full application stylesheet for one palette."""
    p = palette
    return f"""
    QWidget {{
        font-family: "Segoe UI", "Noto Sans", sans-serif;
        font-size: {base_font_size}px;
        color: {p.text};
    }}
    QMainWindow, QWidget#central, QStackedWidget#pages, QWidget#pageBody {{
        background-color: {p.background};
    }}
    QFrame#sidebar {{
        background-color: {p.surface};
        border-right: 1px solid {p.border};
    }}
    QLabel#logo {{
        color: {p.primary};
        font-size: 21px;
        font-weight: 700;
        letter-spacing: 1px;
    }}
    QLabel#logoHint {{
        color: {p.text_muted};
        font-size: 11px;
    }}
    QPushButton#navButton {{
        background-color: transparent;
        border: none;
        border-radius: 10px;
        padding: 10px 14px;
        text-align: left;
        color: {p.text_muted};
        font-size: {base_font_size}px;
    }}
    QPushButton#navButton:hover {{
        background-color: {p.surface_high};
        color: {p.text};
    }}
    QPushButton#navButton:checked {{
        background-color: {p.rgba("primary", 0.14)};
        color: {p.primary};
        font-weight: 600;
    }}
    QFrame#header {{
        background-color: {p.background};
        border-bottom: 1px solid {p.border};
    }}
    QLabel#pageTitle {{
        font-size: 22px;
        font-weight: 600;
        color: {p.text};
    }}
    QLabel#statusChip {{
        border-radius: 10px;
        padding: 4px 12px;
        font-size: 12px;
        font-weight: 600;
        background-color: {p.surface_high};
        color: {p.text_muted};
    }}
    QLabel#statusChip[state="ok"] {{
        background-color: {p.rgba("success", 0.15)};
        color: {p.success};
    }}
    QLabel#statusChip[state="warn"] {{
        background-color: {p.rgba("warning", 0.15)};
        color: {p.warning};
    }}
    QLabel#statusChip[state="error"] {{
        background-color: {p.rgba("error", 0.15)};
        color: {p.error};
    }}
    QPushButton#iconButton {{
        background-color: {p.surface_high};
        border: none;
        border-radius: 10px;
        padding: 8px 12px;
        color: {p.text};
    }}
    QPushButton#iconButton:hover {{
        background-color: {p.rgba("primary", 0.18)};
        color: {p.primary};
    }}
    QLabel#emptyIcon {{
        font-size: 44px;
    }}
    QLabel#emptyTitle {{
        font-size: 18px;
        font-weight: 600;
        color: {p.text};
    }}
    QLabel#emptyHint {{
        color: {p.text_muted};
    }}
    QLabel#cardLabel {{
        color: {p.text_muted};
        font-size: 12px;
        text-transform: uppercase;
    }}
    QLabel#cardValue {{
        font-size: 24px;
        font-weight: 600;
    }}
    QFrame#card {{
        background-color: {p.surface};
        border: 1px solid {p.border};
        border-radius: {CARD_RADIUS}px;
    }}
    QLabel#sectionTitle {{
        font-size: 15px;
        font-weight: 600;
        color: {p.text};
    }}
    QScrollArea {{
        background: transparent;
        border: none;
    }}
    QScrollBar:vertical {{
        background: transparent;
        width: 10px;
        margin: 2px;
    }}
    QScrollBar::handle:vertical {{
        background: {p.surface_high};
        border-radius: 4px;
        min-height: 32px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {p.primary};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0;
    }}
    QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
        background-color: {p.surface};
        border: 1px solid {p.border};
        border-radius: 10px;
        padding: 8px 10px;
        selection-background-color: {p.primary};
        selection-color: {p.background};
    }}
    QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus,
    QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
        border-color: {p.primary};
    }}
    QComboBox::drop-down {{
        border: none;
        width: 26px;
    }}
    QComboBox QAbstractItemView {{
        background-color: {p.surface};
        color: {p.text};
        border: 1px solid {p.border};
        selection-background-color: {p.surface_high};
        selection-color: {p.text};
        outline: none;
    }}
    QCheckBox {{
        spacing: 10px;
        color: {p.text};
    }}
    QCheckBox::indicator {{
        width: 18px;
        height: 18px;
        border-radius: 5px;
        border: 1px solid {p.border};
        background-color: {p.surface};
    }}
    QCheckBox::indicator:hover {{
        border-color: {p.primary};
    }}
    QCheckBox::indicator:checked {{
        background-color: {p.primary};
        border-color: {p.primary};
    }}
    QLabel#formStatus {{
        color: {p.text_muted};
        font-size: 12px;
    }}
    QLabel#formStatus[state="ok"] {{
        color: {p.success};
    }}
    QLabel#formStatus[state="error"] {{
        color: {p.error};
    }}
    QFrame#bubbleUser {{
        background-color: {p.rgba("primary", 0.18)};
        border-radius: 14px;
    }}
    QFrame#bubbleAssistant {{
        background-color: {p.surface};
        border: 1px solid {p.border};
        border-radius: 14px;
    }}
    QFrame#banner {{
        background-color: {p.rgba("error", 0.12)};
        border: 1px solid {p.rgba("error", 0.40)};
        border-radius: 12px;
    }}
    QFrame#banner[state="info"] {{
        background-color: {p.surface_high};
        border: 1px solid {p.border};
    }}
    QLabel#bannerText {{
        color: {p.error};
    }}
    QFrame#banner[state="info"] QLabel#bannerText {{
        color: {p.text_muted};
    }}
    QPushButton {{
        background-color: {p.surface_high};
        border: none;
        border-radius: 10px;
        padding: 8px 16px;
        min-height: {BUTTON_HEIGHT - 16}px;
        color: {p.text};
    }}
    QPushButton:hover {{
        background-color: {p.rgba("primary", 0.18)};
    }}
    QPushButton:disabled {{
        color: {p.text_muted};
        background-color: {p.surface_high};
    }}
    QPushButton#primaryButton {{
        background-color: {p.primary};
        color: {p.background};
        font-weight: 600;
    }}
    QPushButton#primaryButton:hover {{
        background-color: {p.secondary};
    }}
    QToolTip {{
        background-color: {p.surface_high};
        color: {p.text};
        border: 1px solid {p.border};
        padding: 6px;
    }}
    """


class ThemeManager(QObject):
    """Applies the palette to QApplication and follows the OS in `system` mode."""

    changed = Signal(str)  # resolved palette name: "dark" | "light"

    def __init__(self, app: Any, mode: str = DEFAULT_MODE) -> None:
        super().__init__(app)
        self._app = app
        self._mode = DEFAULT_MODE
        self._system_connected = False
        self.apply(mode)

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def resolved(self) -> str:
        return "dark" if palette_for(self._mode).dark else "light"

    def apply(self, mode: str) -> str:
        """Switch theme (dark/light/system); returns the resolved name."""
        normalized = (mode or DEFAULT_MODE).strip().lower()
        if normalized not in MODES:
            normalized = DEFAULT_MODE
        self._mode = normalized

        self._connect_system(normalized == "system")
        palette = palette_for(normalized)
        self._app.setStyleSheet(build_qss(palette))
        resolved = "dark" if palette.dark else "light"
        self.changed.emit(resolved)
        return resolved

    def _connect_system(self, enabled: bool) -> None:
        hints = QGuiApplication.styleHints()
        if hints is None:
            return
        if enabled and not self._system_connected:
            hints.colorSchemeChanged.connect(self._on_system_scheme)
            self._system_connected = True
        elif not enabled and self._system_connected:
            try:
                hints.colorSchemeChanged.disconnect(self._on_system_scheme)
            except (RuntimeError, TypeError):
                pass
            self._system_connected = False

    def _on_system_scheme(self, *_: Any) -> None:
        if self._mode == "system":
            self.apply("system")
