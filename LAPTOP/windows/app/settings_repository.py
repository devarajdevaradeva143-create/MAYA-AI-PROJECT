"""Round-trip settings editing for `MAYA AI\\config\\settings.yaml`.

The YAML file is the source of truth (AGENTS.md rule 4), so the desktop app
must never rewrite it with PyYAML: comments and key order would be lost.
This repository uses `ruamel.yaml` round-trip mode and follows the plan
(Phase 2):

- validate + coerce every value before touching the file;
- timestamped backup in `MAYA AI\\config\\backups\\` before each write;
- atomic replace (`tmp` + `os.replace`);
- unknown keys are preserved; unknown *writes* are rejected.

Nothing here logs values (settings can hold private paths).
"""

from __future__ import annotations

import copy
import io
import os
import threading
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap

from app import paths

THEMES = ("dark", "light", "system")
PERMISSION_LEVELS = ("allow", "ask", "deny")


class SettingsError(ValueError):
    """Invalid settings change; the message is safe to show in the UI."""


# -- value coercion ---------------------------------------------------


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "on", "1"}:
            return True
        if lowered in {"false", "no", "off", "0"}:
            return False
    raise SettingsError("expects true or false")


def _as_int(minimum: int, maximum: int) -> Callable[[Any], int]:
    def coerce(value: Any) -> int:
        if isinstance(value, bool) or not isinstance(value, int | float | str):
            raise SettingsError("expects a whole number")
        try:
            number = int(str(value).strip()) if isinstance(value, str) else int(value)
        except (TypeError, ValueError) as exc:
            raise SettingsError("expects a whole number") from exc
        if not minimum <= number <= maximum:
            raise SettingsError(f"must be between {minimum} and {maximum}")
        return number

    return coerce


def _as_float(minimum: float, maximum: float) -> Callable[[Any], float]:
    def coerce(value: Any) -> float:
        if isinstance(value, bool) or not isinstance(value, int | float | str):
            raise SettingsError("expects a number")
        try:
            number = float(str(value).strip()) if isinstance(value, str) else float(value)
        except (TypeError, ValueError) as exc:
            raise SettingsError("expects a number") from exc
        if not minimum <= number <= maximum:
            raise SettingsError(f"must be between {minimum} and {maximum}")
        return number

    return coerce


def _as_choice(*choices: str) -> Callable[[Any], str]:
    allowed = ", ".join(choices)

    def coerce(value: Any) -> str:
        if not isinstance(value, str):
            raise SettingsError(f"must be one of: {allowed}")
        lowered = value.strip().lower()
        if lowered not in choices:
            raise SettingsError(f"must be one of: {allowed}")
        return lowered

    return coerce


def _as_text(max_length: int = 200) -> Callable[[Any], str]:
    def coerce(value: Any) -> str:
        if not isinstance(value, str):
            raise SettingsError("expects text")
        text = value.strip()
        if not text:
            raise SettingsError("must not be empty")
        if len(text) > max_length:
            raise SettingsError(f"must be at most {max_length} characters")
        return text

    return coerce


def _as_url(value: Any) -> str:
    text = _as_text(300)(value)
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise SettingsError("must be an http:// or https:// address")
    return text.rstrip("/")


def _as_bind_host(value: Any) -> str:
    text = _as_text(64)(value)
    if text in {"0.0.0.0", "localhost"}:
        return text
    parts = text.split(".")
    if len(parts) != 4 or not all(part.isdigit() and 0 <= int(part) <= 255 for part in parts):
        raise SettingsError("must be 0.0.0.0, localhost or an IPv4 address")
    return text


def _as_roots(value: Any) -> list[str]:
    if isinstance(value, str):
        candidate: Any = [value]
    else:
        candidate = value
    if not isinstance(candidate, list | tuple):
        raise SettingsError("expects a list of folders")
    if len(candidate) > 20:
        raise SettingsError("at most 20 folders are allowed")

    roots: list[str] = []
    for item in candidate:
        text = _as_text(300)(item)
        path = Path(text).expanduser()
        if not path.is_absolute():
            raise SettingsError(f"folder must be an absolute path: {text}")
        resolved = str(path)
        if resolved not in roots:
            roots.append(resolved)
    return roots


# -- writable schema --------------------------------------------------

