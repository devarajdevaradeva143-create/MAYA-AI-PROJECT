"""QApplication bootstrap for the Maya AI desktop app.

PySide6 is imported lazily inside :func:`run_gui` so headless server mode can
run on a machine without Qt (and `custom.server` never sees a Qt import).
"""

from __future__ import annotations

import argparse
import sys
import threading
from collections.abc import Sequence

from app import __version__, paths
from app.logging_setup import install_excepthook, setup_logging

# Resolve `MAYA AI\` once, from the exe location when packaged, and publish it
# as MAYA_AI_HOME so `JARVIS\custom` (config, memory, voice) uses the same
# folder instead of its own __file__-based guess.
paths.export_maya_ai_home()

APP_TITLE = "Maya AI"
DEFAULT_WIDTH = 1180
DEFAULT_HEIGHT = 760

# Try to import pystray for tray functionality; fall back gracefully if not available.
try:
    import pystray
    from PIL import Image, ImageDraw
    HAS_PYSTRAY = True
except ImportError:
    HAS_PYSTRAY = False


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="maya", description="Maya AI desktop app")
    parser.add_argument(
        "--headless",
        action="store_true",
        help="run only the phone server (no window)",
    )
    parser.add_argument(
        "--tray",
        action="store_true",
        help="start minimized to the system tray (shows window on demand)",
    )
    parser.add_argument(
        "--tray-only",
        action="store_true",
        help="start only the system tray icon (no main window, for autostart)",
    )
    parser.add_argument("--version", action="version", version=f"Maya AI {__version__}")
    return parser.parse_args(argv)


def create_main_window():
    """Real shell (sidebar + pages). Phase 1 replaces the Phase 0 blank window."""
    from app.settings_repository import SettingsRepository
    from app.ui.main_window import MayaMainWindow

    repository = SettingsRepository()
    return MayaMainWindow(repository=repository)


def _make_tray_icon(icon_name: str = "Maya") -> pystray.Icon:
    """Create a tray icon with the given name.

    If pystray / PIL are not available, returns a no-op icon object.
    """
    if not HAS_PYSTRAY:
        # Return a simple object with minimal needed methods so the
        # caller can check `is_active` and not crash.
        class _NoopIcon:
            def run(self):  # type: ignore[override]
                pass
            def stop(self):  # type: ignore[override]
                pass
        return _NoopIcon()

    # Build a minimal in-memory icon (256x256, white on transparent).
    img = Image.new("RGB", (256, 256), (30, 30, 30))
    draw = ImageDraw.Draw(img)
    draw.text((128 - 40, 128 - 8), icon_name, fill=(255, 255, 255))
    return pystray.Icon(icon_name, img, title="Maya AI")


def run_gui(argv: Sequence[str] | None = None, start_hidden: bool = False, tray_only: bool = False) -> int:
    """Start the Qt app. Returns the process exit code.

    Args:
        argv: Command-line arguments.
        start_hidden: Start with main window hidden (minimized to tray).
        tray_only: Start only the system tray icon, no main window at all (for autostart).
    """
    logger = setup_logging()
    install_excepthook(logger)
    logger.info("Starting Maya AI desktop %s", __version__)

    from PySide6.QtWidgets import QApplication

    from app.settings_repository import SettingsRepository
    from app.single_instance import SingleInstance
    from app.ui.main_window import MayaMainWindow
    from app.ui.theme import ThemeManager

    app = QApplication.instance() or QApplication(list(argv) if argv else sys.argv)
    app.setApplicationName(APP_TITLE)
    app.setApplicationDisplayName(APP_TITLE)
    app.setOrganizationName("MayaAI")

    instance = SingleInstance()
    if not instance.try_acquire():
        logger.info("Another Maya window is already running; showing it")
        return 0

    repository = SettingsRepository()
    mode = str(repository.get("ui.theme", "system"))
    theme = ThemeManager(app, mode)

    global _main_window

    from PySide6.QtWidgets import QDialog

    from app.services.security_service import SecurityService
    from app.ui.lock_screen import LockScreen

    security = SecurityService()
    if security.pin_is_set():
        lock = LockScreen(security)
        if lock.exec() != QDialog.DialogCode.Accepted:
            return 0

    # In tray-only mode, don't create the main window at all
    if not tray_only:
        _main_window = MayaMainWindow(
            repository=repository, theme=theme, security=security,
            tray_available=HAS_PYSTRAY,
        )

    # --- Tray setup ---
    tray_icon = _make_tray_icon("Maya AI")

    def _show_window() -> None:
        window = _main_window
        if window is None:
            return
        window.showNormal()
        window.raise_()
        window.activateWindow()

    def _on_tray_double_click(icon: pystray.Icon, item: pystray.MenuItem) -> None:
        _show_window()

    def _on_tray_quit(icon: pystray.Icon, item: pystray.MenuItem) -> None:
        icon.stop()
        instance.close()
        app.quit()

    tray_icon.menu = pystray.Menu(
        pystray.MenuItem("Open", _show_window),
        pystray.MenuItem("Quit", _on_tray_quit),
    )
    tray_icon.double_click_callback = _on_tray_double_click
    tray_icon.run_detached()  # run in background; does not block

    def _on_activated() -> None:
        instance.activated.connect(_show_window)

    instance.activated.connect(_on_activated)

    if not start_hidden and not tray_only:
        _main_window.show()

    # Optional phone-server auto-start (Settings -> "Start phone server with Maya").
    # Runs in a worker so uvicorn boot never freezes the window.
    def _start_phone_server() -> None:
        try:
            from app.services.server_service import shared_server_service

            service = shared_server_service()
            service.start()
            logger.info(
                "Phone server auto-started on %s:%s",
                service.host,
                service.bound_port or service.port,
            )
        except Exception as exc:  # noqa: BLE001 - never block the UI
            logger.error("Phone server auto-start failed: %s", exc)

    if bool(repository.get("server.auto_start", False)) and bool(
        repository.get("server.enabled", True)
    ):
        threading.Thread(
            target=_start_phone_server, name="maya-server-autostart", daemon=True
        ).start()

    try:
        return app.exec()
    finally:
        instance.close()
        from app.services.server_service import stop_shared_server

        stop_shared_server()


def run_headless() -> int:
    """Start only the phone server. Filled in by Phase 9."""
    logger = setup_logging()
    install_excepthook(logger)
    logger.info("Starting Maya AI headless server %s", __version__)

    try:
        from app.services.server_service import run_headless_server
    except ImportError:
        logger.error("Headless server is not available yet (Phase 9).")
        return 1

    return run_headless_server()


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.headless:
        return run_headless()
    if args.tray_only:
        return run_gui(start_hidden=True, tray_only=True)
    if args.tray:
        return run_gui(start_hidden=True)

    # Honor the "start minimized" setting when the tray is available.
    try:
        from app.settings_repository import SettingsRepository
        _repo = SettingsRepository()
        start_minimized = bool(_repo.get("ui.start_minimized", False)) and HAS_PYSTRAY
    except Exception:  # noqa: BLE001 - never block startup
        start_minimized = False
    return run_gui(start_hidden=start_minimized)


_main_window = None

if __name__ == "__main__":
    try:
        _exit_code = main()
    except SystemExit:
        raise
    except BaseException:  # noqa: BLE001 - packaged exe must show what broke
        try:
            import traceback

            traceback.print_exc()
        except Exception:  # noqa: BLE001 - no console in windowed builds
            pass
        _exit_code = 1
    raise SystemExit(_exit_code)