r"""Maya AI configuration loader.

Loads settings from `MAYA AI\config\settings.yaml` per AGENTS.md.
Path resolution: custom/config.py -> go up 3 levels -> MAYA AI/config/settings.yaml
"""

import os
import sys
from pathlib import Path

import yaml

# Ensure click is available for echo fallback
try:
    import click
except ImportError:
    click = None


# Resolve path: custom/ -> go up 2 levels -> project root -> MAYA AI/
# custom/ is at JARVIS/custom/
# go up: JARVIS/ -> MAYA AI PROJECT/ (parents[1])
# Then: MAYA AI/config/settings.yaml
#
# Packaged (PyInstaller) builds do not keep this file in the project tree, so
# `__file__` points into the temp extraction folder. There the folder is found
# through MAYA_AI_HOME (published by the Windows app) or by walking up from the
# running exe. Dev behaviour is unchanged.
_CUSTOM_DIR = Path(__file__).resolve().parent
MAYA_AI_HOME_ENV = "MAYA_AI_HOME"
_FROZEN_SEARCH_DEPTH = 5


def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _has_settings(root: Path) -> bool:
    return (root / "MAYA AI" / "config" / "settings.yaml").is_file()


def _resolve_project_root() -> Path:
    """Folder that holds `MAYA AI/`, `JARVIS/` and `.env`."""
    home = os.environ.get(MAYA_AI_HOME_ENV, "").strip()
    if home:
        candidate = Path(home).expanduser()
        # MAYA_AI_HOME points at the `MAYA AI/` folder itself.
        if (candidate / "config" / "settings.yaml").is_file():
            return candidate.parent
        if not _is_frozen():
            return candidate.parent

    if _is_frozen():
        executable = getattr(sys, "executable", "") or ""
        if executable:
            exe_dir = Path(executable).resolve().parent
            for base in [exe_dir, *list(exe_dir.parents)[:_FROZEN_SEARCH_DEPTH]]:
                if _has_settings(base):
                    return base
        # Not installed next to the project: keep everything under the exe.
        return Path(executable).resolve().parent if executable else _CUSTOM_DIR.parents[1]

    return _CUSTOM_DIR.parents[1]


PROJECT_ROOT = _resolve_project_root()  # MAYA AI PROJECT
MAYA_AI_CONFIG = PROJECT_ROOT / "MAYA AI" / "config" / "settings.yaml"


def load_settings() -> dict:
    """Load Maya AI settings from settings.yaml.

    Returns the settings dict. If the file doesn't exist,
    returns a sensible default config.

    The YAML file is the source of truth for all Maya settings.
    Code should NOT hardcode settings — read from this config.
    """
    if not MAYA_AI_CONFIG.is_file():
        # Fallback: return minimal defaults
        if click:
            click.echo(
                f"[config] Warning: {MAYA_AI_CONFIG} not found. "
                "Using default settings.",
                err=True,
            )
        else:
            print(f"[config] Warning: {MAYA_AI_CONFIG} not found. Using default settings.", file=sys.stderr)
        return _default_settings()

    try:
        with open(MAYA_AI_CONFIG, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if data is None:
            return _default_settings()
        if isinstance(data, dict):
            _warn_legacy_keys(data)
        return data
    except Exception as exc:
        if click:
            click.echo(
                f"[config] Error reading {MAYA_AI_CONFIG}: {exc}. "
                "Using default settings.",
                err=True,
            )
        else:
            print(f"[config] Error reading {MAYA_AI_CONFIG}: {exc}. Using default settings.", file=sys.stderr)
        return _default_settings()


def _warn_legacy_keys(data: dict) -> None:
    """Warn about pre-`engine.model` keys so old configs get migrated."""
    if "model" not in data and "mode_model" not in data:
        return
    message = (
        "[config] Legacy key(s) 'model'/'mode_model' ignored; "
        "use engine.model in settings.yaml."
    )
    if click:
        click.echo(message, err=True)
    else:
        print(message, file=sys.stderr)


def _default_settings() -> dict:
    """Return default Maya settings when config file is missing."""
    return {
        "mode": "offline",
        "hardware": "auto",
        "language": "tanglish",
        "behaviour": "command_only",
        "autonomous": "false",
        "runtime": "background",
        "autostart": "true",
        "wake": {
            "enabled": True,
            "name": "Maya",
            "name_repeat": 3,
            "clap_count": 3,
            "reply": "Sollu da, enna venum?",
        },
        "voice": {
            "tts": {"engine": "auto", "preferred_voices": ["heera", "neerja"]},
            "stt": {"engine": "vosk", "listen_seconds": 6, "models": {}},
            "clap": {"threshold": 2800, "count": 3, "min_gap": 0.12, "max_gap": 0.9},
        },
        "persona": "girlfriend",
        "web_search": "ask",
        "web_allowed_topics": "news,world news,ai,it,technology",
        "memory_offline": "memory/offline",
        "memory_online": "memory/online",
        "flow_online_to_offline": "true",
        "flow_offline_to_online": "false",
        "privacy_personal_details_online": "false",
        "privacy_send_personal_details": "false",
        "privacy_offline_memory_online": "false",
        "privacy_biometrics_local_only": "true",
        "permissions_offline_ai": "full",
        "permissions_read": "allow",
        "permissions_edit": "ask",
        "permissions_delete": "ask",
        "permissions_important": "ask",
        "permissions_shell": "ask",
        "features_chat": "true",
        "features_voice": "partial",
        "features_pc_control": "true",
        "features_mobile_control": "plan",
        "features_english_teacher": "true",
        "features_identity_security": "partial",
        "features_system_monitoring": "true",
        "features_personal_assistant": "partial",
        "features_knowledge_ai": "true",
        "features_language_intelligence": "partial",
        "features_multi_device": "partial",
        "english_teacher_tab": "true",
        "english_teacher_chat_command": "true",
        "security_mode": "adaptive",
        "security_methods": "face,voice,pin",
        "security_biometrics_local_only": "true",
        "security_unauthorized_alert": "true",
    }


# Backward-compatible accessor for the old import style
def get_settings() -> dict:
    """Deprecated: use load_settings() instead."""
    import warnings
    warnings.warn(
        "get_settings() is deprecated, use load_settings()",
        DeprecationWarning,
        stacklevel=2,
    )
    return load_settings()