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
        screen_adapter=None,
        system_adapter=None,
        browser_adapter=None,
        files_adapter=None,
        office_adapter=None,
        confirm_fn: Callable[[str], bool] | None = None,
    ):
        self._pc = pc_adapter
        self._assistant = assistant_adapter
        self._knowledge = knowledge_adapter
        self._monitor = monitor_adapter
        self._screen = screen_adapter
        self._system = system_adapter
        self._browser = browser_adapter
        self._files = files_adapter
        self._office = office_adapter
        # Secure default: without an explicit confirmation callback,
        # destructive actions are denied instead of auto-approved.
        self._confirm = confirm_fn or (lambda msg: False)

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
            # Screen control
            "screenshot": self._handle_screenshot,
            "screen_size": self._handle_screen_size,
            "mouse_move": self._handle_mouse_move,
            "mouse_click": self._handle_mouse_click,
            "mouse_scroll": self._handle_mouse_scroll,
            "keyboard_type": self._handle_keyboard_type,
            "press_key": self._handle_press_key,
            # System control
            "get_volume": self._handle_get_volume,
            "set_volume": self._handle_set_volume,
            "mute_toggle": self._handle_mute_toggle,
            "get_brightness": self._handle_get_brightness,
            "set_brightness": self._handle_set_brightness,
            "lock_screen": self._handle_lock_screen,
            "sleep_pc": self._handle_sleep_pc,
            "shutdown_pc": self._handle_shutdown_pc,
            "restart_pc": self._handle_restart_pc,
            "cancel_shutdown": self._handle_cancel_shutdown,
            # Clipboard
            "read_clipboard": self._handle_read_clipboard,
            "write_clipboard": self._handle_write_clipboard,
            # Window
            "list_windows": self._handle_list_windows,
            "focus_window": self._handle_focus_window,
            "minimize_all": self._handle_minimize_all,
            "close_window": self._handle_close_window,
            # Process
            "list_processes": self._handle_list_processes,
            "kill_process": self._handle_kill_process,
            "set_priority": self._handle_set_priority,
            # Browser
            "open_url": self._handle_open_url,
            "search_web": self._handle_search_web,
            "fetch_page": self._handle_fetch_page,
            # Files advanced
            "move_file": self._handle_move_file,
            "copy_file": self._handle_copy_file,
            "rename_file": self._handle_rename_file,
            "zip_path": self._handle_zip_path,
            "unzip_path": self._handle_unzip_path,
            "search_content": self._handle_search_content,
            # Office
            "excel_write": self._handle_excel_write,
            "excel_read": self._handle_excel_read,
            "word_create_doc": self._handle_word_create_doc,
            "word_add_text": self._handle_word_add_text,
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
    # ---- Screen control handlers ----
    def _handle_screenshot(self, params: dict) -> AQResult:
        if not self._screen:
            return AQResult(False, None, False, "Screen adapter not available")
        result = self._screen.screenshot(params.get("path"))
        return AQResult(success=result.get("success", False), result=result.get("path", ""),
                       verified=result.get("verified", False), message="Screenshot captured")

    def _handle_screen_size(self, params: dict) -> AQResult:
        if not self._screen:
            return AQResult(False, None, False, "Screen adapter not available")
        result = self._screen.get_screen_size()
        return AQResult(True, result, True, "Screen size retrieved")

    def _handle_mouse_move(self, params: dict) -> AQResult:
        if not self._screen:
            return AQResult(False, None, False, "Screen adapter not available")
        x = params.get("x", 0); y = params.get("y", 0)
        result = self._screen.mouse_move(x, y)
        return AQResult(success=result.get("success", False), result=result.get("result", ""),
                       verified=result.get("verified", False), message=result.get("result", ""))

    def _handle_mouse_click(self, params: dict) -> AQResult:
        if not self._screen:
            return AQResult(False, None, False, "Screen adapter not available")
        result = self._screen.mouse_click(params.get("x"), params.get("y"),
                                         params.get("button", "left"), params.get("clicks", 1))
        return AQResult(success=result.get("success", False), result=result.get("result", ""),
                       verified=result.get("verified", False), message=result.get("result", ""))

    def _handle_mouse_scroll(self, params: dict) -> AQResult:
        if not self._screen:
            return AQResult(False, None, False, "Screen adapter not available")
        result = self._screen.mouse_scroll(params.get("amount", 0))
        return AQResult(success=result.get("success", False), result=result.get("result", ""),
                       verified=result.get("verified", False), message=result.get("result", ""))

    def _handle_keyboard_type(self, params: dict) -> AQResult:
        if not self._screen:
            return AQResult(False, None, False, "Screen adapter not available")
        text = params.get("text", "")
        if not text:
            return AQResult(False, None, False, "Text required")
        result = self._screen.keyboard_type(text)
        return AQResult(success=result.get("success", False), result=result.get("result", ""),
                       verified=result.get("verified", False), message=result.get("result", ""))

    def _handle_press_key(self, params: dict) -> AQResult:
        if not self._screen:
            return AQResult(False, None, False, "Screen adapter not available")
        key = params.get("key", "")
        if not key:
            return AQResult(False, None, False, "Key required")
        result = self._screen.press_key(key)
        return AQResult(success=result.get("success", False), result=result.get("result", ""),
                       verified=result.get("verified", False), message=result.get("result", ""))

    # ---- System control handlers ----
    def _handle_get_volume(self, params: dict) -> AQResult:
        if not self._system:
            return AQResult(False, None, False, "System adapter not available")
        return AQResult(True, self._system.get_volume(), True, "Volume retrieved")

    def _handle_set_volume(self, params: dict) -> AQResult:
        if not self._system:
            return AQResult(False, None, False, "System adapter not available")
        level = params.get("level", params.get("value", 50))
        result = self._system.set_volume(level)
        return AQResult(success=result.get("success", False), result=result.get("result", ""),
                       verified=result.get("verified", False), message=result.get("result", ""))

    def _handle_mute_toggle(self, params: dict) -> AQResult:
        if not self._system:
            return AQResult(False, None, False, "System adapter not available")
        result = self._system.mute_toggle()
        return AQResult(success=result.get("success", False), result=result.get("result", ""),
                       verified=result.get("verified", False), message=result.get("result", ""))

    def _handle_get_brightness(self, params: dict) -> AQResult:
        if not self._system:
            return AQResult(False, None, False, "System adapter not available")
        return AQResult(True, self._system.get_brightness(), True, "Brightness retrieved")

    def _handle_set_brightness(self, params: dict) -> AQResult:
        if not self._system:
            return AQResult(False, None, False, "System adapter not available")
        level = params.get("level", params.get("value", 50))
        result = self._system.set_brightness(level)
        return AQResult(success=result.get("success", False), result=result.get("result", ""),
                       verified=result.get("verified", False), message=result.get("result", ""))

    def _handle_lock_screen(self, params: dict) -> AQResult:
        if not self._system:
            return AQResult(False, None, False, "System adapter not available")
        result = self._system.lock_workstation()
        return AQResult(success=result.get("success", False), result=result.get("result", ""),
                       verified=result.get("verified", False), message=result.get("result", ""))

    def _handle_sleep_pc(self, params: dict) -> AQResult:
        if not self._system:
            return AQResult(False, None, False, "System adapter not available")
        result = self._system.sleep_pc()
        return AQResult(success=result.get("success", False), result=result.get("result", ""),
                       verified=result.get("verified", False), message=result.get("result", ""))

    def _handle_shutdown_pc(self, params: dict) -> AQResult:
        if not self._system:
            return AQResult(False, None, False, "System adapter not available")
        result = self._system.shutdown_pc()
        return AQResult(success=result.get("success", False), result=result.get("result", ""),
                       verified=result.get("verified", False), message=result.get("result", ""))

    def _handle_restart_pc(self, params: dict) -> AQResult:
        if not self._system:
            return AQResult(False, None, False, "System adapter not available")
        result = self._system.restart_pc()
        return AQResult(success=result.get("success", False), result=result.get("result", ""),
                       verified=result.get("verified", False), message=result.get("result", ""))

    def _handle_cancel_shutdown(self, params: dict) -> AQResult:
        if not self._system:
            return AQResult(False, None, False, "System adapter not available")
        result = self._system.cancel_shutdown()
        return AQResult(success=True, result=result.get("result", ""), verified=True,
                       message=result.get("result", ""))

    # ---- Clipboard handlers ----
    def _handle_read_clipboard(self, params: dict) -> AQResult:
        if not self._system:
            return AQResult(False, None, False, "System adapter not available")
        content = self._system.read_clipboard()
        return AQResult(True, content, True, "Clipboard read")

    def _handle_write_clipboard(self, params: dict) -> AQResult:
        if not self._system:
            return AQResult(False, None, False, "System adapter not available")
        text = params.get("text", "")
        if not text:
            return AQResult(False, None, False, "Text required")
        result = self._system.write_clipboard(text)
        return AQResult(success=result.get("success", False), result=result.get("result", ""),
                       verified=result.get("verified", False), message=result.get("result", ""))

    # ---- Window handlers ----
    def _handle_list_windows(self, params: dict) -> AQResult:
        if not self._system:
            return AQResult(False, None, False, "System adapter not available")
        windows = self._system.list_windows()
        return AQResult(True, windows, True, f"{len(windows)} windows")

    def _handle_focus_window(self, params: dict) -> AQResult:
        if not self._system:
            return AQResult(False, None, False, "System adapter not available")
        title = params.get("title", params.get("name", ""))
        if not title:
            return AQResult(False, None, False, "Window title required")
        result = self._system.focus_window(title)
        return AQResult(success=result.get("success", False), result=result.get("result", ""),
                       verified=result.get("verified", False), message=result.get("result", ""))

    def _handle_minimize_all(self, params: dict) -> AQResult:
        if not self._system:
            return AQResult(False, None, False, "System adapter not available")
        result = self._system.minimize_all()
        return AQResult(success=result.get("success", False), result=result.get("result", ""),
                       verified=result.get("verified", False), message=result.get("result", ""))

    def _handle_close_window(self, params: dict) -> AQResult:
        if not self._system:
            return AQResult(False, None, False, "System adapter not available")
        title = params.get("title", params.get("name", ""))
        if not title:
            return AQResult(False, None, False, "Window title required")
        result = self._system.close_window(title)
        return AQResult(success=result.get("success", False), result=result.get("result", ""),
                       verified=result.get("verified", False), message=result.get("result", ""))

    # ---- Process handlers ----
    def _handle_list_processes(self, params: dict) -> AQResult:
        if not self._system:
            return AQResult(False, None, False, "System adapter not available")
        procs = self._system.list_processes(params.get("filter", params.get("name", "")))
        return AQResult(True, procs, True, f"{len(procs)} processes")

    def _handle_kill_process(self, params: dict) -> AQResult:
        if not self._system:
            return AQResult(False, None, False, "System adapter not available")
        target = params.get("target", params.get("name", params.get("pid", "")))
        if not target:
            return AQResult(False, None, False, "Process name/pid required")
        result = self._system.kill_process(target)
        return AQResult(success=result.get("success", False), result=result.get("result", ""),
                       verified=result.get("verified", False), message=result.get("result", ""))

    def _handle_set_priority(self, params: dict) -> AQResult:
        if not self._system:
            return AQResult(False, None, False, "System adapter not available")
        target = params.get("target", params.get("name", params.get("pid", "")))
        priority = params.get("priority", "normal")
        if not target:
            return AQResult(False, None, False, "Process name/pid required")
        result = self._system.set_priority(target, priority)
        return AQResult(success=result.get("success", False), result=result.get("result", ""),
                       verified=result.get("verified", False), message=result.get("result", ""))
    # ---- Browser handlers ----
    def _handle_open_url(self, params: dict) -> AQResult:
        if not self._browser:
            return AQResult(False, None, False, "Browser adapter not available")
        url = params.get("url", params.get("link", ""))
        if not url:
            return AQResult(False, None, False, "URL required")
        result = self._browser.open_url(url)
        return AQResult(success=result.get("success", False), result=result.get("result", ""),
                       verified=result.get("verified", False), message=result.get("result", ""))

    def _handle_search_web(self, params: dict) -> AQResult:
        if not self._browser:
            return AQResult(False, None, False, "Browser adapter not available")
        query = params.get("query", params.get("q", ""))
        if not query:
            return AQResult(False, None, False, "Query required")
        result = self._browser.search_web(query)
        return AQResult(success=result.get("success", False), result=result.get("result", ""),
                       verified=result.get("verified", False), message=result.get("result", ""))

    def _handle_fetch_page(self, params: dict) -> AQResult:
        if not self._browser:
            return AQResult(False, None, False, "Browser adapter not available")
        url = params.get("url", params.get("link", ""))
        if not url:
            return AQResult(False, None, False, "URL required")
        result = self._browser.fetch_page(url)
        return AQResult(success=result.get("success", False), result=result.get("content", ""),
                       verified=result.get("verified", False), message="Page fetched")

    # ---- File advanced handlers ----
    def _handle_move_file(self, params: dict) -> AQResult:
        if not self._files:
            return AQResult(False, None, False, "Files adapter not available")
        src = params.get("src", params.get("source", params.get("path", "")))
        dst = params.get("dst", params.get("destination", ""))
        if not src or not dst:
            return AQResult(False, None, False, "Source and destination required")
        result = self._files.move_file(src, dst)
        return AQResult(success=result.get("success", False), result=result.get("result", ""),
                       verified=result.get("verified", False), message=result.get("result", ""))

    def _handle_copy_file(self, params: dict) -> AQResult:
        if not self._files:
            return AQResult(False, None, False, "Files adapter not available")
        src = params.get("src", params.get("source", params.get("path", "")))
        dst = params.get("dst", params.get("destination", ""))
        if not src or not dst:
            return AQResult(False, None, False, "Source and destination required")
        result = self._files.copy_file(src, dst)
        return AQResult(success=result.get("success", False), result=result.get("result", ""),
                       verified=result.get("verified", False), message=result.get("result", ""))

    def _handle_rename_file(self, params: dict) -> AQResult:
        if not self._files:
            return AQResult(False, None, False, "Files adapter not available")
        path = params.get("path", "")
        new_name = params.get("new_name", params.get("name", ""))
        if not path or not new_name:
            return AQResult(False, None, False, "Path and new name required")
        result = self._files.rename_file(path, new_name)
        return AQResult(success=result.get("success", False), result=result.get("result", ""),
                       verified=result.get("verified", False), message=result.get("result", ""))

    def _handle_zip_path(self, params: dict) -> AQResult:
        if not self._files:
            return AQResult(False, None, False, "Files adapter not available")
        path = params.get("path", "")
        if not path:
            return AQResult(False, None, False, "Path required")
        result = self._files.zip_path(path, params.get("out_zip"))
        return AQResult(success=result.get("success", False), result=result.get("result", ""),
                       verified=result.get("verified", False), message=result.get("result", ""))

    def _handle_unzip_path(self, params: dict) -> AQResult:
        if not self._files:
            return AQResult(False, None, False, "Files adapter not available")
        zp = params.get("zip_path", params.get("path", ""))
        if not zp:
            return AQResult(False, None, False, "Zip path required")
        result = self._files.unzip_path(zp, params.get("dst"))
        return AQResult(success=result.get("success", False), result=result.get("result", ""),
                       verified=result.get("verified", False), message=result.get("result", ""))

    def _handle_search_content(self, params: dict) -> AQResult:
        if not self._files:
            return AQResult(False, None, False, "Files adapter not available")
        directory = params.get("directory", params.get("path", ""))
        query = params.get("query", params.get("q", ""))
        if not directory or not query:
            return AQResult(False, None, False, "Directory and query required")
        results = self._files.search_content(directory, query, params.get("ext", ""))
        return AQResult(True, results, True, f"{len(results)} files")

    # ---- Office handlers ----
    def _handle_excel_write(self, params: dict) -> AQResult:
        if not self._office:
            return AQResult(False, None, False, "Office adapter not available")
        path = params.get("path", "")
        cell = params.get("cell", "")
        value = params.get("value", params.get("text", ""))
        if not path or not cell:
            return AQResult(False, None, False, "Path and cell required")
        result = self._office.excel_write(path, cell, value)
        return AQResult(success=result.get("success", False), result=result.get("result", ""),
                       verified=result.get("verified", False), message=result.get("result", ""))

    def _handle_excel_read(self, params: dict) -> AQResult:
        if not self._office:
            return AQResult(False, None, False, "Office adapter not available")
        path = params.get("path", "")
        rng = params.get("range", params.get("cell", "A1"))
        if not path:
            return AQResult(False, None, False, "Path required")
        content = self._office.excel_read(path, rng)
        return AQResult(True, content, True, "Excel read")

    def _handle_word_create_doc(self, params: dict) -> AQResult:
        if not self._office:
            return AQResult(False, None, False, "Office adapter not available")
        path = params.get("path", "")
        if not path:
            return AQResult(False, None, False, "Path required")
        text = params.get("text", params.get("content", ""))
        result = self._office.word_create_doc(path, text)
        return AQResult(success=result.get("success", False), result=result.get("result", ""),
                       verified=result.get("verified", False), message=result.get("result", ""))

    def _handle_word_add_text(self, params: dict) -> AQResult:
        if not self._office:
            return AQResult(False, None, False, "Office adapter not available")
        path = params.get("path", "")
        text = params.get("text", params.get("content", ""))
        if not path or not text:
            return AQResult(False, None, False, "Path and text required")
        result = self._office.word_add_text(path, text)
        return AQResult(success=result.get("success", False), result=result.get("result", ""),
                       verified=result.get("verified", False), message=result.get("result", ""))