_SCHEMA: dict[str, Callable[[Any], Any]] = {
    "mode": _as_choice("offline", "online"),
    "hardware": _as_choice("auto", "cpu", "gpu", "npu"),
    "language": _as_choice("tamil", "english", "tanglish"),
    "runtime.background": _as_bool,
    "runtime.autostart": _as_bool,
    "wake.enabled": _as_bool,
    "wake.name": _as_text(40),
    "wake.name_repeat": _as_int(1, 10),
    "wake.clap_count": _as_int(1, 10),
    "wake.reply": _as_text(200),
    "engine.host": _as_url,
    "engine.model": _as_text(120),
    "engine.timeout": _as_int(5, 300),
    "engine.temperature": _as_float(0.0, 2.0),
    "engine.max_tokens": _as_int(64, 4096),
    "permissions.read": _as_choice(*PERMISSION_LEVELS),
    "permissions.edit": _as_choice(*PERMISSION_LEVELS),
    "permissions.delete": _as_choice(*PERMISSION_LEVELS),
    "permissions.important": _as_choice(*PERMISSION_LEVELS),
    "permissions.shell": _as_choice(*PERMISSION_LEVELS),
    "permissions.allowed_roots": _as_roots,
    "security.watchdog.idle_lock_minutes": _as_int(0, 240),
    "security.watchdog.max_session_minutes": _as_int(0, 1440),
    "security.watchdog.voice_check_minutes": _as_int(0, 240),
    "voice.tts.engine": _as_choice("auto", "piper", "sapi"),
    "voice.tts.volume": _as_int(0, 100),
    "voice.clap.threshold": _as_int(100, 20000),
    "voice.clap.count": _as_int(1, 10),
    "voice.clap.cooldown": _as_float(1.0, 120.0),
    "cloud.enabled": _as_bool,
    "server.enabled": _as_bool,
    "server.auto_start": _as_bool,
    "server.host": _as_bind_host,
    "server.port": _as_int(1, 65535),
    "server.lan_only": _as_bool,
    "server.token_ttl_hours": _as_int(1, 8760),
    "server.pin_ttl_seconds": _as_int(30, 600),
    "server.qr_ttl_seconds": _as_int(30, 600),
    "server.max_pair_attempts": _as_int(1, 20),
    "server.lockout_minutes": _as_int(1, 1440),
    "server.max_devices": _as_int(1, 32),
    "ui.theme": _as_choice(*THEMES),
    "ui.window_width": _as_int(800, 3840),
    "ui.window_height": _as_int(600, 2160),
    "ui.minimize_to_tray": _as_bool,
    "ui.close_to_tray": _as_bool,
    "ui.start_minimized": _as_bool,
    "ui.confirm_destructive": _as_bool,
    "phone_remote.enabled": _as_bool,
    "bluetooth_remote.enabled": _as_bool,
    "wan_remote.enabled": _as_bool,
    "wan_remote.relay_url": _as_url,
    "wan_remote.cert_path": _as_text(300),
    "wan_remote.key_path": _as_text(300),
}


def writable_keys() -> tuple[str, ...]:
    """Dotted keys the Settings page is allowed to change."""
    return tuple(sorted(_SCHEMA))


# -- helpers ----------------------------------------------------------


def _plain(value: Any) -> Any:
    """Convert ruamel scalar types to plain Python values."""
    if isinstance(value, CommentedMap | dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_plain(item) for item in value]
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        return float(value)
    if isinstance(value, str):
        return str(value)
    return copy.deepcopy(value)


def _split(key: str) -> list[str]:
    parts = [part for part in key.split(".") if part]
    if not parts:
        raise SettingsError("Settings key is empty")
    return parts


