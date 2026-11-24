"""Remote screen / input / hybrid adapters for the phone server.

Only the Windows app imports this module. `custom.server` stays headless and
talks to these adapters through the ports in `custom.server.contracts`.
"""

from __future__ import annotations

import ctypes
import io
import sys
from typing import Any

from custom.server.contracts import ScreenFrame
from custom.tools.hybrid_controller import Controller, HybridController


class ScreenAdapter:
    """Capture the Windows desktop as a resized JPEG frame."""

    @staticmethod
    def available() -> bool:
        return sys.platform == "win32"

    def capture(self, *, max_width: int = 1280, quality: int = 60) -> ScreenFrame:
        if sys.platform != "win32":
            raise RuntimeError("Screen capture is Windows-only right now")
        try:
            from PIL import Image, ImageGrab
        except ImportError as exc:  # pragma: no cover - shipped with the app
            raise RuntimeError("Pillow is not installed") from exc

        image = ImageGrab.grab()
        if image.width > max_width:
            height = max(1, round(image.height * max_width / image.width))
            resample = getattr(Image, "Resampling", Image).LANCZOS
            image = image.resize((max_width, height), resample)
        buffer = io.BytesIO()
        image.convert("RGB").save(buffer, format="JPEG", quality=quality, optimize=True)
        return ScreenFrame(
            data=buffer.getvalue(),
            media_type="image/jpeg",
            width=image.width,
            height=image.height,
        )


class HybridAdapter:
    """No-argument wrapper so the server does not import controller enums."""

    def __init__(self, controller: HybridController | None = None) -> None:
        self.controller = controller or HybridController()

    def status(self) -> Any:
        return self.controller.status()

    def list_tasks(self) -> list[Any]:
        return self.controller.list_tasks()

    def takeover(self) -> bool:
        return self.controller.takeover(Controller.USER)

    def release(self) -> bool:
        return self.controller.release(Controller.USER)


# -- Windows input injection ------------------------------------------------

if sys.platform == "win32":  # pragma: no cover - exercised on the laptop only
    from ctypes import wintypes

    ULONG_PTR = wintypes.WPARAM

    class _MOUSEINPUT(ctypes.Structure):
        _fields_ = [
            ("dx", wintypes.LONG),
            ("dy", wintypes.LONG),
            ("mouseData", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ULONG_PTR),
        ]

    class _KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", wintypes.WORD),
            ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ULONG_PTR),
        ]

    class _HARDWAREINPUT(ctypes.Structure):
        _fields_ = [
            ("uMsg", wintypes.DWORD),
            ("wParamL", wintypes.WORD),
            ("wParamH", wintypes.WORD),
        ]

    class _INPUTUNION(ctypes.Union):
        _fields_ = [("mi", _MOUSEINPUT), ("ki", _KEYBDINPUT), ("hi", _HARDWAREINPUT)]

    class _INPUT(ctypes.Structure):
        _anonymous_ = ("u",)
        _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]

    INPUT_MOUSE = 0
    INPUT_KEYBOARD = 1
    KEYEVENTF_KEYUP = 0x0002
    KEYEVENTF_UNICODE = 0x0004
    MOUSEEVENTF_LEFTDOWN = 0x0002
    MOUSEEVENTF_LEFTUP = 0x0004
    MOUSEEVENTF_RIGHTDOWN = 0x0008
    MOUSEEVENTF_RIGHTUP = 0x0010
    MOUSEEVENTF_MIDDLEDOWN = 0x0020
    MOUSEEVENTF_MIDDLEUP = 0x0040
    MOUSEEVENTF_WHEEL = 0x0800

    VK = {
        "enter": 0x0D,
        "tab": 0x09,
        "esc": 0x1B,
        "backspace": 0x08,
        "delete": 0x2E,
        "space": 0x20,
        "up": 0x26,
        "down": 0x28,
        "left": 0x25,
        "right": 0x27,
        "home": 0x24,
        "end": 0x23,
        "pageup": 0x21,
        "pagedown": 0x22,
        "ctrl": 0x11,
        "alt": 0x12,
        "shift": 0x10,
        "win": 0x5B,
        "f5": 0x74,
    }
    VK_CHARS = {chr(code): code - 32 for code in range(ord("A"), ord("Z") + 1)}


class InputAdapter:
    """Mouse + keyboard injection for REMOTE/HYBRID mode."""

    @staticmethod
    def available() -> bool:
        return sys.platform == "win32"

    def _require_windows(self) -> None:
        if sys.platform != "win32":
            raise RuntimeError("Remote input is Windows-only right now")

    def _screen_size(self) -> tuple[int, int]:
        user32 = ctypes.windll.user32
        return max(1, user32.GetSystemMetrics(0)), max(1, user32.GetSystemMetrics(1))

    def _mouse(self, flags: int, data: int = 0) -> None:
        ctypes.windll.user32.mouse_event(flags, 0, 0, data, 0)

    def _unicode(self, text: str) -> None:
        units = text.encode("utf-16-le")
        for index in range(0, len(units), 2):
            code = int.from_bytes(units[index : index + 2], "little")
            down = _INPUT(
                type=INPUT_KEYBOARD,
                u=_INPUTUNION(ki=_KEYBDINPUT(0, code, KEYEVENTF_UNICODE, 0, 0)),
            )
            up = _INPUT(
                type=INPUT_KEYBOARD,
                u=_INPUTUNION(
                    ki=_KEYBDINPUT(0, code, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0, 0)
                ),
            )
            ctypes.windll.user32.SendInput(1, ctypes.byref(down), ctypes.sizeof(_INPUT))
            ctypes.windll.user32.SendInput(1, ctypes.byref(up), ctypes.sizeof(_INPUT))

    def _vk(self, name: str, up: bool = False) -> None:
        code = VK.get(name) or VK_CHARS.get(name.upper())
        if code is None:
            raise RuntimeError(f"Unsupported key: {name}")
        flags = KEYEVENTF_KEYUP if up else 0
        ctypes.windll.user32.keybd_event(code, 0, flags, 0)

    def _combo(self, combo: str) -> None:
        parts = [part.strip().lower() for part in combo.split("+") if part.strip()]
        if not parts:
            return
        for key in parts[:-1]:
            self._vk(key)
        self._vk(parts[-1])
        self._vk(parts[-1], up=True)
        for key in reversed(parts[:-1]):
            self._vk(key, up=True)

    def apply(self, events: list[dict[str, Any]]) -> int:
        self._require_windows()
        applied = 0
        for event in events:
            kind = event.get("type")
            if kind == "move":
                width, height = self._screen_size()
                x = int(float(event["x"]) * (width - 1))
                y = int(float(event["y"]) * (height - 1))
                ctypes.windll.user32.SetCursorPos(x, y)
            elif kind == "click":
                button = event.get("button", "left")
                flags = {
                    "left": (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
                    "right": (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP),
                    "middle": (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP),
                }[button]
                self._mouse(flags[0])
                self._mouse(flags[1])
            elif kind == "scroll":
                self._mouse(MOUSEEVENTF_WHEEL, int(event["dy"]) * 120)
            elif kind == "text":
                text = str(event.get("text", ""))
                for line_index, line in enumerate(text.split("\n")):
                    if line_index:
                        self._vk("enter")
                    self._unicode(line)
            elif kind == "key":
                self._combo(str(event.get("key", "")))
            else:
                raise RuntimeError(f"Unsupported input event: {kind}")
            applied += 1
        return applied


__all__ = ["HybridAdapter", "InputAdapter", "ScreenAdapter"]
