"""Phase 1/2 UI tests: shell navigation, theme + settings save, single instance."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from app.services.chat_service import ChatService
from app.settings_repository import SettingsError, SettingsRepository
from app.single_instance import SingleInstance
from app.ui.main_window import MayaMainWindow
from app.ui.pages.settings_page import SettingsPage
from app.ui.sidebar import NAV_ITEMS
from app.ui.theme import DARK, LIGHT, ThemeManager
from tests.fakes import FakeEngine

SAMPLE = """# test settings (keep me)
mode: offline

ui:
  theme: system      # keep this comment
  window_width: 1180
  window_height: 760
  minimize_to_tray: true
  close_to_tray: true
  start_minimized: false
"""


@pytest.fixture
def repo(tmp_path: Path) -> SettingsRepository:
    path = tmp_path / "settings.yaml"
    path.write_text(SAMPLE, encoding="utf-8")
    return SettingsRepository(path, tmp_path / "backups")


@pytest.fixture
def window(qtbot, repo: SettingsRepository, tmp_path: Path) -> MayaMainWindow:
    chat = ChatService(FakeEngine(), tmp_path / "chat_history.json")
    theme = ThemeManager(QApplication.instance(), "dark")
    win = MayaMainWindow(repository=repo, theme=theme, chat=chat)
    qtbot.addWidget(win)
    win.show()
    return win


def test_sidebar_has_all_seven_sections(window: MayaMainWindow) -> None:
    keys = tuple(key for key, _icon, _label in NAV_ITEMS)

    assert window.sidebar.keys() == keys
    assert len(keys) == 8


def test_navigation_switches_every_page(window: MayaMainWindow) -> None:
    for key, _icon, label in NAV_ITEMS:
        window.navigate(key)

        assert window.current_page == key
        assert window.sidebar.button(key).isChecked()
        assert window.page_title == label


def test_sidebar_click_navigates(qtbot, window: MayaMainWindow) -> None:
    qtbot.mouseClick(window.sidebar.button("monitor"), Qt.MouseButton.LeftButton)

    assert window.current_page == "monitor"


def test_status_chip_states(window: MayaMainWindow) -> None:
    window.set_status("Engine offline", "error")

    assert window.status_text == "Engine offline"
    assert window.status_state == "error"


def test_theme_switches_live(qtbot) -> None:
    app = QApplication.instance()
    theme = ThemeManager(app, "dark")

    assert theme.apply("dark") == "dark"
    assert DARK.background.lower() in app.styleSheet().lower()

    assert theme.apply("light") == "light"
    assert LIGHT.background.lower() in app.styleSheet().lower()
    assert theme.mode == "light"

    # Invalid names fall back to system, never crash.
    assert theme.apply("purple") in {"dark", "light"}


def test_window_uses_saved_size(qtbot, tmp_path: Path) -> None:
    path = tmp_path / "settings.yaml"
    path.write_text("ui:\n  window_width: 1280\n  window_height: 700\n", encoding="utf-8")
    repo = SettingsRepository(path, tmp_path / "backups")
    chat = ChatService(FakeEngine(), tmp_path / "chat_history.json")

    win = MayaMainWindow(repository=repo, chat=chat)
    qtbot.addWidget(win)

    assert win.width() >= 1280
    assert win.height() >= 700


def test_settings_save_writes_yaml_and_backup(qtbot, window: MayaMainWindow, repo: SettingsRepository) -> None:
    window.navigate("settings")
    page = window.page("settings")
    assert isinstance(page, SettingsPage)

    page.set_theme_choice("light")
    page.set_startup_choices(close_to_tray=False, minimize_to_tray=True, start_minimized=True)

    assert page.save() is True

    assert repo.get("ui.theme") == "light"
    assert repo.get("ui.close_to_tray") is False
    assert repo.get("ui.start_minimized") is True
    assert repo.backups(), "a timestamped backup must exist"
    assert "# keep this comment" in repo.path.read_text(encoding="utf-8")
    assert "Saved" in page.status_text


def test_settings_save_reports_validation_error(qtbot, window: MayaMainWindow, repo: SettingsRepository, monkeypatch) -> None:
    window.navigate("settings")
    page = window.page("settings")
    assert isinstance(page, SettingsPage)

    def _boom(_changes):
        raise SettingsError("ui.theme: must be one of: dark, light, system")

    monkeypatch.setattr(repo, "update", _boom)

    assert page.save() is False
    assert "ui.theme" in page.status_text


def test_settings_no_changes_message(qtbot, window: MayaMainWindow) -> None:
    window.navigate("settings")
    page = window.page("settings")
    assert isinstance(page, SettingsPage)

    assert page.save() is True
    assert page.status_text == "No changes to save."


def test_single_instance_second_launch_activates_first(qtbot) -> None:
    key = f"maya-test-{uuid.uuid4().hex}"
    first = SingleInstance(key)
    second = SingleInstance(key)
    assert first.try_acquire() is True

    try:
        with qtbot.waitSignal(first.activated, timeout=3000):
            assert second.try_acquire() is False
    finally:
        second.close()
        first.close()
