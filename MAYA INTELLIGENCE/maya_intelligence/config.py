"""Configuration for MAYA INTELLIGENCE."""

import os
from pathlib import Path


def get_project_root() -> Path:
    """Get the project root directory."""
    return Path(__file__).parent.parent.parent


def get_db_path() -> Path:
    """Get the default memory database path."""
    env_path = os.environ.get("MAYA_INTEL_DB")
    if env_path:
        return Path(env_path).expanduser().resolve()
    return get_project_root() / "MAYA AI" / "memory" / "offline" / "maya_intelligence.db"


def get_persona_path() -> Path:
    """Get the maya persona file path."""
    return Path(__file__).parent / "persona" / "maya.md"


def load_persona() -> str:
    """Load the maya persona prompt."""
    path = get_persona_path()
    if path.exists():
        return path.read_text(encoding="utf-8")
    return "You are Maya, a helpful offline AI assistant."


def load_settings() -> dict:
    """Load settings, reusing custom.config.load_settings if available."""
    try:
        from custom.config import load_settings as custom_load_settings
        return custom_load_settings()
    except ImportError:
        return {}