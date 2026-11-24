"""Laptop-control adapter for the phone server and the desktop UI.

The server already validated the request (action catalog, path guard, command
denylist) and obtained the owner's confirmation. This module executes the
action against Windows and writes an audit line (action + result only, never
file contents or command text).
"""

from __future__ import annotations

import ctypes
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

import psutil
from custom.server.policy import whatsapp_digits
from custom.tools import pc_control
from custom.tools.control_guard import is_command_blocked
from custom.tools.path_guard import is_path_allowed

from app import paths

CREATE_NO_WINDOW = 0x08000000
COMMAND_TIMEOUT_S = 30

VK_MEDIA = {
    "media.next": 0xB0,
    "media.prev": 0xB1,
    "media.pause": 0xB3,
    "media.play": 0xB3,
}
KEYEVENTF_KEYUP = 0x0002


def _run_hidden(args: list[str], timeout: float = 15) -> subprocess.CompletedProcess[str]:
    kwargs: dict[str, Any] = {"capture_output": True, "text": True, "timeout": timeout}
    if sys.platform == "win32":
        kwargs["creationflags"] = CREATE_NO_WINDOW
    return subprocess.run(args, **kwargs)


def _ps_quote(value: str) -> str:
    return value.replace("'", "''")


def build_whatsapp_uri(number: str, text: str) -> str:
    """`whatsapp:` deep link that only prefills the chat (user presses Send)."""
    digits = whatsapp_digits(number)
    if len(digits) < 7:
        raise RuntimeError("Invalid phone number")
    return f"whatsapp://send?phone={digits}&text={quote(text, safe='')}"


def build_wa_me_url(number: str, text: str) -> str:
    """Browser fallback when WhatsApp Desktop is not installed."""
    digits = whatsapp_digits(number)
    if len(digits) < 7:
        raise RuntimeError("Invalid phone number")
    return f"https://wa.me/{digits}?text={quote(text, safe='')}"


def _protocol_registered(scheme: str) -> bool:
    """True when a `scheme:` handler is registered on this Windows machine."""
    if sys.platform != "win32":
        return False
    try:
        import winreg
    except ImportError:  # pragma: no cover - non-Windows
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, scheme):
            return True
    except OSError:
        return False


