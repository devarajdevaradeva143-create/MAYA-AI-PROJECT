"""Personal assistant tools for Maya AI.

To-dos and reminders are saved in a **local JSON file** under
``MAYA AI/memory/offline/assistant.json`` (offline memory only — never
``memory/online/``, never the cloud).

Tool layer rule: these functions are **silent**. They return strings/lists
and the CLI (``custom/cli.py``) is the only place that prints them, so the
user never sees duplicate output.

Maya = command only — these functions run when the owner calls them.
"""

from datetime import datetime
import threading

from .store import JsonStore

_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"


def _now() -> str:
    """Current local timestamp used for ``created`` fields."""
    return datetime.now().strftime(_TIMESTAMP_FORMAT)


class PersonalAssistant:
    """Personal assistant: reminders, to-dos, daily schedule.

    Data lives in the offline JSON store and survives process restarts.
    """

    def __init__(self, store: JsonStore | None = None) -> None:
        self.store = store if store is not None else JsonStore()
        # Last loaded snapshot (kept for backwards compatibility).
        self.reminders: list = []
        self.todos: list = []

    # ── Internal persistence ──────────────────────────────────────────
    def _load(self) -> dict:
        """Load the latest data from disk into memory."""
        data = self.store.load()
        self.reminders = list(data.get("reminders", []))
        self.todos = list(data.get("todos", []))
        return data

    def _save(self) -> None:
        """Persist current lists to the local JSON store."""
        # JsonStore.save() returns False on failure instead of raising, so a
        # read-only disk never crashes the CLI. In-memory state stays valid.
        self.store.save({"reminders": self.reminders, "todos": self.todos})

    # ── Reminders ─────────────────────────────────────────────────────
    def set_reminder(self, text: str, time_str: str) -> str:
        """Set a reminder. Saved offline, message returned (not printed)."""
        self._load()
        self.reminders.append(
            {
                "id": _new_id(),
                "text": text,
                "time": time_str,
                "created": _now(),
            }
        )
        self._save()
        return f"Reminder set: '{text}' at {time_str}"

    def list_reminders(self) -> list:
        """Return all reminders."""
        self._load()
        return list(self.reminders)

    # ── To-dos ────────────────────────────────────────────────────────
    def add_todo(self, task: str) -> str:
        """Add a to-do item. Saved offline, message returned (not printed)."""
        self._load()
        self.todos.append(
            {
                "id": _new_id(),
                "task": task,
                "done": False,
                "created": _now(),
            }
        )
        self._save()
        return f"To-do added: '{task}'"

    def list_todos(self) -> list:
        """Return all to-do items."""
        self._load()
        return list(self.todos)

    def complete_todo(self, index: int) -> str:
        """Mark a to-do item as complete by index (1-based)."""
        self._load()
        if index < 1 or index > len(self.todos):
            return f"Invalid to-do index: {index}"
        todo = self.todos[index - 1]
        todo["done"] = True
        self._save()
        return f"To-do marked complete: '{todo['task']}'"

    # ── Schedule ──────────────────────────────────────────────────────
    def set_schedule_item(self, time_str: str, text: str) -> str:
        """Set a daily schedule item at a given time (HH:MM).

        Saved to the offline store. Can be retrieved via
        :meth:`get_daily_schedule`.
        """
        self._load()
        if not hasattr(self, "schedule") or self.schedule is None:
            self.schedule = []
        # Validate time format HH:MM
        try:
            datetime.strptime(time_str, "%H:%M")
        except ValueError:
            return f"Invalid time format: '{time_str}'. Use HH:MM."
        self.schedule.append(
            {
                "id": _new_id(),
                "time": time_str,
                "text": text,
            }
        )
        self._save()
        return f"Schedule set: '{text}' at {time_str} daily"

    def get_daily_schedule(self) -> str:
        """Return today's schedule items sorted by time."""
        self._load()
        schedule = getattr(self, "schedule", []) or []
        if not schedule:
            return "No schedule set yet"
        sorted_items = sorted(schedule, key=lambda x: x.get("time", ""))
        lines = ["Today's schedule:"]
        for item in sorted_items:
            lines.append(f"  {item['time']} — {item['text']}")
        return "\n".join(lines)

    # ── Reminder scheduler ────────────────────────────────────────────

    def _time_matches(self, reminder_time: str) -> bool:
        """Return True if the current HH:MM matches the reminder time."""
        now = datetime.now().strftime("%H:%M")
        return now == reminder_time

    def start_reminder_scheduler(
        self,
        interval: float = 30.0,
        on_reminder: object = None,
    ) -> None:
        """Start a background thread that fires reminders at their set time.

        Runs as a daemon thread. Checks every ``interval`` seconds whether any
        stored reminder's ``time`` matches the current HH:MM. When a match is
        found, calls ``on_reminder(reminder)`` if provided.

        Silent by design — the caller/CLI handles output.
        """
        if getattr(self, "_scheduler_running", False):
            return

        self._scheduler_running = True
        self._scheduler_stop = threading.Event()

        def _run() -> None:
            while not self._scheduler_stop.is_set():
                try:
                    self._load()
                    now_str = datetime.now().strftime("%H:%M")
                    for reminder in self.reminders:
                        if reminder.get("time") == now_str:
                            if callable(on_reminder):
                                on_reminder(reminder)
                except Exception:
                    # Never crash the scheduler thread.
                    pass
                self._scheduler_stop.wait(interval)

        self._scheduler_thread = threading.Thread(target=_run, daemon=True)
        self._scheduler_thread.start()

    def stop_reminder_scheduler(self) -> None:
        """Stop the background reminder scheduler."""
        self._scheduler_running = False
        if getattr(self, "_scheduler_stop", None):
            self._scheduler_stop.set()
        thread = getattr(self, "_scheduler_thread", None)
        if thread and thread.is_alive():
            thread.join(timeout=2)


def _new_id() -> str:
    """Short unique id for a reminder / to-do entry."""
    from uuid import uuid4

    return uuid4().hex


# Module-level default assistant instance (offline JSON only, no cloud).
assistant = PersonalAssistant()

# Convenience wrappers so the module can be used directly too.
def set_reminder(text: str, time_str: str) -> str:
    return assistant.set_reminder(text, time_str)


def list_reminders() -> list:
    return assistant.list_reminders()


def add_todo(task: str) -> str:
    return assistant.add_todo(task)


def list_todos() -> list:
    return assistant.list_todos()


def complete_todo(index: int) -> str:
    return assistant.complete_todo(index)


def get_daily_schedule() -> str:
    return assistant.get_daily_schedule()


def set_schedule_item(time_str: str, text: str) -> str:
    return assistant.set_schedule_item(time_str, text)


def start_reminder_scheduler(interval: float = 30.0, on_reminder=None) -> None:
    assistant.start_reminder_scheduler(interval=interval, on_reminder=on_reminder)


def stop_reminder_scheduler() -> None:
    assistant.stop_reminder_scheduler()


if __name__ == "__main__":
    # Quick self-test — uses a temporary store, never the real memory folder.
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        demo = PersonalAssistant(JsonStore(Path(tmp) / "assistant.json"))
        print(demo.set_reminder("Drink water", "09:00"))
        print(demo.add_todo("Review AGENTS.md"))
        print(demo.add_todo("Test knowledge search"))
        print("Reminders:", demo.list_reminders())
        print("Todos:", demo.list_todos())
        print(demo.complete_todo(1))
        print("Todos after complete:", demo.list_todos())
        print("Schedule:", demo.get_daily_schedule())
