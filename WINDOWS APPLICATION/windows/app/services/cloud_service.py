"""Gemini cloud adapter for the desktop chat — explicit, opt-in only.

`custom.tools.cloud` is the single place that talks to the internet; this
adapter only shapes it for the UI and enforces the project rules:

- nothing is sent until the user switches the local engine off (or confirms
  "Send to Gemini" when the local engine fails);
- only the current message is sent (no offline history, no memory files);
- `cloud.system_prompt` is sent as Gemini's systemInstruction, editable in
  Settings → AI Engine;
- the key is read by `custom.tools.cloud` from `.env`, never logged here;
- `cloud.enabled: false` in settings.yaml makes every call refuse.

Qt-free: the chat page drives this from a worker thread.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any


class CloudUnavailableError(RuntimeError):
    """Cloud is not usable (no key, or disabled in settings.yaml)."""


class CloudAdapter:
    """Thin wrapper around `custom.tools.cloud` (same shape as EngineAdapter)."""

    def __init__(self, tools: Any | None = None, settings: Any | None = None) -> None:
        if tools is None:
            from custom.tools import cloud as cloud_tools

            tools = cloud_tools
        self._tools = tools
        self._settings = settings

    # -- status -------------------------------------------------------

    def _status(self) -> dict[str, Any]:
        try:
            data = self._tools.status()
        except Exception:  # noqa: BLE001 - status must never crash the UI
            return {}
        return data if isinstance(data, dict) else {}

    @property
    def configured(self) -> bool:
        """A key is stored in `.env` / the environment."""
        return bool(self._status().get("configured"))

    @property
    def enabled(self) -> bool:
        """`cloud.enabled` in settings.yaml (defaults to true)."""
        try:
            return bool(self._tools.enabled())
        except Exception:  # noqa: BLE001 - a broken config must not enable cloud
            return False

    @property
    def available(self) -> bool:
        return self.enabled and self.configured

    @property
    def model(self) -> str:
        try:
            return str(self._tools.model_name())
        except Exception:  # noqa: BLE001
            return ""

    @property
    def system_prompt(self) -> str:
        """`cloud.system_prompt` — the instruction sent with every request."""
        if self._settings is None:
            return ""
        try:
            return str(self._settings.get("cloud.system_prompt", "") or "").strip()
        except Exception:  # noqa: BLE001 - a broken config must not block chat
            return ""

    def status(self) -> dict[str, Any]:
        """Honest status for the settings card (never includes the key)."""
        data = self._status()
        return {
            "available": self.available,
            "configured": bool(data.get("configured")),
            "enabled": self.enabled,
            "key_preview": data.get("key_preview"),
            "model": data.get("model") or self.model,
            "endpoint": data.get("endpoint") or "",
            "env_file": data.get("env_file") or "",
        }

    def save_api_key(self, key: str) -> dict[str, Any]:
        """Store `GEMINI_API_KEY` in the project `.env` (value never echoed)."""
        try:
            result = self._tools.save_api_key(key)
        except Exception as exc:  # noqa: BLE001 - shown in the settings card
            return {"ok": False, "error": str(exc)}
        return result if isinstance(result, dict) else {"ok": False, "error": "Unknown error"}

    # -- generation ---------------------------------------------------

    def ask(self, text: str) -> str:
        """Send one message (only that message) and return the reply."""
        if not self.enabled:
            raise CloudUnavailableError("Cloud is disabled in settings.yaml (cloud.enabled: false)")
        if not self.configured:
            raise CloudUnavailableError("No Gemini API key saved. Add one in Settings → Cloud AI.")
        system = self.system_prompt
        kwargs = {"system": system} if system else {}
        try:
            reply = self._tools.ask(text, **kwargs)
        except Exception as exc:  # noqa: BLE001 - cloud errors are shown as text
            raise CloudUnavailableError(str(exc) or type(exc).__name__) from exc
        reply = str(reply).strip()
        if not reply:
            raise CloudUnavailableError("Gemini returned an empty reply")
        try:
            self._tools.log_exchange(text, reply)
        except Exception:  # noqa: BLE001 - the online log is best-effort
            pass
        return reply

    def chat_stream(self, text: str) -> Iterator[str]:
        """Gemini has no streaming here: the whole reply is one chunk."""
        yield self.ask(text)
