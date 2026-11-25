"""Settings repository tests (round-trip, validation, backups)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.settings_repository import SettingsError, SettingsRepository, writable_keys

SAMPLE = """# Maya AI settings (test copy)
mode: offline

ui:
  theme: system        # dark | light | system
  window_width: 1180
  window_height: 760
  minimize_to_tray: true

server:
  enabled: true
  host: 0.0.0.0
  port: 8420

# trailing comment must survive
permissions:
  edit: ask
  allowed_roots:
    - "C:\\\\Users\\\\devar\\\\Desktop"
"""


@pytest.fixture
def repo(tmp_path: Path) -> SettingsRepository:
    path = tmp_path / "config" / "settings.yaml"
    path.parent.mkdir()
    path.write_text(SAMPLE, encoding="utf-8")
    return SettingsRepository(path, tmp_path / "config" / "backups")


def test_writable_keys_are_dotted_and_unique() -> None:
    keys = writable_keys()

    assert "ui.theme" in keys
    assert "server.port" in keys
    assert len(keys) == len(set(keys))


def test_get_returns_plain_values(repo: SettingsRepository) -> None:
    assert repo.get("ui.theme") == "system"
    assert repo.get("server.port") == 8420
    assert isinstance(repo.get("server.port"), int)
    assert repo.get("ui.missing", "fallback") == "fallback"


def test_update_preserves_comments_and_creates_backup(repo: SettingsRepository) -> None:
    backup = repo.update({"ui.theme": "dark", "server.port": "9000"})

    text = repo.path.read_text(encoding="utf-8")
    assert "# Maya AI settings (test copy)" in text
    assert "# dark | light | system" in text
    assert "# trailing comment must survive" in text
    assert repo.get("ui.theme") == "dark"
    assert repo.get("server.port") == 9000
    assert isinstance(repo.get("server.port"), int)

    assert backup is not None
    assert backup.parent == repo.backup_dir
    assert backup.name.startswith("settings-")
    assert "ui:\n  theme: system" in backup.read_text(encoding="utf-8")


def test_update_without_changes_writes_nothing(repo: SettingsRepository) -> None:
    before = repo.path.read_bytes()

    assert repo.update({"ui.theme": "system", "server.port": "8420"}) is None
    assert repo.path.read_bytes() == before
    assert repo.backups() == []


def test_invalid_value_is_rejected_and_file_untouched(repo: SettingsRepository) -> None:
    before = repo.path.read_bytes()

    with pytest.raises(SettingsError, match="ui.theme"):
        repo.update({"ui.theme": "purple", "server.port": 9000})

    assert repo.path.read_bytes() == before
    assert repo.backups() == []


def test_unknown_key_is_rejected(repo: SettingsRepository) -> None:
    with pytest.raises(SettingsError, match="not editable"):
        repo.update({"ui.nope": True})


def test_unknown_existing_keys_are_preserved(tmp_path: Path) -> None:
    path = tmp_path / "settings.yaml"
    path.write_text("mode: offline\nfuture_feature:\n  flag: true\n", encoding="utf-8")
    repo = SettingsRepository(path, tmp_path / "backups")

    repo.update({"mode": "online"})

    data = repo.plain()
    assert data["future_feature"] == {"flag": True}
    assert data["mode"] == "online"


def test_new_section_is_created_when_missing(tmp_path: Path) -> None:
    path = tmp_path / "settings.yaml"
    path.write_text("mode: offline\n", encoding="utf-8")
    repo = SettingsRepository(path, tmp_path / "backups")

    repo.update({"ui.theme": "light"})

    assert repo.get("ui.theme") == "light"


@pytest.mark.parametrize(
    ("key", "raw", "expected"),
    [
        ("server.enabled", "false", False),
        ("server.lan_only", 0, False),
        ("server.pin_ttl_seconds", "90", 90),
        ("server.max_devices", 8, 8),
        ("voice.tts.volume", "55", 55),
        ("engine.temperature", "0.4", 0.4),
        ("wake.name", "  Maya  ", "Maya"),
    ],
)
def test_values_are_coerced(
    repo: SettingsRepository, key: str, raw: object, expected: object
) -> None:
    repo.update({key: raw})

    assert repo.get(key) == expected


@pytest.mark.parametrize(
    ("key", "raw"),
    [
        ("server.pin_ttl_seconds", 10),
        ("server.max_devices", 99),
        ("ui.window_width", 100),
        ("engine.temperature", 9),
        ("server.port", "not-a-port"),
    ],
)
def test_out_of_range_values_are_rejected(
    repo: SettingsRepository, key: str, raw: object
) -> None:
    before = repo.path.read_bytes()

    with pytest.raises(SettingsError, match=key):
        repo.update({key: raw})

    assert repo.path.read_bytes() == before


def test_allowed_roots_requires_absolute_paths(repo: SettingsRepository) -> None:
    with pytest.raises(SettingsError, match="allowed_roots"):
        repo.update({"permissions.allowed_roots": ["relative/folder"]})


def test_allowed_roots_deduplicates(repo: SettingsRepository) -> None:
    repo.update(
        {
            "permissions.allowed_roots": [
                r"C:\Users\devar\Desktop",
                r"C:\Users\devar\Desktop",
                r"C:\Users\devar\Documents",
            ]
        }
    )

    assert repo.get("permissions.allowed_roots") == [
        r"C:\Users\devar\Desktop",
        r"C:\Users\devar\Documents",
    ]


def test_restore_round_trips_and_backs_up_current(repo: SettingsRepository) -> None:
    backup = repo.update({"ui.theme": "dark"})
    assert backup is not None
    repo.update({"ui.theme": "light"})

    kept = repo.restore(backup)

    # The backup holds the state *before* the write, i.e. the original value.
    assert kept is not None and kept.is_file()
    assert repo.get("ui.theme") == "system"


def test_restore_rejects_missing_or_invalid_backup(repo: SettingsRepository, tmp_path: Path) -> None:
    with pytest.raises(SettingsError, match="not found"):
        repo.restore(tmp_path / "nope.yaml")

    bad = tmp_path / "bad.yaml"
    bad.write_text("- just\n- a list\n", encoding="utf-8")
    with pytest.raises(SettingsError, match="mapping"):
        repo.restore(bad)


def test_no_temp_files_left_behind(repo: SettingsRepository) -> None:
    repo.update({"ui.theme": "dark"})

    leftovers = [item.name for item in repo.path.parent.iterdir() if item.name.endswith(".tmp")]
    assert leftovers == []


def test_crlf_file_keeps_crlf(repo: SettingsRepository) -> None:
    repo.path.write_bytes(repo.path.read_bytes().replace(b"\n", b"\r\n"))

    repo.update({"ui.theme": "dark"})

    data = repo.path.read_bytes()
    assert b"\r\n" in data
    assert data.replace(b"\r\n", b"").count(b"\n") == 0


def test_backups_listed_newest_first(repo: SettingsRepository) -> None:
    first = repo.update({"ui.theme": "dark"})
    second = repo.update({"ui.theme": "light"})

    listed = repo.backups()

    assert first is not None and second is not None
    assert listed[0] == second
    assert listed[1] == first


def test_missing_file_starts_empty(tmp_path: Path) -> None:
    repo = SettingsRepository(tmp_path / "settings.yaml", tmp_path / "backups")

    assert repo.plain() == {}
    assert repo.update({"ui.theme": "dark"}) is None
    assert repo.get("ui.theme") == "dark"
    assert repo.backups() == []
