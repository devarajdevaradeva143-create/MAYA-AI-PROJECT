"""Screen control adapter for MAYA INTELLIGENCE."""

from typing import Any


class MayaIntelError(Exception):
    pass


class ScreenAdapter:
    def __init__(self):
        from custom.tools import screen_control
        self._sc = screen_control

    def get_screen_size(self) -> dict[str, Any]:
        return self._sc.get_screen_size()

    def get_cursor_pos(self) -> dict[str, Any]:
        return self._sc.get_cursor_pos()

    def screenshot(self, path: str = None) -> dict[str, Any]:
        try:
            saved = self._sc.screenshot(path)
            ok = isinstance(saved, str) and not saved.startswith(("Failed", "Screenshot error"))
            return {"success": ok, "path": saved, "verified": ok}
        except Exception as e:
            return {"success": False, "path": "", "verified": False, "error": str(e)}

    def mouse_move(self, x: int, y: int) -> dict[str, Any]:
        res = self._sc.mouse_move(x, y)
        ok = not str(res).startswith("Cancelled")
        return {"success": ok, "result": res, "verified": ok}

    def mouse_click(self, x: int = None, y: int = None, button: str = "left", clicks: int = 1) -> dict[str, Any]:
        res = self._sc.mouse_click(x, y, button, clicks)
        ok = not str(res).startswith("Cancelled")
        return {"success": ok, "result": res, "verified": ok}

    def mouse_scroll(self, amount: int) -> dict[str, Any]:
        res = self._sc.mouse_scroll(amount)
        ok = not str(res).startswith("Cancelled")
        return {"success": ok, "result": res, "verified": ok}

    def keyboard_type(self, text: str) -> dict[str, Any]:
        res = self._sc.keyboard_type(text)
        ok = not str(res).startswith("Cancelled")
        return {"success": ok, "result": res, "verified": ok}

    def press_key(self, key: str) -> dict[str, Any]:
        res = self._sc.press_key(key)
        ok = not str(res).startswith("Cancelled")
        return {"success": ok, "result": res, "verified": ok}
