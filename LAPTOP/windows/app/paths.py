r"""Path resolution for the Maya Windows app (source and packaged).

Rules (plan section 17):
- Dev: APP_ROOT = LAPTOP\windows, PROJECT_ROOT = project folder.
- Packaged: APP_ROOT = folder that holds mayaai.exe (MAYA AI\ sits next to it).
  `__file__` lives in the PyInstaller temp extraction folder, so the exe
  location (`sys.executable`) is the only reliable anchor there.
- Writable fallback when the install folder is read-only:
  %LOCALAPPDATA%\MayaAI\data.

Every caller gets a Path; nothing here reads chat content or personal data.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "MayaAI"
MAYA_AI_HOME_ENV = "MAYA_AI_HOME"
MAYA_DATA_HOME_ENV = "MAYA_DATA_HOME"

# How far up from the exe we look for a `MAYA AI\config\settings.yaml`.
_FROZEN_SEARCH_DEPTH = 5


def is_frozen() -> bool:
    """True when running from a PyInstaller build."""
    return bool(getattr(sys, "frozen", False) or getattr(os, "frozen", False))


def app_root() -> Path:
    """Folder that contains the app code (dev) or the exe (packaged)."""
    if is_frozen():
        executable = getattr(sys, "executable", "") or ""
        if executable:
            return Path(executable).resolve().parent
        # Last resort: the temp extraction folder (never write there).
        return Path(__file__).resolve().parents[1]
    return Path(__file__).resolve().parents[1]


APP_ROOT = app_root()
PROJECT_ROOT = APP_ROOT if is_frozen() else APP_ROOT.parents[1]


def _has_settings(path: Path) -> bool:
    return (path / "config" / "settings.yaml").is_file()


def _candidate_maya_dirs() -> list[Path]:
    r"""Every plausible `MAYA AI\` location, most specific first."""
    candidates: list[Path] = []

    def add(path: Path) -> None:
        if path not in candidates:
            candidates.append(path)

    add(APP_ROOT / "MAYA AI")
    if is_frozen():
        # dist\ -> windows\ -> LAPTOP\ -> project root -> Desktop
        for parent in list(APP_ROOT.parents)[:_FROZEN_SEARCH_DEPTH]:
            add(parent / "MAYA AI")
        # exe dropped inside `MAYA AI\` itself
        add(APP_ROOT)
    else:
        add(PROJECT_ROOT / "MAYA AI")
    return candidates


def maya_ai_dir() -> Path:
    r"""The `MAYA AI\` folder (config, model, voice, memory, logs)."""
    override = os.environ.get(MAYA_AI_HOME_ENV, "").strip()
    if override:
        path = Path(override).expanduser()
        # A packaged build ignores a stale override that has no settings file.
        if not is_frozen() or _has_settings(path):
            return path

    candidates = _candidate_maya_dirs()
    for candidate in candidates:
        if _has_settings(candidate):
            return candidate
    return candidates[0]


def export_maya_ai_home() -> Path:
    r"""Point `MAYA_AI_HOME` at the resolved folder so `custom.config` agrees.

    `JARVIS\custom` derives `PROJECT_ROOT` from its own `__file__`, which in a
    frozen build is the PyInstaller temp folder. Publishing the resolved path
    keeps one source of truth for both halves of the app.
    """
    resolved = maya_ai_dir()
    if _has_settings(resolved):
        os.environ[MAYA_AI_HOME_ENV] = str(resolved)
    return resolved


def config_dir() -> Path:
    return maya_ai_dir() / "config"


def settings_path() -> Path:
    return config_dir() / "settings.yaml"


def models_dir() -> Path:
    return maya_ai_dir() / "Model"


def voice_dir() -> Path:
    return maya_ai_dir() / "voice"


def persona_dir() -> Path:
    return maya_ai_dir() / "persona"


def knowledge_dir() -> Path:
    return maya_ai_dir() / "knowledge"


def _is_writable(path: Path) -> bool:
    """Check without creating a missing folder (missing means fallback)."""
    if not path.is_dir():
        return False
    probe = path / ".maya_write_probe"
    try:
        probe.write_text("", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def data_root() -> Path:
    """Writable root for logs, memory and stores."""
    override = os.environ.get(MAYA_DATA_HOME_ENV)
    if override:
        return Path(override).expanduser()

    base = maya_ai_dir()
    if _is_writable(base):
        return base
    local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(local) / APP_NAME / "data"


def logs_dir() -> Path:
    return data_root() / "logs"


def memory_dir() -> Path:
    return data_root() / "memory"


def offline_memory_dir() -> Path:
    return memory_dir() / "offline"


def devices_store_dir() -> Path:
    return offline_memory_dir() / "devices"


def app_log_path() -> Path:
    return logs_dir() / "app.log"


def server_log_path() -> Path:
    return logs_dir() / "server.log"


def audit_log_path() -> Path:
    return logs_dir() / "control_audit.jsonl"


def backups_dir() -> Path:
    """Settings backups; falls back to the data root when config is read-only."""
    preferred = config_dir() / "backups"
    if _is_writable(preferred) or _is_writable(config_dir()):
        return preferred
    return data_root() / "backups"


def ensure_runtime_dirs() -> None:
    """Create the folders the app writes to. Safe to call more than once."""
    for path in (logs_dir(), offline_memory_dir(), devices_store_dir(), backups_dir()):
        path.mkdir(parents=True, exist_ok=True)


def settings_available() -> bool:
    return settings_path().is_file()
