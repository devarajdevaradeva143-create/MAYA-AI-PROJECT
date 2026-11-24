"""W1: monitor/teacher/security pages are real widgets, not placeholders."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from app.services.chat_service import ChatService
from app.settings_repository import SettingsRepository
from app.ui.main_window import MayaMainWindow
from app.ui.pages.monitor_page import MonitorPage
from app.ui.pages.security_page import SecurityPage
from app.ui.pages.teacher_page import TeacherPage
from app.ui.theme import ThemeManager
from app.ui.widgets.empty_state import PlaceholderPage
from tests.fakes import FakeEngine


@pytest.fixture
def window(qtbot, tmp_path: Path):
    path = tmp_path / "settings.yaml"
    path.write_text(
        "ui:\n  theme: dark\n  window_width: 1180\n  window_height: 760\n",
        encoding="utf-8",
    )
    repo = SettingsRepository(path, tmp_path / "backups")
    chat = ChatService(FakeEngine(), tmp_path / "chat_history.json")
    theme = ThemeManager(QApplication.instance(), "dark")
    win = MayaMainWindow(repository=repo, theme=theme, chat=chat)
    qtbot.addWidget(win)
    win.show()
    return win


def test_no_placeholder_for_core_pages(window: MayaMainWindow) -> None:
    for key, expected in (
        ("monitor", MonitorPage),
        ("teacher", TeacherPage),
        ("security", SecurityPage),
    ):
        page = window.page(key)
        assert page is not None
        assert type(page) is expected, (key, type(page).__name__)
        assert not isinstance(page, PlaceholderPage)


def test_all_seven_pages_navigate(window: MayaMainWindow) -> None:
    for key, _icon, _label in __import__("app.ui.sidebar", fromlist=["NAV_ITEMS"]).NAV_ITEMS:
        window.navigate(key)
        assert window.current_page == key
        assert window.page(key) is not None
