"""Chat history persistence — offline memory only.

Saves Maya conversations to ``MAYA AI/memory/offline/chat_history.json``
(never to ``memory/online/``, never to the cloud).

Tool layer rule: this class is **silent**. It returns data and the CLI
(``custom/cli.py``) is the only place that prints.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from ..config import PROJECT_ROOT, load_settings


ENV_CHAT_HISTORY = "MAYA_CHAT_HISTORY"
DEFAULT_OFFLINE_MEMORY = "memory/offline"
CHAT_HISTORY_FILENAME = "chat_history.json"


def _history_path() -> Path:
    """Resolve the chat history JSON path from settings.yaml (offline only)."""
    override = os.environ.get(ENV_CHAT_HISTORY, "").strip()
    if override:
        return Path(override).expanduser()

    settings = load_settings()
    memory = settings.get("memory", {}) if isinstance(settings, dict) else {}
    offline = memory.get("offline", DEFAULT_OFFLINE_MEMORY)
    dir_path = Path(offline)
    if not dir_path.is_absolute():
        dir_path = PROJECT_ROOT / "MAYA AI" / dir_path
    return dir_path / CHAT_HISTORY_FILENAME


class ChatHistory:
    """Persisted chat history with persona.

    Lives in offline JSON only. Survives process restarts.
    """

    def __init__(self, path: Path | str | None = None) -> None:
        self._path = Path(path) if path is not None else _history_path()
        self.persona: str = "girlfriend"
        self.messages: list[dict[str, str]] = []
        self._load()

    # ── Internal persistence ────────────────────────────────────────
    def _load(self) -> None:
        """Load history from disk. Missing/corrupt file -> empty."""
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.persona = str(data.get("persona", "girlfriend"))
            self.messages = [
                m
                for m in data.get("messages", [])
                if isinstance(m, dict)
                and "role" in m
                and "content" in m
            ]
        except (FileNotFoundError, OSError, ValueError, TypeError):
            self.persona = "girlfriend"
            self.messages = []

    def save(self) -> None:
        """Persist current persona + messages to the local JSON store."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(
                {"persona": self.persona, "messages": self.messages},
                f,
                indent=2,
                ensure_ascii=False,
            )
        os.replace(tmp, self._path)

    # ── Persona ─────────────────────────────────────────────────────
    def set_persona(self, name: str) -> None:
        """Switch persona and clear history."""
        self.persona = name
        self.messages = []
        self.save()

    # ── Messages ────────────────────────────────────────────────────
    def get_messages(self) -> list[dict[str, str]]:
        """Return a copy of the current message list."""
        return list(self.messages)

    def set_system(self, content: str) -> None:
        """Replace the system message (insert at front, remove old one)."""
        self.messages = [m for m in self.messages if m.get("role") != "system"]
        self.messages.insert(0, {"role": "system", "content": content})
        self.save()

    def add_user(self, content: str) -> None:
        """Append a user message."""
        self.messages.append({"role": "user", "content": content})
        self.save()

    def add_assistant(self, content: str) -> None:
        """Append an assistant message."""
        self.messages.append({"role": "assistant", "content": content})
        self.save()

    def trim(self, keep: int = 19) -> None:
        """Keep system message + last ``keep`` non-system messages."""
        system_msgs = [m for m in self.messages if m.get("role") == "system"]
        other_msgs = [m for m in self.messages if m.get("role") != "system"][-keep:]
        self.messages = system_msgs + other_msgs
        self.save()
