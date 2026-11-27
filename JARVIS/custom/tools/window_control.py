"""Maya AI window management tools (Windows). LOCAL only."""

from __future__ import annotations

import subprocess
import threading
from typing import Callable, Optional

_GATE = None
_GATE_LOCK = threading.RLock()


def set_permission_gate(fn):
    global _GATE
    with _GATE_LOCK:
        _GATE = fn


def _ask_permission(action: str, item: str) -> bool:
    if _GATE is not None:
        try:
            return bool(_GATE(action, item))
        except Exception:
            return False
    try:
        return input(f"[permission] {action} '{item}'? [y/N]: ").strip().lower() in ("y", "yes", "true", "1")
    except Exception:
        return False


def _ps(cmd: str) -> str:
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", cmd],
                           capture_output=True, text=True, timeout=15)
        return (r.stdout or "").strip() or (r.stderr or "").strip()
    except Exception as e:
        return str(e)


def list_windows() -> list:
    out = _ps("Get-Process | Where-Object {$_.MainWindowTitle} | Select-Object -ExpandProperty MainWindowTitle")
    return [w for w in out.splitlines() if w.strip()]


def focus_window(title: str) -> str:
    if not _ask_permission("Focus window", title):
        return "Cancelled"
    _ps(f"$w=New-Object -ComObject WScript.Shell; $w.AppActivate('{title}')")
    return f"Focused: {title}"


def minimize_all() -> str:
    if not _ask_permission("Minimize all windows", "desktop"):
        return "Cancelled"
    _ps("$shell=New-Object -ComObject Shell.Application; $shell.MinimizeAll()")
    return "All windows minimized"


def close_window(title: str) -> str:
    if not _ask_permission("Close window", title):
        return "Cancelled"
    _ps(f"Get-Process | Where-Object {{$_.MainWindowTitle -like '*{title}*'}} | Stop-Process")
    return f"Closed window: {title}"


__all__ = ["list_windows", "focus_window", "minimize_all", "close_window", "set_permission_gate"]
PYEOF