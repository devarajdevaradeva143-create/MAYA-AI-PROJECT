"""Persona-aware chat with local history and streaming (plan 12.2).

Qt-free: the chat page drives it from a worker thread. History is the existing
offline `ChatHistory` store (`MAYA AI\\memory\\offline\\chat_history.json`),
never the online one.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from custom.persona.loader import load_persona
from custom.tools.chat_history import ChatHistory

PERSONAS: dict[str, str] = {
    "maya": "girlfriend",
    "teacher": "english_teacher",
}

PERSONA_LABELS: dict[str, str] = {
    "maya": "Maya",
    "teacher": "English Teacher",
}

HISTORY_KEEP = 19
MAX_INPUT_CHARS = 4000


class ChatError(RuntimeError):
    """Chat failed in a way the UI should show as a banner."""


class ChatService:
    """One conversation, one persona, persisted locally after every reply."""

    def __init__(
        self,
        engine: Any,
        history_path: Path | str | None = None,
        persona_loader: Callable[[str], str] | None = None,
        intelligence: Any | None = None,
        cloud: Any | None = None,
        settings: Any | None = None,
    ) -> None:
        self._engine = engine
        self._cloud = cloud
        self._settings = settings
        self._history = ChatHistory(history_path)
        self._loader = persona_loader or load_persona
        self._lock = threading.RLock()
        self._cancel = threading.Event()

        self._persona = self._key_for(self._history.persona)
        self._intelligence = intelligence
        if self._intelligence is not None:
            try:
                self._intelligence.set_persona(self._loader(PERSONAS[self._persona]))
            except Exception:
                pass
        self._ensure_system()

    # -- persona ------------------------------------------------------

    @property
    def persona(self) -> str:
        return self._persona

    @property
    def engine(self) -> Any:
        return self._engine

    @property
    def persona_label(self) -> str:
        return PERSONA_LABELS.get(self._persona, PERSONA_LABELS["maya"])

    @property
    def model(self) -> str:
        return str(getattr(self._engine, "model", "") or "")

    # -- cloud (Gemini) -----------------------------------------------

    @property
    def engine_enabled(self) -> bool:
        """`engine.enabled` in settings.yaml (defaults to true)."""
        if self._settings is None:
            return True
        try:
            return bool(self._settings.get("engine.enabled", True))
        except Exception:  # noqa: BLE001 - a broken config must not block chat
            return True

    def _require_local_engine(self) -> None:
        if not self.engine_enabled:
            raise ChatError("Lemonade (local engine) is turned off in Settings → AI Engine.")

    @property
    def cloud_available(self) -> bool:
        """True when a key is saved and `cloud.enabled` is not false."""
        return bool(getattr(self._cloud, "available", False))

    @property
    def cloud_enabled(self) -> bool:
        """`cloud.enabled` in settings.yaml (defaults to true)."""
        return bool(getattr(self._cloud, "enabled", True))

    @property
    def cloud_configured(self) -> bool:
        """A Gemini key is stored in `.env` / the environment."""
        return bool(getattr(self._cloud, "configured", False))

    @property
    def cloud_model(self) -> str:
        return str(getattr(self._cloud, "model", "") or "")

    @staticmethod
    def _key_for(history_name: str) -> str:
        for key, name in PERSONAS.items():
            if name == history_name:
                return key
        return "maya"

    def set_persona(self, key: str) -> None:
        """Switch persona; the history is cleared (existing ChatHistory rule)."""
        if key not in PERSONAS:
            raise ValueError(f"Unknown persona: {key}")
        with self._lock:
            self._persona = key
            self._history.set_persona(PERSONAS[key])
            self._ensure_system()
            if self._intelligence is not None:
                try:
                    self._intelligence.set_persona(self._loader(PERSONAS[key]))
                    self._intelligence.clear()
                except Exception:
                    pass

    def new_chat(self) -> None:
        """Clear the conversation but keep the current persona."""
        with self._lock:
            self._history.set_persona(PERSONAS[self._persona])
            self._ensure_system()
            if self._intelligence is not None:
                try:
                    self._intelligence.clear()
                except Exception:
                    pass

    def _ensure_system(self) -> None:
        if any(item.get("role") == "system" for item in self._history.get_messages()):
            return
        prompt = self._loader(PERSONAS[self._persona])
        if prompt.strip():
            self._history.set_system(prompt)

    # -- messages -----------------------------------------------------

    def messages(self) -> list[dict[str, str]]:
        """Conversation without the system prompt (what the UI shows)."""
        with self._lock:
            return [
                dict(item)
                for item in self._history.get_messages()
                if item.get("role") != "system"
            ]

    def _context(self, text: str) -> list[dict[str, str]]:
        stored = self._history.get_messages()
        system = [item for item in stored if item.get("role") == "system"]
        others = [item for item in stored if item.get("role") != "system"][-HISTORY_KEEP:]
        return [dict(item) for item in system + others] + [{"role": "user", "content": text}]

    @staticmethod
    def _prepare(text: str) -> str:
        cleaned = (text or "").strip()
        if not cleaned:
            raise ChatError("Message is empty")
        if len(cleaned) > MAX_INPUT_CHARS:
            raise ChatError(f"Message is longer than {MAX_INPUT_CHARS} characters")
        return cleaned

    def _record(self, text: str, reply: str) -> None:
        with self._lock:
            self._history.add_user(text)
            self._history.add_assistant(reply)
            self._history.trim(HISTORY_KEEP)

    # -- generation ---------------------------------------------------

    def send(self, text: str) -> str:
        """Non-streaming call (used by tests/tools)."""
        cleaned = self._prepare(text)
        self._require_local_engine()
        if self._intelligence is not None:
            reply = self._intelligence.chat(cleaned)
            reply = str(reply).strip()
            if reply:
                self._record(cleaned, reply)
            return reply
        with self._lock:
            self._cancel.clear()
            messages = self._context(cleaned)
        reply = self._engine.chat(messages)
        reply = str(reply).strip()
        if reply:
            self._record(cleaned, reply)
        return reply

    def stream(self, text: str) -> Iterator[str]:
        """Yield chunks; history is saved only when the reply finishes."""
        cleaned = self._prepare(text)
        self._require_local_engine()
        if self._intelligence is not None:
            reply = self._intelligence.chat(cleaned)
            reply = str(reply).strip()
            if reply:
                self._record(cleaned, reply)
                yield reply
            return
        with self._lock:
            self._cancel.clear()
            messages = self._context(cleaned)

        parts: list[str] = []
        for chunk in self._engine.chat_stream(messages):
            if self._cancel.is_set():
                return
            piece = str(chunk)
            parts.append(piece)
            yield piece

        if self._cancel.is_set():
            return
        reply = "".join(parts).strip()
        if reply:
            self._record(cleaned, reply)

    def stream_cloud(self, text: str) -> Iterator[str]:
        """Explicit cloud reply: only this message leaves the laptop.

        The user must have confirmed in the UI — this method sends right away,
        so offline history is deliberately not attached.
        """
        cleaned = self._prepare(text)
        if self._cloud is None:
            raise ChatError("Cloud AI is not configured")
        with self._lock:
            self._cancel.clear()
        reply = ""
        for chunk in self._cloud.chat_stream(cleaned):
            if self._cancel.is_set():
                return
            reply += str(chunk)
            yield str(chunk)
        reply = reply.strip()
        if reply:
            self._record(cleaned, reply)

    def cancel(self) -> None:
        """Ask the running stream to stop; the partial reply is not saved."""
        self._cancel.set()

    @property
    def was_cancelled(self) -> bool:
        return self._cancel.is_set()
