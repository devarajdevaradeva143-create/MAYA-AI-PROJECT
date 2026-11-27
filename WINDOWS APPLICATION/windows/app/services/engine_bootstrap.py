"""Start LemonadeServer.exe if the local engine is not answering.

Called once at app start (and from the Settings "Fix" button).
Never raises: returns False and lets the UI show an honest error.
"""

from __future__ import annotations

import logging
import subprocess
import time
from pathlib import Path

import httpx

logger = logging.getLogger("maya.engine.bootstrap")

DEFAULT_HOST = "http://localhost:13305"
LEMONADE_EXE = (
    Path.home() / "AppData" / "Local" / "lemonade_server" / "bin" / "LemonadeServer.exe"
)
START_TIMEOUT = 25.0


def engine_alive(host: str = DEFAULT_HOST, timeout: float = 2.0) -> bool:
    try:
        return httpx.get(f"{host}/api/v1/health", timeout=timeout).status_code == 200
    except Exception:  # noqa: BLE001 - a dead engine is a normal state
        return False


def ensure_engine(host: str = DEFAULT_HOST, wait: float = START_TIMEOUT) -> bool:
    if engine_alive(host):
        return True
    if not LEMONADE_EXE.is_file():
        logger.warning("LemonadeServer.exe not found at %s", LEMONADE_EXE)
        return False
    try:
        subprocess.Popen(
            [str(LEMONADE_EXE)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError as exc:
        logger.error("failed to start Lemonade: %s", exc)
        return False
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        if engine_alive(host):
            logger.info("Lemonade engine started")
            return True
        time.sleep(0.5)
    logger.warning("Lemonade did not answer within %.0fs", wait)
    return False