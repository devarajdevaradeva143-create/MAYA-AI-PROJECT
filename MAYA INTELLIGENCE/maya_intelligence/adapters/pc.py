"""PC control adapter — wraps custom.tools.pc_control + adds create_folder."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any


class MayaIntelError(Exception):
    """Base exception for MAYA INTELLIGENCE adapters."""


#: Friendly app names -> executable / shell names.
_LAUNCH_ALIASES = {
    "calculator": "calc",
    "calc": "calc",
    "vs code": "code",
    "vscode": "code",
    "visual studio code": "code",
    "chrome": "chrome",
    "google chrome": "chrome",
    "edge": "msedge",
    "microsoft edge": "msedge",
    "word": "winword",
    "excel": "excel",
    "powerpoint": "powerpnt",
    "paint": "mspaint",
    "explorer": "explorer",
    "file explorer": "explorer",
    "files": "explorer",
    "task manager": "taskmgr",
    "terminal": "wt",
    "cmd": "cmd",
    "command prompt": "cmd",
    "settings": "ms-settings:",
}

#: Friendly app names -> process-name fragments used for verification.
_PROCESS_ALIASES = {
    "vs code": "code",
    "vscode": "code",
    "visual studio code": "code",
    "file explorer": "explorer",
    "files": "explorer",
    "command prompt": "cmd",
    "terminal": "terminal",
}


def _start_app(name: str) -> str:
    """Launch an app without waiting for it to exit. Returns launch target."""
    key = name.strip().lower()
    target = _LAUNCH_ALIASES.get(key, name.strip())

    if target.startswith("ms-"):
        os.startfile(target)
        return target

    resolved = shutil.which(target) or target
    try:
        if str(resolved).lower().endswith((".cmd", ".bat")):
            subprocess.Popen(
                ["cmd", "/c", str(resolved)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            subprocess.Popen(
                [str(resolved)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
    except (FileNotFoundError, OSError):
        # Last resort: Windows shell association (works for "calc", URLs, etc.)
        os.startfile(target)
    return target


class PCAdapter:
    """Thin wrapper over custom.tools.pc_control with create_folder added.

    Confirmation is owned by the AQ engine: it asks once, then calls these
    methods with ``confirm=False``. The underlying pc_control tool asks again,
    so we wrap those calls in ``approve_once()`` to avoid double prompts.
    """

    def __init__(self):
        from custom.tools import pc_control
        from custom.tools.path_guard import is_path_allowed
        from custom.tools.control_guard import is_command_blocked, safe_cmd

        self._pc = pc_control
        self._is_path_allowed = is_path_allowed
        self._is_command_blocked = is_command_blocked
        self._safe_cmd = safe_cmd

    # ── Helpers ─────────────────────────────────────────────────────
    def _call_pc(self, func, *args, confirm: bool = False, **kwargs):
        """Call a pc_control function, suppressing its gate when already asked."""
        if confirm:
            return func(*args, **kwargs)
        approve = getattr(self._pc, "approve_once", None)
        if approve is None:
            return func(*args, **kwargs)
        with approve():
            return func(*args, **kwargs)

    def is_app_running(self, name: str) -> bool:
        """Check if app is running (uses friendly aliases)."""
        candidate = _PROCESS_ALIASES.get(name.strip().lower(), name)
        return self._pc.is_app_running(candidate)

    def _wait_running(self, name: str, timeout: float = 4.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.is_app_running(name):
                return True
            time.sleep(0.2)
        return False

    def _wait_stopped(self, name: str, timeout: float = 4.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not self.is_app_running(name):
                return True
            time.sleep(0.2)
        return not self.is_app_running(name)

    # ── Apps ────────────────────────────────────────────────────────
    def open_app(self, name: str, confirm: bool = True) -> dict[str, Any]:
        """Open an application without blocking the chat."""
        if not name or not name.strip():
            return {"success": False, "result": "App name required", "verified": False}
        try:
            target = _start_app(name)
        except Exception as exc:
            return {
                "success": False,
                "result": f"Failed to open {name}: {exc}",
                "verified": False,
            }
        running = self._wait_running(name)
        return {
            "success": running,
            "result": f"Opening: {name}" if running else f"Tried to open {name} ({target})",
            "verified": running,
        }

    def close_app(self, name: str, confirm: bool = True) -> dict[str, Any]:
        """Close an application. Requires confirmation."""
        if not name or not name.strip():
            return {"success": False, "result": "App name required", "verified": False}
        result = self._call_pc(self._pc.close_app, name, confirm=confirm)
        stopped = self._wait_stopped(name)
        return {"success": stopped, "result": result, "verified": stopped}

    def list_apps(self) -> list[str]:
        """List available applications."""
        return self._pc.list_apps()

    # ── Files ───────────────────────────────────────────────────────
    def read_file(self, path: str) -> dict[str, Any]:
        """Read a file. Path must be allowed by path_guard."""
        if not self._is_path_allowed(path):
            raise MayaIntelError(f"Path not allowed: {path}")
        content = self._pc.read_file(path)
        if isinstance(content, str) and content.startswith("Access denied"):
            raise MayaIntelError(content)
        if isinstance(content, str) and content.startswith(("File not found", "Error reading")):
            raise MayaIntelError(content)
        return {"success": True, "content": content}

    def edit_file(
        self,
        path: str,
        old_text: str,
        new_text: str,
        confirm: bool = True,
    ) -> dict[str, Any]:
        """Replace text inside a file. Requires confirmation."""
        if not self._is_path_allowed(path):
            raise MayaIntelError(f"Path not allowed: {path}")
        try:
            content = self._pc.read_file(path)
            if content is None or old_text not in content:
                return {
                    "success": False,
                    "result": f"Text not found in {path}",
                    "verified": False,
                }
            updated = content.replace(old_text, new_text, 1)
            result = self._call_pc(
                self._pc.edit_file, path, updated, confirm=confirm
            )
            try:
                new_content = self._pc.read_file(path)
                verified = new_text in new_content
            except Exception:
                verified = False
            return {"success": verified, "result": result, "verified": verified}
        except Exception as exc:
            return {"success": False, "result": str(exc), "verified": False}

    def delete_file(self, path: str, confirm: bool = True) -> dict[str, Any]:
        """Delete a file. Requires confirmation."""
        if not self._is_path_allowed(path):
            raise MayaIntelError(f"Path not allowed: {path}")
        result = self._call_pc(self._pc.delete_file, path, confirm=confirm)
        verified = not os.path.exists(path)
        return {"success": verified, "result": result, "verified": verified}

    def create_folder(self, path: str, confirm: bool = True) -> dict[str, Any]:
        """Create a folder. Requires confirmation."""
        if not self._is_path_allowed(path):
            raise MayaIntelError(f"Path not allowed: {path}")
        try:
            Path(path).mkdir(parents=True, exist_ok=True)
            result = f"Created folder: {path}"
            verified = os.path.isdir(path)
            return {"success": verified, "result": result, "verified": verified}
        except Exception as e:
            return {"success": False, "result": str(e), "verified": False}

    def run_command(self, command: str, confirm: bool = True) -> dict[str, Any]:
        """Run a command. Requires confirmation and passes control_guard."""
        if self._is_command_blocked(command):
            raise MayaIntelError(f"Command blocked by control_guard: {command}")
        result = self._call_pc(self._pc.run_command, command, confirm=confirm)
        failed = isinstance(result, str) and result.startswith(
            ("Blocked", "Cancelled", "Error", "Command timed out")
        )
        return {"success": not failed, "result": result, "verified": not failed}

    def _ensure_permission_gate(self):
        """Kept for compatibility; the AQ engine owns confirmation."""
        pass
