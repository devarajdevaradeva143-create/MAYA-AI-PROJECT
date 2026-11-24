"""Action Intelligence (AQ) engine — intent→tool, confirm, execute, verify."""

import re
from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class AQResult:
    success: bool
    result: Any
    verified: bool
    message: str


class AQEngine:
    """Action Intelligence — maps intent to tools, handles confirmation, executes, verifies."""

    def __init__(
        self,
        pc_adapter,
        assistant_adapter,
        knowledge_adapter,
        monitor_adapter=None,
        confirm_fn: Callable[[str], bool] = None,
    ):
        self._pc = pc_adapter
        self._assistant = assistant_adapter
        self._knowledge = knowledge_adapter
        self._monitor = monitor_adapter
        self._confirm = confirm_fn or (lambda msg: True)

        # Wire permission gate for pc_control
        self._wire_permission_gate()

    def _wire_permission_gate(self):
        """Set the permission gate on pc_control to use our confirm function."""
        try:
            from custom.tools import pc_control
            pc_control.set_permission_gate(self._confirm)
        except Exception:
            pass  # pc_control may not have set_permission_gate in all versions

    def execute(self, intent: str, params: dict[str, Any] = None) -> AQResult:
        """Execute an action based on intent."""
        params = params or {}
        intent_lower = intent.lower()

        # Direct intent mapping (for programmatic use)
        intent_map = {
            "open_app": self._handle_open_app,
            "close_app": self._handle_close_app,
            "search_files": self._handle_search_files,
            "read_file": self._handle_read_file,
            "create_folder": self._handle_create_folder,
            "delete_file": self._handle_delete_file,
            "edit_file": self._handle_edit_file,
            "run_command": self._handle_run_command,
            "todo": self._handle_todo,
            "reminder": self._handle_reminder,
            "schedule": self._handle_schedule,
            "monitor": self._handle_monitor,
            "knowledge": self._handle_knowledge,
        }

        if intent_lower in intent_map:
            return intent_map[intent_lower](params)

        # Fast-path heuristics for natural language commands
        if self._is_open_app(intent_lower):
            return self._handle_open_app(params)
        if self._is_close_app(intent_lower):
            return self._handle_close_app(params)
        if self._is_search_files(intent_lower):
            return self._handle_search_files(params)
        if self._is_read_file(intent_lower):
            return self._handle_read_file(params)
        if self._is_create_folder(intent_lower):
            return self._handle_create_folder(params)
        if self._is_delete_file(intent_lower):
            return self._handle_delete_file(params)
        if self._is_edit_file(intent_lower):
            return self._handle_edit_file(params)
        if self._is_run_command(intent_lower):
            return self._handle_run_command(params)
        if self._is_todo(intent_lower):
            return self._handle_todo(params)
        if self._is_reminder(intent_lower):
            return self._handle_reminder(params)
        if self._is_schedule(intent_lower):
            return self._handle_schedule(params)
        if self._is_monitor(intent_lower):
            return self._handle_monitor(params)
        if self._is_knowledge(intent_lower):
            return self._handle_knowledge(params)

        # Unknown intent
        return AQResult(
            success=False,
            result=None,
            verified=False,
            message=f"Unknown action: {intent}",
        )

    # Intent detection heuristics
    def _is_open_app(self, text: str) -> bool:
        return bool(re.search(r"\b(open|launch|start|run)\b.*\b(app|application|program|software)\b", text)) or \
               bool(re.search(r"\b(open|launch)\b", text))

    def _is_close_app(self, text: str) -> bool:
        return bool(re.search(r"\b(close|quit|exit|stop|kill)\b.*\b(app|application|program)\b", text))

    def _is_search_files(self, text: str) -> bool:
        return bool(re.search(r"\b(search|find|look for)\b.*\b(file|folder|document)\b", text))

    def _is_read_file(self, text: str) -> bool:
        return bool(re.search(r"\b(read|show|display|cat|view)\b.*\b(file)\b", text))

    def _is_create_folder(self, text: str) -> bool:
        return bool(re.search(r"\b(create|make|new)\b.*\b(folder|directory)\b", text))

    def _is_delete_file(self, text: str) -> bool:
        return bool(re.search(r"\b(delete|remove|rm)\b.*\b(file|folder)\b", text))

    def _is_edit_file(self, text: str) -> bool:
        return bool(re.search(r"\b(edit|modify|change|update)\b.*\b(file)\b", text))

    def _is_run_command(self, text: str) -> bool:
        return bool(re.search(r"\b(run|execute|cmd|command|shell)\b", text))

    def _is_todo(self, text: str) -> bool:
        return bool(re.search(r"\b(todo|task|add.*todo)\b", text))

    def _is_reminder(self, text: str) -> bool:
        return bool(re.search(r"\b(remind|reminder|alert)\b", text))

    def _is_schedule(self, text: str) -> bool:
        return bool(re.search(r"\b(schedule|calendar|appointment)\b", text))

    def _is_monitor(self, text: str) -> bool:
        return bool(re.search(r"\b(monitor|system|status|cpu|memory|disk)\b", text))

    def _is_knowledge(self, text: str) -> bool:
        return bool(re.search(r"\b(index|rag|knowledge|search.*knowledge)\b", text))

    # Handlers
    def _handle_open_app(self, params: dict) -> AQResult:
        name = params.get("name") or params.get("app")
        if not name:
            return AQResult(False, None, False, "App name required")
        msg = f"Open '{name}'?"
        if not self._confirm(msg):
            return AQResult(False, None, False, "Cancelled by user")
        result = self._pc.open_app(name, confirm=False)
        return AQResult(
            success=result["success"],
            result=result["result"],
            verified=result["verified"],
            message=f"Opened {name}" if result["verified"] else f"Failed to open {name}",
        )

    def _handle_close_app(self, params: dict) -> AQResult:
        name = params.get("name") or params.get("app")
        if not name:
            return AQResult(False, None, False, "App name required")
        msg = f"Close '{name}'?"
        if not self._confirm(msg):
            return AQResult(False, None, False, "Cancelled by user")
        result = self._pc.close_app(name, confirm=False)
        return AQResult(
            success=result["success"],
            result=result["result"],
            verified=result["verified"],
            message=f"Closed {name}" if result["verified"] else f"Failed to close {name}",
        )

    def _handle_search_files(self, params: dict) -> AQResult:
        query = params.get("query") or params.get("q")
        root = params.get("root")
        if not query:
            return AQResult(False, None, False, "Search query required")
        results = self._knowledge.search_files(query, root)
        return AQResult(True, results, True, f"Found {len(results)} results")

    def _handle_read_file(self, params: dict) -> AQResult:
        path = params.get("path") or params.get("file")
        if not path:
            return AQResult(False, None, False, "File path required")
        try:
            result = self._pc.read_file(path)
            return AQResult(True, result["content"], True, "File read successfully")
        except Exception as e:
            return AQResult(False, None, False, str(e))

    def _handle_create_folder(self, params: dict) -> AQResult:
        path = params.get("path") or params.get("folder")
        if not path:
            return AQResult(False, None, False, "Folder path required")
        msg = f"Create folder '{path}'?"
        if not self._confirm(msg):
            return AQResult(False, None, False, "Cancelled by user")
        result = self._pc.create_folder(path, confirm=False)
        return AQResult(
            success=result["success"],
            result=result["result"],
            verified=result["verified"],
            message=result["result"],
        )

    def _handle_delete_file(self, params: dict) -> AQResult:
        path = params.get("path") or params.get("file")
        if not path:
            return AQResult(False, None, False, "File path required")
        msg = f"Delete '{path}'? This cannot be undone."
        if not self._confirm(msg):
            return AQResult(False, None, False, "Cancelled by user")
        result = self._pc.delete_file(path, confirm=False)
        return AQResult(
            success=result["success"],
            result=result["result"],
            verified=result["verified"],
            message=result["result"],
        )

    def _handle_edit_file(self, params: dict) -> AQResult:
        path = params.get("path") or params.get("file")
        old_text = params.get("old_text")
        new_text = params.get("new_text")
        if not path or old_text is None or new_text is None:
            return AQResult(False, None, False, "Path, old_text, and new_text required")
        msg = f"Edit '{path}'?"
        if not self._confirm(msg):
            return AQResult(False, None, False, "Cancelled by user")
        result = self._pc.edit_file(path, old_text, new_text, confirm=False)
        return AQResult(
            success=result["success"],
            result=result["result"],
            verified=result["verified"],
            message=result["result"],
        )

    def _handle_run_command(self, params: dict) -> AQResult:
        command = params.get("command") or params.get("cmd")
        if not command:
            return AQResult(False, None, False, "Command required")
        msg = f"Run command: {command}?"
        if not self._confirm(msg):
            return AQResult(False, None, False, "Cancelled by user")
        result = self._pc.run_command(command, confirm=False)
        return AQResult(
            success=result["success"],
            result=result["result"],
            verified=result["verified"],
            message=result["result"],
        )

    def _handle_todo(self, params: dict) -> AQResult:
        action = params.get("action", "add")
        if action == "add":
            text = params.get("text")
            if not text:
                return AQResult(False, None, False, "Todo text required")
            result = self._assistant.add_todo(text)
            return AQResult(
                success=result["success"],
                result=result["result"],
                verified=result["verified"],
                message="Todo added" if result["verified"] else "Failed to add todo",
            )
        elif action == "list":
            todos = self._assistant.list_todos()
            return AQResult(True, todos, True, f"{len(todos)} todos")
        elif action == "complete":
            index = params.get("index")
            if index is None:
                return AQResult(False, None, False, "Index required")
            result = self._assistant.complete_todo(index)
            return AQResult(True, result["result"], True, "Todo completed")
        return AQResult(False, None, False, f"Unknown todo action: {action}")

    def _handle_reminder(self, params: dict) -> AQResult:
        action = params.get("action", "add")
        if action == "add":
            text = params.get("text")
            when = params.get("when")
            if not text or not when:
                return AQResult(False, None, False, "Text and when required")
            result = self._assistant.set_reminder(text, when)
            return AQResult(
                success=result["success"],
                result=result["result"],
                verified=result["verified"],
                message="Reminder set" if result["verified"] else "Failed to set reminder",
            )
        elif action == "list":
            reminders = self._assistant.list_reminders()
            return AQResult(True, reminders, True, f"{len(reminders)} reminders")
        return AQResult(False, None, False, f"Unknown reminder action: {action}")

    def _handle_schedule(self, params: dict) -> AQResult:
        time = params.get("time")
        text = params.get("text")
        if not time or not text:
            return AQResult(False, None, False, "Time and text required")
        result = self._assistant.set_schedule_item(time, text)
        return AQResult(
            success=result["success"],
            result=result["result"],
            verified=result["verified"],
            message="Schedule item set" if result["verified"] else "Failed to set schedule",
        )

    def _handle_monitor(self, params: dict) -> AQResult:
        if self._monitor:
            try:
                report = self._monitor.get_full_report()
                return AQResult(True, report, True, "System report retrieved")
            except Exception as e:
                return AQResult(False, None, False, str(e))
        return AQResult(False, None, False, "Monitor not available")

    def _handle_knowledge(self, params: dict) -> AQResult:
        action = params.get("action", "search")
        if action == "search":
            query = params.get("query")
            if not query:
                return AQResult(False, None, False, "Query required")
            results = self._knowledge.knowledge_search(query)
            return AQResult(True, results, True, f"Found {len(results)} results")
        elif action == "index":
            paths = params.get("paths", [])
            if not paths:
                return AQResult(False, None, False, "Paths required")
            result = self._knowledge.index_documents(paths)
            return AQResult(True, result, True, "Documents indexed")
        return AQResult(False, None, False, f"Unknown knowledge action: {action}")