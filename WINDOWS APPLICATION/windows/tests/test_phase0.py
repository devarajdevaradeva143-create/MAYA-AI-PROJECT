"""Phase 0 smoke tests: path resolution, logging, empty window."""

from __future__ import annotations

import logging

from app import paths
from app.logging_setup import setup_logging


def test_dev_paths_resolve() -> None:
    assert paths.APP_ROOT.name == "windows"
    assert (paths.PROJECT_ROOT / "MAYA AI").is_dir()
    assert paths.settings_available()


def test_maya_ai_home_override(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(paths.MAYA_AI_HOME_ENV, str(tmp_path))
    assert paths.maya_ai_dir() == tmp_path
    assert paths.settings_path() == tmp_path / "config" / "settings.yaml"


def test_logging_writes_rotating_file(tmp_path) -> None:
    log_file = tmp_path / "app.log"
    logger = setup_logging(log_file=log_file)
    logger.info("phase0 smoke line")

    for handler in logging.getLogger().handlers:
        handler.flush()

    assert log_file.is_file()
    assert "phase0 smoke line" in log_file.read_text(encoding="utf-8")

    # Close handlers so Windows can release the file.
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()


def test_empty_window_builds(qapp) -> None:
    from app.main import create_main_window

    window = create_main_window()
    assert window.windowTitle() == "Maya AI"
    assert window.width() >= 1
    assert window.height() >= 1
