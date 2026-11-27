"""Maya AI system control tools (Windows). LOCAL only."""

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


def get_volume() -> str:
    return _ps("(Get-AudioDevice -Playback -ErrorAction SilentlyContinue).Volume")


def set_volume(level: int) -> str:
    level = max(0, min(100, int(level)))
    if not _ask_permission("Set volume", str(level)):
        return "Cancelled"
    _ps("$o=New-Object -ComObject WScript.Shell")
    return f"Volume request: {level} (use system keys)"


def mute_toggle() -> str:
    if not _ask_permission("Toggle mute", "audio"):
        return "Cancelled"
    _ps("$o=New-Object -ComObject WScript.Shell; $o.SendKeys([char]173)")
    return "Mute toggled"


def get_brightness() -> str:
    return _ps("(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightness -ErrorAction SilentlyContinue).CurrentBrightness")


def set_brightness(level: int) -> str:
    level = max(0, min(100, int(level)))
    if not _ask_permission("Set brightness", str(level)):
        return "Cancelled"
    _ps(f"(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods -ErrorAction SilentlyContinue).WmiSetBrightness(1,{level})")
    return f"Brightness set to {level}"


def lock_workstation() -> str:
    if not _ask_permission("Lock workstation", "screen"):
        return "Cancelled"
    _ps("rundll32.exe user32.dll,LockWorkStation")
    return "Workstation locked"


def sleep_pc() -> str:
    if not _ask_permission("Sleep PC", "system"):
        return "Cancelled"
    _ps("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")
    return "Sleeping"


def shutdown_pc() -> str:
    if not _ask_permission("Shutdown PC", "system (IRREVERSIBLE)"):
        return "Cancelled"
    _ps("shutdown /s /t 30")
    return "Shutdown scheduled in 30s"


def restart_pc() -> str:
    if not _ask_permission("Restart PC", "system (IRREVERSIBLE)"):
        return "Cancelled"
    _ps("shutdown /r /t 30")
    return "Restart scheduled in 30s"


def cancel_shutdown() -> str:
    _ps("shutdown /a")
    return "Shutdown cancelled"


__all__ = ["get_volume", "set_volume", "mute_toggle", "get_brightness",
           "set_brightness", "lock_workstation", "sleep_pc", "shutdown_pc",
           "restart_pc", "cancel_shutdown", "set_permission_gate"]
PYEOF