"""Rotating file logging for the desktop app and the phone server.

Privacy: callers must never log chat text, phone numbers or message content.
Only operational metadata (route, duration, error code) belongs in the log.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app import paths

LOG_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
MAX_BYTES = 2 * 1024 * 1024
BACKUP_COUNT = 5
_HANDLER_FLAG = "_maya_file_handler"


def _file_handler(path: Path, level: int) -> RotatingFileHandler:
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        path,
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    handler.setLevel(level)
    setattr(handler, _HANDLER_FLAG, True)
    return handler


def _reset_handlers(root: logging.Logger) -> None:
    for handler in list(root.handlers):
        if getattr(handler, _HANDLER_FLAG, False):
            root.removeHandler(handler)
            handler.close()


def _configure(
    log_file: Path,
    level: int,
    console: bool,
    logger_name: str,
) -> logging.Logger:
    root = logging.getLogger()
    _reset_handlers(root)
    root.setLevel(level)
    root.addHandler(_file_handler(log_file, level))

    if console and not any(
        isinstance(handler, logging.StreamHandler)
        and getattr(handler, _HANDLER_FLAG, False)
        for handler in root.handlers
    ):
        stream = logging.StreamHandler(sys.stderr)
        stream.setFormatter(logging.Formatter(LOG_FORMAT))
        stream.setLevel(level)
        setattr(stream, _HANDLER_FLAG, True)
        root.addHandler(stream)

    logging.captureWarnings(True)
    return logging.getLogger(logger_name)


def setup_logging(
    level: int = logging.INFO,
    log_file: Path | None = None,
    console: bool = False,
) -> logging.Logger:
    """Configure the app logger (`MAYA AI\\logs\\app.log`, 5 x 2 MB)."""
    paths.ensure_runtime_dirs()
    return _configure(log_file or paths.app_log_path(), level, console, "maya")


def setup_server_logging(
    level: int = logging.INFO,
    log_file: Path | None = None,
    console: bool = False,
) -> logging.Logger:
    """Configure the phone server logger (`MAYA AI\\logs\\server.log`)."""
    paths.ensure_runtime_dirs()
    return _configure(log_file or paths.server_log_path(), level, console, "maya.server")


def install_excepthook(logger: logging.Logger) -> None:
    """Log uncaught exceptions without dumping local variables."""

    def _hook(exc_type, exc_value, exc_tb) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        logger.error("Unhandled exception", exc_info=(exc_type, exc_value, exc_tb))

    sys.excepthook = _hook
