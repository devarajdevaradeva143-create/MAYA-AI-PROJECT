"""Settings page reflects the live phone-server state; shared instance is reused."""

from __future__ import annotations

from pathlib import Path

import pytest

import app.services.server_service as server_module
from app.settings_repository import SettingsRepository
from app.ui.pages.settings_page import SettingsPage


class _FakeServer:
    host = "127.0.0.1"
    port = 8420
    bound_port = 8421

    def __init__(self, running: bool) -> None:
        self.running = running
        self.stopped = False

    def stop(self, timeout: float = 5.0) -> None:
        self.stopped = True
        self.running = False


@pytest.fixture
def page(qtbot, tmp_path: Path):
    path = tmp_path / "settings.yaml"
    path.write_text("ui:\n  theme: dark\n", encoding="utf-8")
    repo = SettingsRepository(path, tmp_path / "backups")
    widget = SettingsPage(repo)
    qtbot.addWidget(widget)
    widget.show()
    return widget


def test_page_reports_running_server(page: SettingsPage) -> None:
    page._server = _FakeServer(running=True)
    page._refresh_server_state()
    assert "Running on 127.0.0.1:8421" in page._server_status.text()
    assert page._server_stop_btn.isEnabled()
    assert not page._server_start_btn.isEnabled()
    assert page._server_pin_btn.isEnabled()


def test_page_reports_stopped_server(page: SettingsPage) -> None:
    page._server = _FakeServer(running=False)
    page._refresh_server_state()
    assert "Stopped" in page._server_status.text()
    assert page._server_start_btn.isEnabled()
    assert not page._server_stop_btn.isEnabled()


def test_stop_button_stops_server(page: SettingsPage) -> None:
    fake = _FakeServer(running=True)
    page._server = fake
    page._refresh_server_state()
    page._on_server_stop()
    assert fake.stopped is True
    assert "Stopped" in page._server_status.text()


def test_shared_server_is_singleton(monkeypatch) -> None:
    fake = _FakeServer(running=False)
    monkeypatch.setattr(server_module, "_SHARED_SERVICE", None, raising=False)
    monkeypatch.setattr(server_module, "ServerService", lambda: fake)

    assert server_module.shared_server_service() is fake
    assert server_module.shared_server_service() is fake
    assert server_module._SHARED_SERVICE is fake

    server_module.stop_shared_server()
    assert server_module._SHARED_SERVICE is None


def test_auto_start_setting_is_editable(page: SettingsPage) -> None:
    page._on_server_auto_toggled(True)
    assert page._repository.get("server.auto_start") is True
    page._on_server_auto_toggled(False)
    assert page._repository.get("server.auto_start") is False
