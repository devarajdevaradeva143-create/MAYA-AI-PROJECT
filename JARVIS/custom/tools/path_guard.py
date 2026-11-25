"""Path guard: validates that a file path is inside allowed roots.

Per AGENTS.md: important actions need explicit user permission.
This guard checks that a requested path is within the permitted root directories,
so that file operations never escape the user's laptop.
"""

from __future__ import annotations

from pathlib import Path

# These are the allowed roots — set from settings.yaml "server.allowed_roots"
# or default to the user's desktop/My Documents area.
_ALLOWED_ROOTS: tuple[Path, ...] = (Path.home(),)

# Populate from settings when available.
# The server_service.py sets this at startup.
try:
    from app.services.server_service import server_settings  # noqa: F401 — sets _ALLOWED_ROOTS
except ImportError:
    pass


def is_path_allowed(path: Path | str) -> bool:
    """Return True if *path* is inside one of the allowed roots."""
    p = Path(path).resolve()
    for root in _ALLOWED_ROOTS:
        try:
            p.relative_to(Path(root).resolve())
            return True
        except ValueError:
            continue
    return False


def restrict_to_allowed(path: Path | str) -> Path | None:
    """Return the path if it's inside an allowed root, otherwise None."""
    p = Path(path).resolve()
    for root in _ALLOWED_ROOTS:
        try:
            p.relative_to(Path(root).resolve())
            return p  # allowed
        except ValueError:
            continue
    return None


__all__ = ["is_path_allowed", "restrict_to_allowed"]