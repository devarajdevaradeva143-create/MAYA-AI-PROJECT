"""Maya AI screen control tools (Windows).

Provides screenshot capture, mouse/keyboard control via ctypes (no external
deps). All actions that change state require user permission per AGENTS.md.

Everything is LOCAL only.
"""

from __future__ import annotations

import ctypes
import os
import subprocess
import threading
from ctypes import wintypes
from typing import Callable, Optional

# Permission gate (same pattern as pc_control)
_GATE: Optional[Callable[[str, str], bool]] = None
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
        response = input(f"[permission] {action} '{item}'? [y/N]: ").strip().lower()
        return response in ("y", "yes", "true", "1")
    except Exception:
        return False


# ---------- Screen size / cursor ----------
def get_screen_size() -> dict:
    """Return primary screen width/height."""
    user32 = ctypes.windll.user32
    return {"width": user32.GetSystemMetrics(0), "height": user32.GetSystemMetrics(1)}


def get_cursor_pos() -> dict:
    """Return current mouse cursor position."""
    pt = wintypes.POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    return {"x": pt.x, "y": pt.y}


# ---------- Screenshot ----------
def screenshot(path: str = None) -> str:
    """Capture primary screen to a PNG file. Returns saved path."""
    if path is None:
        import tempfile
        fd, path = tempfile.mkstemp(suffix=".png", prefix="maya_screen_")
        os.close(fd)
    try:
        from PIL import ImageGrab  # optional
        img = ImageGrab.grab()
        img.save(path)
        return path
    except ImportError:
        pass
    # Fallback: PowerShell System.Drawing
    try:
        size = get_screen_size()
        w, h = size["width"], size["height"]
        ps = (
            "Add-Type -AssemblyName System.Drawing; "
            "$b=New-Object System.Drawing.Bitmap(%d,%d); "
            "$g=[System.Drawing.Graphics]::FromImage($b); "
            "$g.CopyFromScreen(0,0,0,0,$b.Size); "
            "$b.Save('%s'); $g.Dispose(); $b.Dispose()"
            % (w, h, path.replace("\\", "\\\\"))
        )
        subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                      capture_output=True, timeout=15)
        if os.path.exists(path):
            return path
        return f"Failed to capture screenshot: {path}"
    except Exception as e:
        return f"Screenshot error: {e}"


# ---------- Mouse ----------
def mouse_move(x: int, y: int, duration: float = 0.0) -> str:
    """Move mouse to (x,y)."""
    if not _ask_permission("Move mouse", f"({x},{y})"):
        return "Cancelled"
    ctypes.windll.user32.SetCursorPos(int(x), int(y))
    return f"Moved mouse to ({x},{y})"


def mouse_click(x: int = None, y: int = None, button: str = "left",
               clicks: int = 1) -> str:
    """Click at (x,y) or current position."""
    desc = f"{button} click x{clicks}" + (f" at ({x},{y})" if x is not None else "")
    if not _ask_permission("Mouse click", desc):
        return "Cancelled"
    if x is not None and y is not None:
        ctypes.windll.user32.SetCursorPos(int(x), int(y))
    # mouse_event flags
    if button == "right":
        down, up = 0x0008, 0x0010
    elif button == "middle":
        down, up = 0x0020, 0x0040
    else:
        down, up = 0x0002, 0x0004
    for _ in range(max(1, clicks)):
        ctypes.windll.user32.mouse_event(down, 0, 0, 0, 0)
        ctypes.windll.user32.mouse_event(up, 0, 0, 0, 0)
    return f"Clicked {desc}"


def mouse_scroll(amount: int) -> str:
    """Scroll mouse wheel (positive=up)."""
    if not _ask_permission("Mouse scroll", str(amount)):
        return "Cancelled"
    ctypes.windll.user32.mouse_event(0x0800, 0, 0, int(amount), 0)
    return f"Scrolled {amount}"


# ---------- Keyboard ----------
def keyboard_type(text: str) -> str:
    """Type text via SendInput (Unicode)."""
    if not _ask_permission("Type text", text[:60]):
        return "Cancelled"
    for ch in text:
        # Use VkKeyScan / SendInput approach via PowerShell for reliability
        pass
    # Fallback: PowerShell SendKeys
    try:
        escaped = text.replace("'", "''")
        ps = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "[System.Windows.Forms.SendKeys]::SendWait('%s')" % escaped
        )
        subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                      capture_output=True, timeout=10)
        return f"Typed: {text[:60]}"
    except Exception as e:
        return f"Type error: {e}"


def press_key(key: str) -> str:
    """Press a special key (enter, tab, esc, ctrl+c etc.)."""
    if not _ask_permission("Press key", key):
        return "Cancelled"
    try:
        escaped = key.replace("'", "''")
        ps = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "[System.Windows.Forms.SendKeys]::SendWait('%s')" % escaped
        )
        subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                      capture_output=True, timeout=10)
        return f"Pressed: {key}"
    except Exception as e:
        return f"Key error: {e}"


__all__ = [
    "get_screen_size", "get_cursor_pos", "screenshot",
    "mouse_move", "mouse_click", "mouse_scroll",
    "keyboard_type", "press_key", "set_permission_gate",
]
