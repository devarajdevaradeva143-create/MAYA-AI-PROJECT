"""Maya AI process management tools. LOCAL only."""

from __future__ import annotations

import threading
from typing import Callable, Optional

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False
    psutil = None

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


def list_processes(filter_name: str = "") -> list:
    if not HAS_PSUTIL:
        return []
    out = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_info"]):
        try:
            info = p.info
            name = info.get("name") or ""
            if filter_name and filter_name.lower() not in name.lower():
                continue
            mem = info.get("memory_info")
            out.append({
                "pid": info.get("pid"),
                "name": name,
                "cpu": info.get("cpu_percent"),
                "mem_mb": round(mem.rss / (1024*1024), 1) if mem else 0,
            })
        except Exception:
            pass
    return out[:50]


def kill_process(name_or_pid) -> str:
    target = str(name_or_pid)
    if not _ask_permission("Kill process", target):
        return "Cancelled"
    if not HAS_PSUTIL:
        return "psutil not available"
    killed = []
    try:
        if target.isdigit():
            p = psutil.Process(int(target))
            p.kill()
            killed.append(int(target))
        else:
            for p in psutil.process_iter(["pid", "name"]):
                try:
                    if p.info["name"] and target.lower() in p.info["name"].lower():
                        p.kill()
                        killed.append(p.info["pid"])
                except Exception:
                    pass
    except Exception as e:
        return f"Error: {e}"
    if killed:
        return f"Killed {target} (PIDs: {killed})"
    return f"No process matched: {target}"


def set_priority(name_or_pid, priority: str = "normal") -> str:
    if not _ask_permission("Set priority", f"{name_or_pid} -> {priority}"):
        return "Cancelled"
    if not HAS_PSUTIL:
        return "psutil not available"
    levels = {
        "low": psutil.BELOW_NORMAL_PRIORITY_CLASS,
        "normal": psutil.NORMAL_PRIORITY_CLASS,
        "high": psutil.HIGH_PRIORITY_CLASS,
        "realtime": psutil.REALTIME_PRIORITY_CLASS,
    }
    lvl = levels.get(priority.lower(), psutil.NORMAL_PRIORITY_CLASS)
    try:
        if str(name_or_pid).isdigit():
            psutil.Process(int(name_or_pid)).nice(lvl)
        else:
            for p in psutil.process_iter(["pid", "name"]):
                if p.info["name"] and str(name_or_pid).lower() in p.info["name"].lower():
                    p.nice(lvl)
        return f"Priority set to {priority}"
    except Exception as e:
        return f"Error: {e}"


__all__ = ["list_processes", "kill_process", "set_priority", "set_permission_gate", "HAS_PSUTIL"]
PYEOF