"""Cloud (Gemini) adapter tests — no network, no real key."""

from __future__ import annotations

from typing import Any

import pytest

from app.services.cloud_service import CloudAdapter, CloudUnavailableError
from app.settings_repository import SettingsError, SettingsRepository
from app.ui.pages.settings_page import SettingsPage


class FakeTools:
    """Stand-in for `custom.tools.cloud`."""

    def __init__(
        self,
        configured: bool = True,
        enabled: bool = True,
        ask: Any = None,
    ) -> None:
        self.configured = configured
        self._enabled = enabled
        self.ask_result = ask if ask is not None else "Gemini reply"
        self.asked: list[str] = []
        self.systems: list[str | None] = []
        self.logged: list[tuple[str, str]] = []
        self.saved: list[str] = []

    def status(self) -> dict[str, Any]:
        return {
            "configured": self.configured,
            "key_preview": "...abcd" if self.configured else None,
            "model": "gemini-3.5-flash-lite",
            "endpoint": "https://example.invalid/v1beta",
            "env_file": "",
        }

    def enabled(self) -> bool:
        return self._enabled

    def model_name(self) -> str:
        return "gemini-3.5-flash-lite"

    def ask(self, prompt: str, system: str | None = None) -> str:
        self.systems.append(system)
        self.asked.append(prompt)
        if isinstance(self.ask_result, Exception):
            raise self.ask_result
        return self.ask_result

    def log_exchange(self, prompt: str, reply: str) -> None:
        self.logged.append((prompt, reply))

    def save_api_key(self, key: str) -> dict[str, Any]:
        self.saved.append(key)
        return {"ok": True}


def test_available_needs_key_and_enabled_flag() -> None:
    assert CloudAdapter(FakeTools(configured=True, enabled=True)).available is True
    assert CloudAdapter(FakeTools(configured=False, enabled=True)).available is False
    assert CloudAdapter(FakeTools(configured=True, enabled=False)).available is False


def test_ask_returns_reply_and_writes_online_log() -> None:
    tools = FakeTools(ask="Vanakkam da!")
    adapter = CloudAdapter(tools)

    assert adapter.ask("hi") == "Vanakkam da!"
    assert tools.asked == ["hi"]
    assert tools.logged == [("hi", "Vanakkam da!")]


def test_ask_refuses_when_disabled() -> None:
    adapter = CloudAdapter(FakeTools(enabled=False))

    with pytest.raises(CloudUnavailableError, match="disabled"):
        adapter.ask("hi")


def test_ask_refuses_without_key() -> None:
    adapter = CloudAdapter(FakeTools(configured=False))

    with pytest.raises(CloudUnavailableError, match="key"):
        adapter.ask("hi")


def test_ask_wraps_cloud_errors() -> None:
    adapter = CloudAdapter(FakeTools(ask=RuntimeError("Cannot reach Gemini: ConnectError")))

    with pytest.raises(CloudUnavailableError, match="Cannot reach Gemini"):
        adapter.ask("hi")


class _Settings:
    """Minimal settings stub for the prompt tests."""

    def __init__(self, values: dict[str, Any]) -> None:
        self.values = values

    def get(self, key: str, default: Any = None) -> Any:
        return self.values.get(key, default)


def test_system_prompt_is_sent_with_each_request() -> None:
    tools = FakeTools()
    adapter = CloudAdapter(tools, settings=_Settings({"cloud.system_prompt": "Be brief."}))

    adapter.ask("hi")

    assert tools.systems == ["Be brief."]


def test_no_system_prompt_keeps_gemini_default() -> None:
    tools = FakeTools()
    adapter = CloudAdapter(tools, settings=_Settings({}))

    adapter.ask("hi")

    assert tools.systems == [None]


def test_settings_prompt_box_saves_to_yaml(qtbot, tmp_path) -> None:
    path = tmp_path / "settings.yaml"
    path.write_text("cloud:\n  enabled: true\n", encoding="utf-8")
    repo = SettingsRepository(path, tmp_path / "backups")
    page = SettingsPage(repo, cloud=CloudAdapter(FakeTools()))
    qtbot.addWidget(page)

    page._cloud_prompt_input.setPlainText("You are Maya. Reply in Tanglish.")
    page._cloud_prompt_save.click()

    assert repo.get("cloud.system_prompt") == "You are Maya. Reply in Tanglish."
    assert "Prompt saved" in page._cloud_status.text()


def test_status_never_contains_the_key() -> None:
    status = CloudAdapter(FakeTools()).status()

    assert status["available"] is True
    assert status["key_preview"] == "...abcd"
    assert "key" not in {name for name in status if name == "key"}


