"""Maya AI — Windows tray app.

Small tray icon that lets you open Maya chat, check system status, test the
voice, and quit. Everything runs locally.

Run:
    python LAPTOP/windows/app/maya_tray.py

Needs (optional):
    uv pip install pystray pillow

If pystray is missing, the app falls back to opening the terminal chat, so it
still works without extra packages.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# Project root: this file -> app -> windows -> LAPTOP -> project root
ROOT = Path(__file__).resolve().parents[3]
MAYA_DIR = ROOT / "JARVIS"


def _run(args: list[str], *, terminal: bool = False) -> None:
    """Run the Maya CLI (or any command) in the background."""
    python = sys.executable
    kwargs: dict = {"cwd": str(MAYA_DIR)}
    if terminal and sys.platform == "win32":
        # New console window so chat is interactive.
        kwargs["creationflags"] = subprocess.CREATE_NEW_CONSOLE
    subprocess.Popen([python, *args], **kwargs)


def _chat() -> None:
    _run(["-m", "custom.cli", "chat"], terminal=True)


def _status() -> None:
    _run(["-m", "custom.cli", "monitor", "status"], terminal=True)


def _speak() -> None:
    _run(
        ["-m", "custom.cli", "voice", "speak", "Maya is here, sollu da"],
        terminal=True,
    )


def main() -> int:
    """Start the tray icon, or fall back to the terminal chat."""
    try:
        import pystray
        from PIL import Image, ImageDraw
    except ImportError:
        print("pystray / pillow not installed — opening terminal chat instead.")
        print("Install with: uv pip install pystray pillow")
        _chat()
        return 0

    # Simple round icon (no external image file needed).
    image = Image.new("RGB", (64, 64), (30, 30, 40))
    draw = ImageDraw.Draw(image)
    draw.ellipse((8, 8, 56, 56), fill=(255, 120, 170))

    def _on_chat(icon, item) -> None:  # noqa: ANN001 - pystray signature
        _chat()

    def _on_status(icon, item) -> None:  # noqa: ANN001
        _status()

    def _on_speak(icon, item) -> None:  # noqa: ANN001
        _speak()

    def _on_quit(icon, item) -> None:  # noqa: ANN001
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem("Chat pannu", _on_chat, default=True),
        pystray.MenuItem("System status", _on_status),
        pystray.MenuItem("Voice test", _on_speak),
        pystray.MenuItem("Quit", _on_quit),
    )

    icon = pystray.Icon("Maya AI", image, "Maya AI", menu)
    icon.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
