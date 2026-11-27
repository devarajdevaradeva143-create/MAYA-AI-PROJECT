"""System control adapter for MAYA INTELLIGENCE (system + clipboard + window + process)."""

from typing import Any


class MayaIntelError(Exception):
    pass


class SystemAdapter:
    def __init__(self):
        from custom.tools import system_control, clipboard, window_control, process_control
        self._sys = system_control
        self._clip = clipboard
        self._win = window_control
        self._proc = process_control

    # System
    def get_volume(self) -> str:
        return self._sys.get_volume()

    def set_volume(self, level: int) -> dict[str, Any]:
        res = self._sys.set_volume(level)
        ok = not str(res).startswith("Cancelled")
        return {"success": ok, "result": res, "verified": ok}

    def mute_toggle(self) -> dict[str, Any]:
        res = self._sys.mute_toggle()
        ok = not str(res).startswith("Cancelled")
        return {"success": ok, "result": res, "verified": ok}

    def get_brightness(self) -> str:
        return self._sys.get_brightness()

    def set_brightness(self, level: int) -> dict[str, Any]:
        res = self._sys.set_brightness(level)
        ok = not str(res).startswith("Cancelled")
        return {"success": ok, "result": res, "verified": ok}

    def lock_workstation(self) -> dict[str, Any]:
        res = self._sys.lock_workstation()
        ok = not str(res).startswith("Cancelled")
        return {"success": ok, "result": res, "verified": ok}

    def sleep_pc(self) -> dict[str, Any]:
        res = self._sys.sleep_pc()
        ok = not str(res).startswith("Cancelled")
        return {"success": ok, "result": res, "verified": ok}

    def shutdown_pc(self) -> dict[str, Any]:
        res = self._sys.shutdown_pc()
        ok = not str(res).startswith("Cancelled")
        return {"success": ok, "result": res, "verified": ok}

    def restart_pc(self) -> dict[str, Any]:
        res = self._sys.restart_pc()
        ok = not str(res).startswith("Cancelled")
        return {"success": ok, "result": res, "verified": ok}

    def cancel_shutdown(self) -> dict[str, Any]:
        res = self._sys.cancel_shutdown()
        return {"success": True, "result": res, "verified": True}

    # Clipboard
    def read_clipboard(self) -> str:
        return self._clip.read_clipboard()

    def write_clipboard(self, text: str) -> dict[str, Any]:
        res = self._clip.write_clipboard(text)
        ok = not str(res).startswith("Cancelled")
        return {"success": ok, "result": res, "verified": ok}

    # Window
    def list_windows(self) -> list:
        return self._win.list_windows()

    def focus_window(self, title: str) -> dict[str, Any]:
        res = self._win.focus_window(title)
        ok = not str(res).startswith("Cancelled")
        return {"success": ok, "result": res, "verified": ok}

    def minimize_all(self) -> dict[str, Any]:
        res = self._win.minimize_all()
        ok = not str(res).startswith("Cancelled")
        return {"success": ok, "result": res, "verified": ok}

    def close_window(self, title: str) -> dict[str, Any]:
        res = self._win.close_window(title)
        ok = not str(res).startswith("Cancelled")
        return {"success": ok, "result": res, "verified": ok}

    # Process
    def list_processes(self, filter_name: str = "") -> list:
        return self._proc.list_processes(filter_name)

    def kill_process(self, target) -> dict[str, Any]:
        res = self._proc.kill_process(target)
        ok = not str(res).startswith("Cancelled")
        return {"success": ok, "result": res, "verified": ok}

    def set_priority(self, target, priority: str = "normal") -> dict[str, Any]:
        res = self._proc.set_priority(target, priority)
        ok = not str(res).startswith("Cancelled")
        return {"success": ok, "result": res, "verified": ok}
PYEOF