def test_settings_cloud_card_saves_key(qtbot, tmp_path) -> None:
    path = tmp_path / "settings.yaml"
    path.write_text("cloud:\n  enabled: true\n  model: gemini-3.5-flash-lite\n", encoding="utf-8")
    repo = SettingsRepository(path, tmp_path / "backups")
    tools = FakeTools()
    page = SettingsPage(repo, cloud=CloudAdapter(tools))
    qtbot.addWidget(page)

    assert "Ready" in page._cloud_status.text()

    page._cloud_key_input.setText("AIza-test-key-value-1234")
    page._cloud_key_button.click()

    assert tools.saved == ["AIza-test-key-value-1234"]
    assert page._cloud_key_input.text() == ""
    assert "never shown" in page._cloud_status.text()


def test_settings_toggle_writes_cloud_enabled(qtbot, tmp_path) -> None:
    path = tmp_path / "settings.yaml"
    path.write_text("cloud:\n  enabled: true\n", encoding="utf-8")
    repo = SettingsRepository(path, tmp_path / "backups")
    page = SettingsPage(repo, cloud=CloudAdapter(FakeTools()))
    qtbot.addWidget(page)

    page._cloud_enable.setChecked(False)

    assert repo.get("cloud.enabled") is False
    assert "Disabled" in page._cloud_status.text()
    assert page._cloud_enable.text() == "Off"


def test_settings_engine_switch_writes_engine_enabled(qtbot, tmp_path) -> None:
    path = tmp_path / "settings.yaml"
    path.write_text("engine:\n  enabled: true\n  host: http://localhost:13305\n", encoding="utf-8")
    repo = SettingsRepository(path, tmp_path / "backups")
    page = SettingsPage(repo, cloud=CloudAdapter(FakeTools()))
    qtbot.addWidget(page)

    assert page._engine_enable.text() == "On"
    assert "localhost:13305" in page._engine_status.text()

    page._engine_enable.setChecked(False)

    assert repo.get("engine.enabled") is False
    assert page._engine_enable.text() == "Off"
    assert "Off" in page._engine_status.text()

    page._engine_enable.setChecked(True)

    assert repo.get("engine.enabled") is True
    assert page._engine_enable.text() == "On"


def test_settings_switch_colours_track_state(qtbot, tmp_path) -> None:
    path = tmp_path / "settings.yaml"
    path.write_text(
        "engine:\n  enabled: true\ncloud:\n  enabled: true\n", encoding="utf-8"
    )
    repo = SettingsRepository(path, tmp_path / "backups")
    page = SettingsPage(repo, cloud=CloudAdapter(FakeTools()))
    qtbot.addWidget(page)

    assert page._engine_enable.objectName() == "switchOn"
    page._engine_enable.setChecked(False)
    assert page._engine_enable.objectName() == "switchOff"


def test_switch_reverts_when_the_write_fails(qtbot, tmp_path, monkeypatch) -> None:
    path = tmp_path / "settings.yaml"
    path.write_text("engine:\n  enabled: true\n", encoding="utf-8")
    repo = SettingsRepository(path, tmp_path / "backups")
    page = SettingsPage(repo, cloud=CloudAdapter(FakeTools()))
    qtbot.addWidget(page)

    def refuse(changes):
        raise SettingsError("settings.yaml is read-only")

    monkeypatch.setattr(repo, "update", refuse)
    page._engine_enable.setChecked(False)

    # The switch must not show a state the file does not have.
    assert page._engine_enable.isChecked() is True
    assert page._engine_enable.text() == "On"
    assert "read-only" in page._engine_status.text()


def test_quoted_yaml_boolean_shows_off(qtbot, tmp_path) -> None:
    path = tmp_path / "settings.yaml"
    path.write_text('engine:\n  enabled: "false"\n', encoding="utf-8")
    repo = SettingsRepository(path, tmp_path / "backups")
    page = SettingsPage(repo, cloud=CloudAdapter(FakeTools()))
    qtbot.addWidget(page)

    assert page._engine_enable.isChecked() is False
    assert page._engine_enable.text() == "Off"


def test_both_engines_off_warns_in_settings(qtbot, tmp_path) -> None:
    path = tmp_path / "settings.yaml"
    path.write_text(
        "engine:\n  enabled: true\ncloud:\n  enabled: true\n", encoding="utf-8"
    )
    repo = SettingsRepository(path, tmp_path / "backups")
    page = SettingsPage(repo, cloud=CloudAdapter(FakeTools()))
    qtbot.addWidget(page)

    page._engine_enable.setChecked(False)
    page._cloud_enable.setChecked(False)

    assert "cannot answer" in page._engine_status.text()

    page._engine_enable.setChecked(True)

    assert "cannot answer" not in page._engine_status.text()
