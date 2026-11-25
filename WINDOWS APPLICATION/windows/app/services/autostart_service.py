"""OS-level autostart for the Maya Windows phone server."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger("maya.autostart")

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "MayaAI"


def _winreg() -> Any | None:
    if sys.platform != "win32":
        return None
    try:
        import winreg

        return winreg
    except ImportError:
        return None


def _launch_command() -> str:
    exe = sys.executable
    # Packaged build: the exe is the interpreter and resolves its own paths.
    if getattr(sys, "frozen", False):
        return f'"{exe}" --tray'
    # Dev build: run from the app folder so `app` is importable.
    app_dir = Path(__file__).resolve().parents[2]
    return f'cmd /c cd /d "{app_dir}" && "{exe}" -m app --tray'


def is_autostart_enabled() -> bool:
    winreg = _winreg()
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            try:
                winreg.QueryValueEx(key, VALUE_NAME)
                return True
            except FileNotFoundError:
                return False
    except (FileNotFoundError, OSError) as exc:
        logger.warning("autostart query failed: %s", exc)
        return False


def enable_autostart() -> bool:
    winreg = _winreg()
    if winreg is None:
        logger.warning("autostart is Windows-only")
        return False
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, _launch_command())
        logger.info("autostart enabled")
        return True
    except OSError as exc:
        logger.error("autostart enable failed: %s", exc)
        return False


def disable_autostart() -> bool:
    winreg = _winreg()
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            try:
                winreg.DeleteValue(key, VALUE_NAME)
            except FileNotFoundError:
                pass
        logger.info("autostart disabled")
        return True
    except OSError as exc:
        logger.error("autostart disable failed: %s", exc)
        return False


__all__ = ["disable_autostart", "enable_autostart", "is_autostart_enabled"]
