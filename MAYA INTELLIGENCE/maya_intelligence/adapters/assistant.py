"""Assistant adapter — wraps custom.tools.assistant."""

from typing import Any


class MayaIntelError(Exception):
    """Base exception for MAYA INTELLIGENCE adapters."""


def _item_text(item: Any, key: str = "task") -> str:
    """Return human-readable text from a dict/list item."""
    if isinstance(item, dict):
        return str(item.get(key) or item.get("text") or item.get("task") or "")
    return str(item)


class AssistantAdapter:
    """Thin wrapper over custom.tools.assistant."""

    def __init__(self):
        from custom.tools import assistant

        self._assistant = assistant

    def set_reminder(self, text: str, when: str) -> dict[str, Any]:
        """Set a reminder. when: ISO format or natural language."""
        result = self._assistant.set_reminder(text, when)
        reminders = self.list_reminders()
        verified = any(text in _item_text(r, "text") for r in reminders)
        return {"success": verified, "result": result, "verified": verified}

    def list_reminders(self) -> list:
        """List all reminders."""
        return self._assistant.list_reminders()

    def add_todo(self, text: str) -> dict[str, Any]:
        """Add a todo item."""
        result = self._assistant.add_todo(text)
        todos = self.list_todos()
        verified = any(text in _item_text(t, "task") for t in todos)
        return {"success": verified, "result": result, "verified": verified}

    def list_todos(self) -> list:
        """List all todos."""
        return self._assistant.list_todos()

    def complete_todo(self, index: int) -> dict[str, Any]:
        """Complete a todo by index."""
        before = self.list_todos()
        result = self._assistant.complete_todo(index)
        after = self.list_todos()
        # A successful completion marks the item done (list length stays the
        # same) or removes it, depending on the assistant version.
        verified = len(after) < len(before)
        if not verified and 1 <= index <= len(after):
            item = after[index - 1]
            verified = bool(item.get("done")) if isinstance(item, dict) else False
        if not verified:
            verified = "invalid" not in str(result).lower()
        return {"success": True, "result": result, "verified": verified}

    def set_schedule_item(self, time: str, text: str) -> dict[str, Any]:
        """Set a schedule item."""
        result = self._assistant.set_schedule_item(time, text)
        schedule = self.get_daily_schedule()
        verified = text in schedule
        return {"success": verified, "result": result, "verified": verified}

    def get_daily_schedule(self) -> str:
        """Get today's schedule."""
        result = self._assistant.get_daily_schedule()
        if isinstance(result, list):
            return "\n".join(_item_text(item, "text") for item in result)
        return str(result)
