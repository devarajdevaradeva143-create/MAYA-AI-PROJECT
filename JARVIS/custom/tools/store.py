"""Local JSON store for Maya's personal assistant data.

Ithu **offline memory mattum**. To-dos and reminders are saved to
``MAYA AI/memory/offline/assistant.json`` — never to ``memory/online/``
and never to the cloud (AGENTS.md privacy rule).

The storage folder comes from ``settings.yaml`` (``memory.offline``), so
code-la path hardcode pannaadhu. ``memory.offline`` is resolved relative to
the project root, the same way ``custom/config.py`` resolves config paths.

Test override
-------------
Set the environment variable ``MAYA_ASSISTANT_STORE`` to a full JSON file
path (for example ``tmp_path/"assistant.json"``) to redirect every read and
write. The path is resolved on each call, so tests can set/unset the variable
per test with ``monkeypatch.setenv`` + ``monkeypatch.delenv``.

Writes are atomic (temp file + ``os.replace``), parent folders are created
automatically, and a missing/corrupt file simply reads as empty data instead
of crashing.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from ..config import PROJECT_ROOT, load_settings

#: Environment variable used by tests to point the store somewhere harmless.
ENV_STORE_PATH = "MAYA_ASSISTANT_STORE"

#: File name inside the offline memory folder.
STORE_FILENAME = "assistant.json"

#: Folder used when settings.yaml has no memory.offline value.
DEFAULT_OFFLINE_MEMORY = "memory/offline"


def empty_data() -> dict:
    """Return a fresh empty store structure."""
    return {"reminders": [], "todos": []}


def _offline_memory_setting() -> str:
    """Read ``memory.offline`` from settings.yaml (flat fallback included)."""
    settings = load_settings()

    memory = settings.get("memory")
    if isinstance(memory, dict):
        offline = memory.get("offline")
        if offline:
            return str(offline)

    # Fallback for the flat defaults returned by config._default_settings()
    return str(settings.get("memory_offline") or DEFAULT_OFFLINE_MEMORY)


def default_store_path() -> Path:
    """Return the real store path: ``MAYA AI/memory/offline/assistant.json``."""
    memory_dir = Path(_offline_memory_setting())
    if not memory_dir.is_absolute():
        memory_dir = PROJECT_ROOT / "MAYA AI" / memory_dir
    return memory_dir / STORE_FILENAME


def store_path() -> Path:
    """Return the active store path (env override wins over settings)."""
    override = os.environ.get(ENV_STORE_PATH, "").strip()
    if override:
        return Path(override).expanduser()
    return default_store_path()


class JsonStore:
    """Tiny JSON file store. Read/write only, no cloud, no network."""

    def __init__(self, path: Path | str | None = None) -> None:
        self._path = Path(path) if path is not None else None

    @property
    def path(self) -> Path:
        """Resolved path of the JSON file."""
        return self._path if self._path is not None else store_path()

    def load(self) -> dict:
        """Read the store. Missing or corrupt file -> empty structure."""
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except FileNotFoundError:
            return empty_data()
        except (OSError, ValueError, TypeError):
            # Corrupt / unreadable JSON: behave as if nothing is stored yet.
            return empty_data()

        if not isinstance(data, dict):
            return empty_data()

        result = empty_data()
        for key in ("reminders", "todos"):
            items = data.get(key)
            if isinstance(items, list):
                result[key] = [item for item in items if isinstance(item, dict)]
        return result

    def save(self, data: dict) -> bool:
        """Atomically write the store. Returns False if the write failed."""
        payload = empty_data()
        for key in ("reminders", "todos"):
            items = data.get(key)
            if isinstance(items, list):
                payload[key] = items

        tmp_name = ""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_name = tempfile.mkstemp(
                prefix=".assistant-", suffix=".tmp", dir=str(self.path.parent)
            )
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=2, ensure_ascii=False)
                fh.write("\n")
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_name, self.path)
            return True
        except (OSError, ValueError, TypeError):
            if tmp_name:
                try:
                    os.unlink(tmp_name)
                except OSError:
                    pass
            return False


def load_data() -> dict:
    """Convenience helper: load the active store."""
    return JsonStore().load()


def save_data(data: dict) -> bool:
    """Convenience helper: save to the active store."""
    return JsonStore().save(data)
