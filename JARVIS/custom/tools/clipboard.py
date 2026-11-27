"""Maya AI clipboard tools (Windows). LOCAL only."""

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


def read_clipboard() -> str:
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", "Get-Clipboard"],
                           capture_output=True, text=True, timeout=10)
        return (r.stdout or "").strip()
    except Exception as e:
        return str(e)


def write_clipboard(text: str) -> str:
    if not _ask_permission("Write clipboard", text[:60]):
        return "Cancelled"
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command",
                            f"Set-Clipboard -Value '{text.replace(chr(39), chr(39)+chr(39))}'"],
                           capture_output=True, text=True, timeout=10)
        if r.returncode == 0:
            return "Clipboard updated"
        return (r.stderr or "").strip() or "Failed"
    except Exception as e:
        return str(e)


__all__ = ["read_clipboard", "write_clipboard", "set_permission_gate"]
PYEOF