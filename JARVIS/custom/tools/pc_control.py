"""Maya AI PC control tools.

Provides functions to control the PC: open/close apps, read/edit/delete files,
run commands. Important actions (edit/delete/command) require USER PERMISSION
— they prompt before executing per AGENTS.md rule.

All functions are LOCAL only — nothing leaves the laptop.
"""

import os
import subprocess
import sys
import threading
from contextlib import contextmanager
from typing import Callable, Iterator, List, Optional

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

from custom.tools.path_guard import is_path_allowed
from custom.tools.control_guard import is_command_blocked

# The desktop UI / phone server installs a gate for an approved action so the
# console prompt below is never reached in headless mode.
_GATE: Optional[Callable[[str, str], bool]] = None
_GATE_LOCK = threading.RLock()


def _approve_all(action: str, item: str) -> bool:
    del action, item
    return True


def set_permission_gate(fn: Optional[Callable[[str, str], bool]]) -> None:
    """Replace the console permission prompt (None restores it)."""
    global _GATE
    with _GATE_LOCK:
        _GATE = fn


@contextmanager
def approve_once() -> Iterator[None]:
    """Temporarily approve the next call(s) from this thread only."""
    global _GATE
    with _GATE_LOCK:
        previous = _GATE
        _GATE = _approve_all
        try:
            yield
        finally:
            _GATE = previous


def _ask_permission(action: str, item: str) -> bool:
    """Ask user for permission before important action.

    Per AGENTS.md: Important action-ku permission kekkum.
    Returns True if user confirms, False otherwise.
    """
    if _GATE is not None:
        return bool(_GATE(action, item))
    response = input(f"[permission] {action} '{item}'? [y/N]: ").strip().lower()
    return response in ("y", "yes", "true", "1")


def _run_cmd(cmd: List[str]) -> Optional[str]:
    """Run a shell command and return stdout."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None


# ── App listing ────────────────────────────────────────────────────────────

def list_apps() -> List[str]:
    """List running application names (psutil), if available."""
    if not HAS_PSUTIL:
        return ["(psutil not available — install with: uv pip install psutil)"]
    apps = []
    for proc in psutil.process_iter(["name"]):
        try:
            name = proc.info["name"]
            if name:
                apps.append(name)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return sorted(set(apps))


# ── Open / Close apps ─────────────────────────────────────────────────────

def open_app(app_name: str) -> str:
    """Open an application.

    Per AGENTS.md: Important action-ku permission kekkum.
    Asks permission before executing.
    """
    if _ask_permission("Open app", app_name):
        try:
            subprocess.run([app_name], check=False, capture_output=True)
            return f"Opening: {app_name}"
        except Exception as e:
            return f"Failed to open {app_name}: {e}"
    else:
        return f"Cancelled: {app_name} not opened"


def close_app(app_name: str) -> str:
    """Close an application.

    Per AGENTS.md: Important action-ku permission kekkum.
    Asks permission before executing.
    """
    if _ask_permission("Close app", app_name):
        try:
            killed: list[int] = []
            if HAS_PSUTIL:
                for proc in psutil.process_iter(["name", "pid"]):
                    try:
                        if proc.info["name"] and app_name.lower() in proc.info["name"].lower():
                            proc.kill()
                            killed.append(proc.info["pid"])
                    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                        pass
            # Fallback: taskkill on Windows (catches processes psutil missed)
            if sys.platform == "win32" and not killed:
                _run_cmd(["taskkill", "/f", "/im", app_name + ".exe"])
                killed.append(-1)
            if killed:
                return f"Closed: {app_name} (PID: {killed[0]})"
            return f"No running process matched: {app_name}"
        except Exception as e:
            return f"Failed to close {app_name}: {e}"
    else:
        return f"Cancelled: {app_name} not closed"


# ── File operations ───────────────────────────────────────────────────────

def read_file(path: str) -> Optional[str]:
    """Read and return file contents.

    Per AGENTS.md: Read is ✅ Free — no permission needed.
    """
    if not is_path_allowed(path):
        return f"Access denied: {path} is outside allowed roots."
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return f"File not found: {path}"
    except Exception as e:
        return f"Error reading {path}: {e}"


def edit_file(path: str, content: str) -> str:
    """Edit a file — replaces contents.

    Per AGENTS.md: Edit -ku permission kekkum.
    Asks permission before executing.
    """
    if not is_path_allowed(path):
        return f"Access denied: {path} is outside allowed roots."
    if _ask_permission("Edit file", path):
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return f"Edited: {path}"
        except Exception as e:
            return f"Error editing {path}: {e}"
    else:
        return f"Cancelled: {path} not edited"


def delete_file(path: str) -> str:
    """Delete a file.

    Per AGENTS.md: Delete -ku permission kekkum.
    Asks permission before executing.
    """
    if not is_path_allowed(path):
        return f"Access denied: {path} is outside allowed roots."
    if _ask_permission("Delete file", path):
        try:
            os.remove(path)
            return f"Deleted: {path}"
        except Exception as e:
            return f"Error deleting {path}: {e}"
    else:
        return f"Cancelled: {path} not deleted"


# ── Command execution ─────────────────────────────────────────────────────

def run_command(cmd: str) -> str:
    """Run a shell command.

    Per AGENTS.md: Important action-ku permission kekkum.
    Asks permission before executing.
    """
    if is_command_blocked(cmd):
        return f"Blocked command: {cmd}"
    if _ask_permission("Run command", cmd):
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )
            output = result.stdout.strip()
            if result.stderr:
                output += f"\nStderr: {result.stderr.strip()}"
            return f"Command ran: {cmd}\nOutput: {output or '(no output)'}"
        except subprocess.TimeoutExpired:
            return f"Command timed out: {cmd}"
        except Exception as e:
            return f"Error running command: {e}"
    else:
        return f"Cancelled: command not run '{cmd}'"


# ── Convenience: check if app is running ──────────────────────────────────

def is_app_running(app_name: str) -> bool:
    """Check if an app is currently running."""
    if not HAS_PSUTIL:
        return False
    for proc in psutil.process_iter(["name"]):
        try:
            if proc.info["name"] and app_name.lower() in proc.info["name"].lower():
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return False