class ControlService:
    """PcPort implementation."""

    def __init__(self, audit_path: Path | None = None) -> None:
        self._lock = threading.RLock()
        self._audit_path = audit_path or paths.audit_log_path()

    # -- port ---------------------------------------------------------

    def execute(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            try:
                handler = getattr(self, f"_do_{action.replace('.', '_')}", None)
                if handler is None:
                    raise RuntimeError(f"Unsupported action: {action}")
                result = handler(params)
            except Exception:
                self._audit(action, ok=False)
                raise
            self._audit(action, ok=True)
            return result

    # -- audit --------------------------------------------------------

    def _audit(self, action: str, *, ok: bool) -> None:
        entry = {"ts": int(time.time()), "action": action, "ok": ok, "source": "phone"}
        try:
            self._audit_path.parent.mkdir(parents=True, exist_ok=True)
            with self._audit_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry) + "\n")
        except OSError:
            pass

    # -- apps ---------------------------------------------------------

    def _do_app_list(self, params: dict[str, Any]) -> dict[str, Any]:
        del params
        return {"apps": pc_control.list_apps()}

    def _do_process_list(self, params: dict[str, Any]) -> dict[str, Any]:
        del params
        processes = []
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                name = proc.info.get("name")
                if name:
                    processes.append({"pid": proc.info["pid"], "name": name})
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        processes.sort(key=lambda item: item["name"].lower())
        return {"processes": processes}

    def _do_app_open(self, params: dict[str, Any]) -> dict[str, Any]:
        name = str(params["name"])
        # Popen, not pc_control.open_app: that helper blocks until the app exits.
        process = subprocess.Popen([name])
        return {"message": f"Opened: {name}", "pid": process.pid}

    def _do_app_close(self, params: dict[str, Any]) -> dict[str, Any]:
        name = str(params["name"])
        with pc_control.approve_once():
            message = pc_control.close_app(name)
        return {"message": message}

    # -- files --------------------------------------------------------

    def _do_file_read(self, params: dict[str, Any]) -> dict[str, Any]:
        path = str(params["path"])
        if not is_path_allowed(path):
            raise RuntimeError(f"Access denied: {path} is outside allowed roots.")
        try:
            content = pc_control.read_file(path)
            return {"path": path, "content": content}
        except RuntimeError as e:
            raise RuntimeError(str(e)) from e

    def _do_dir_list(self, params: dict[str, Any]) -> dict[str, Any]:
        path = Path(params["path"])
        if not path.is_dir():
            raise NotADirectoryError(str(path))
        entries = []
        with os.scandir(path) as iterator:
            for entry in iterator:
                try:
                    is_dir = entry.is_dir()
                    size = entry.stat().st_size if not is_dir else None
                except OSError:
                    continue
                entries.append(
                    {"name": entry.name, "path": entry.path, "is_dir": is_dir, "size": size}
                )
        entries.sort(key=lambda item: (not item["is_dir"], item["name"].lower()))
        return {"path": str(path), "entries": entries}

    def _do_file_write(self, params: dict[str, Any]) -> dict[str, Any]:
        path = str(params["path"])
        content = str(params["content"])
        if not is_path_allowed(path):
            raise RuntimeError(f"Access denied: {path} is outside allowed roots.")
        with pc_control.approve_once():
            message = pc_control.edit_file(path, content)
        return {"message": message, "path": path}

    def _do_file_delete(self, params: dict[str, Any]) -> dict[str, Any]:
        path = str(params["path"])
        if not is_path_allowed(path):
            raise RuntimeError(f"Access denied: {path} is outside allowed roots.")
        try:
            from send2trash import send2trash
        except ImportError:
            with pc_control.approve_once():
                message = pc_control.delete_file(str(path))
            return {"message": message, "path": str(path)}

        send2trash(str(path))
        return {"message": f"Moved to recycle bin: {path}", "path": str(path)}

    # -- shell --------------------------------------------------------

    def _do_cmd_run(self, params: dict[str, Any]) -> dict[str, Any]:
        command = str(params["command"])
        # Block dangerous commands at the guard level
        if is_command_blocked(command):
            raise RuntimeError(f"Blocked command: {command}")
        cwd = params.get("cwd")
        kwargs: dict[str, Any] = {
            "shell": True,
            "capture_output": True,
            "text": True,
            "timeout": COMMAND_TIMEOUT_S,
            "cwd": str(cwd) if cwd else None,
        }
        if sys.platform == "win32":
            kwargs["creationflags"] = CREATE_NO_WINDOW
        completed = subprocess.run(command, **kwargs)
        output = (completed.stdout or "").strip()
        error = (completed.stderr or "").strip()
        message = output or "(no output)"
        if error:
            message += f"\nStderr: {error}"
        self._audit(command, ok=True)
        return {"message": message, "returncode": completed.returncode}

    # -- system -------------------------------------------------------

    def _require_windows(self) -> None:
        if sys.platform != "win32":
            raise RuntimeError("This action is Windows-only right now")

    def _do_system_lock(self, params: dict[str, Any]) -> dict[str, Any]:
        del params
        self._require_windows()
        if not ctypes.windll.user32.LockWorkStation():
            raise RuntimeError("Could not lock the workstation")
        return {"message": "PC locked"}

    def _do_system_sleep(self, params: dict[str, Any]) -> dict[str, Any]:
        del params
        self._require_windows()
        _run_hidden(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])
        return {"message": "Sleep requested"}

    def _do_system_shutdown(self, params: dict[str, Any]) -> dict[str, Any]:
        self._require_windows()
        delay = int(params.get("delay_s", 60))
        kwargs: dict[str, Any] = {"creationflags": CREATE_NO_WINDOW}
        subprocess.Popen(
            ["shutdown", "/s", "/t", str(delay), "/c", "Maya AI"],
            **kwargs,
        )
        return {"message": f"Shutting down in {delay} seconds"}

    def _do_system_volume(self, params: dict[str, Any]) -> dict[str, Any]:
        self._require_windows()
        level = int(params["level"])
        self._set_volume(level / 100.0)
        return {"message": f"Volume set to {level}%"}

    def _do_system_mute(self, params: dict[str, Any]) -> dict[str, Any]:
        self._require_windows()
        muted = bool(params.get("mute"))
        self._set_mute(muted)
        return {"message": "Muted" if muted else "Unmuted"}

    @staticmethod
    def _endpoint_volume():
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

        device = AudioUtilities.GetSpeakers()
        interface = device.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        return interface.QueryInterface(IAudioEndpointVolume)

    def _set_volume(self, scalar: float) -> None:
        self._endpoint_volume().SetMasterVolumeLevelScalar(max(0.0, min(1.0, scalar)), None)

    def _set_mute(self, muted: bool) -> None:
        self._endpoint_volume().SetMute(1 if muted else 0, None)

    def _do_system_screenshot(self, params: dict[str, Any]) -> dict[str, Any]:
        from PIL import ImageGrab

        target = params.get("save_path")
        if target:
            path = Path(str(target))
        else:
            stamp = time.strftime("%Y%m%d-%H%M%S")
            path = paths.data_root() / "screenshots" / f"screenshot-{stamp}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        ImageGrab.grab().save(path)
        return {"path": str(path), "message": "Screenshot saved"}

    def _do_media_play(self, params: dict[str, Any]) -> dict[str, Any]:
        return self._media_key("media.play")

    def _do_media_pause(self, params: dict[str, Any]) -> dict[str, Any]:
        return self._media_key("media.pause")

    def _do_media_next(self, params: dict[str, Any]) -> dict[str, Any]:
        return self._media_key("media.next")

    def _do_media_prev(self, params: dict[str, Any]) -> dict[str, Any]:
        return self._media_key("media.prev")

    def _media_key(self, action: str) -> dict[str, Any]:
        self._require_windows()
        vk = VK_MEDIA[action]
        ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
        ctypes.windll.user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
        return {"message": f"Media key sent: {action.split('.', 1)[1]}"}

    # -- clipboard ----------------------------------------------------

    def _do_clipboard_get(self, params: dict[str, Any]) -> dict[str, Any]:
        del params
        self._require_windows()
        completed = _run_hidden(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", "Get-Clipboard -Raw"]
        )
        if completed.returncode != 0:
            raise RuntimeError("Could not read the clipboard")
        return {"text": completed.stdout.rstrip("\r\n")}

    def _do_clipboard_set(self, params: dict[str, Any]) -> dict[str, Any]:
        self._require_windows()
        text = str(params["text"])
        temp = paths.data_root() / "clipboard.txt"
        temp.parent.mkdir(parents=True, exist_ok=True)
        temp.write_text(text, encoding="utf-8")
        try:
            script = (
                f"Get-Content -Raw -Encoding UTF8 '{_ps_quote(str(temp))}' | Set-Clipboard"
            )
            completed = _run_hidden(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", script]
            )
            if completed.returncode != 0:
                raise RuntimeError("Could not write the clipboard")
        finally:
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass
        return {"message": "Clipboard updated"}

    # -- notification -------------------------------------------------

    def _do_notify(self, params: dict[str, Any]) -> dict[str, Any]:
        self._require_windows()
        title = _ps_quote(str(params["title"]))
        body = _ps_quote(str(params.get("body", "")))
        script = (
            "Add-Type -AssemblyName System.Windows.Forms;"
            "Add-Type -AssemblyName System.Drawing;"
            "$n = New-Object System.Windows.Forms.NotifyIcon;"
            "$n.Icon = [System.Drawing.SystemIcons]::Information;"
            "$n.Visible = $true;"
            f"$n.ShowBalloonTip(4000, '{title}', '{body}', 'Info');"
            "Start-Sleep -Seconds 5;"
            "$n.Dispose();"
        )
        subprocess.Popen(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            creationflags=CREATE_NO_WINDOW,
        )
        return {"message": "Notification shown"}

    # -- whatsapp -----------------------------------------------------

    def _do_whatsapp_message(self, params: dict[str, Any]) -> dict[str, Any]:
        """Open WhatsApp with the chat prefilled. The user still presses Send."""
        self._require_windows()
        number = str(params["number"])
        text = str(params["text"]).strip()
        if not text:
            raise RuntimeError("Message is empty")

        if _protocol_registered("whatsapp"):
            os.startfile(build_whatsapp_uri(number, text))  # type: ignore[attr-defined]
            return {"message": "WhatsApp opened with the message - press Send"}

        os.startfile(build_wa_me_url(number, text))  # type: ignore[attr-defined]
        return {"message": "WhatsApp Desktop not found - opened wa.me in the browser"}

    # -- helpers ------------------------------------------------------

    @staticmethod
    def available() -> dict[str, bool]:
        try:
            import send2trash  # noqa: F401

            trash = True
        except ImportError:
            trash = False
        return {
            "send2trash": trash,
            "powershell": shutil.which("powershell") is not None,
            "windows": sys.platform == "win32",
        }