class SettingsRepository:
    """Read/write settings with validation, backups and comment preservation."""

    def __init__(self, path: Path | None = None, backup_dir: Path | None = None) -> None:
        self._path = Path(path) if path is not None else paths.settings_path()
        self._backup_dir = Path(backup_dir) if backup_dir is not None else paths.backups_dir()
        self._lock = threading.RLock()
        self._yaml = YAML()
        self._yaml.preserve_quotes = True
        self._yaml.width = 4096

    # -- read ---------------------------------------------------------

    @property
    def path(self) -> Path:
        return self._path

    @property
    def backup_dir(self) -> Path:
        return self._backup_dir

    def load(self) -> CommentedMap:
        """Parsed file (round-trip object). Empty map when the file is new."""
        with self._lock:
            if not self._path.is_file():
                return CommentedMap()
            try:
                text = self._path.read_text(encoding="utf-8")
                data = self._yaml.load(text)
            except OSError as exc:
                raise SettingsError(f"Could not read settings: {exc}") from exc
            except Exception as exc:  # noqa: BLE001 - YAML errors must not crash the UI
                raise SettingsError(f"settings.yaml is not valid YAML: {exc}") from exc
            if data is None:
                return CommentedMap()
            if not isinstance(data, CommentedMap):
                raise SettingsError("settings.yaml must contain a mapping at the top level")
            return data

    def plain(self) -> dict[str, Any]:
        """Plain dict for services/tests (no ruamel types)."""
        return _plain(self.load())

    def get(self, key: str, default: Any = None) -> Any:
        node: Any = self.load()
        for part in _split(key):
            if not isinstance(node, Mapping) or part not in node:
                return default
            node = node[part]
        return _plain(node)

    # -- write --------------------------------------------------------

    def update(self, changes: Mapping[str, Any]) -> Path | None:
        """Validate + write several keys. Returns the backup path, or None.

        Raises `SettingsError` before writing if any value is invalid or the
        key is not writable. The file is only replaced after everything passed.
        """
        if not changes:
            return None

        validated: dict[str, Any] = {}
        for key, raw in changes.items():
            validated[key] = self._validate(key, raw)

        with self._lock:
            data = self.load()
            changed = False
            for key, value in validated.items():
                if self._get_in(data, key) == value:
                    continue
                self._set_in(data, key, value)
                changed = True
            if not changed:
                return None

            backup = self._backup()
            self._write(data)
            return backup

    def restore(self, backup: Path) -> Path | None:
        """Replace the live file with a backup (current file is backed up first)."""
        source = Path(backup)
        with self._lock:
            if not source.is_file():
                raise SettingsError(f"Backup not found: {source.name}")
            try:
                restored = self._yaml.load(source.read_text(encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001 - shown in the UI
                raise SettingsError(f"Backup is not valid YAML: {exc}") from exc
            if not isinstance(restored, CommentedMap):
                raise SettingsError("Backup must contain a mapping at the top level")

            keep = self._backup() if self._path.is_file() else None
            self._write(restored)
            return keep

    def backups(self) -> list[Path]:
        """Newest first; safe when the folder does not exist yet."""
        if not self._backup_dir.is_dir():
            return []
        files = sorted(
            self._backup_dir.glob("settings-*.yaml"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        return files

    # -- internals ----------------------------------------------------

    def _validate(self, key: str, raw: Any) -> Any:
        checker = _SCHEMA.get(key)
        if checker is None:
            raise SettingsError(f"Settings key is not editable: {key}")
        try:
            return checker(raw)
        except SettingsError as exc:
            raise SettingsError(f"{key}: {exc}") from exc

    @staticmethod
    def _get_in(data: Mapping[str, Any], key: str) -> Any:
        node: Any = data
        for part in _split(key):
            if not isinstance(node, Mapping) or part not in node:
                return None
            node = node[part]
        return _plain(node)

    @staticmethod
    def _set_in(data: CommentedMap, key: str, value: Any) -> None:
        parts = _split(key)
        node: Any = data
        for part in parts[:-1]:
            child = node.get(part)
            if not isinstance(child, CommentedMap):
                child = CommentedMap()
                node[part] = child
            node = child
        node[parts[-1]] = value

    def _backup(self) -> Path | None:
        if not self._path.is_file():
            return None
        self._backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        target = self._backup_dir / f"settings-{stamp}.yaml"
        counter = 1
        while target.exists():
            target = self._backup_dir / f"settings-{stamp}-{counter}.yaml"
            counter += 1
        target.write_bytes(self._path.read_bytes())
        return target

    def _write(self, data: CommentedMap) -> None:
        stream = io.StringIO()
        self._yaml.dump(data, stream)
        text = stream.getvalue()

        self._path.parent.mkdir(parents=True, exist_ok=True)
        temp = self._path.with_name(f".{self._path.name}.{os.getpid()}.tmp")
        try:
            temp.write_text(text, encoding="utf-8", newline=self._newline())
            os.replace(temp, self._path)
        finally:
            temp.unlink(missing_ok=True)

    def _newline(self) -> str:
        """Keep the file's existing line endings (CRLF on Windows checkouts)."""
        if not self._path.is_file():
            return "\n"
        try:
            head = self._path.read_bytes()[:4096]
        except OSError:
            return "\n"
        return "\r\n" if b"\r\n" in head else "\n"
