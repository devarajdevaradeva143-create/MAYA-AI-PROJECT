"""Maya Intelligence — offline orchestration layer for Maya AI.

This package adds three engines (IQ/EQ/AQ) and a 10-step pipeline on top of
the existing ``JARVIS/custom/`` engine + tools. It is a new self-contained
package; it does **not** modify ``custom/`` or ``OpenJarvis/``.

Importing this package also bootstraps ``sys.path`` so ``import custom``
resolves to ``../JARVIS/custom`` (see :mod:`maya_intelligence._bootstrap`).
"""

from __future__ import annotations

# Make ``import custom`` work before anything else imports it.
from . import _bootstrap  # noqa: F401

from .orchestrator import Orchestrator
from .config import get_db_path, load_persona
from .memory import MemoryStore, MemoryEntry

__version__ = "0.1.0"
__all__ = [
    "__version__",
    "Orchestrator",
    "get_db_path",
    "load_persona",
    "MemoryStore",
    "MemoryEntry",
]