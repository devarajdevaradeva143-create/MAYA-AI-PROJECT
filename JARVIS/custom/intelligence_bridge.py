"""Bridge the laptop CLI to the MAYA INTELLIGENCE orchestrator.

The intelligence package may be missing in a stripped install, so everything
here is lazy and defensive: :attr:`IntelligenceBridge.available` is ``False``
when the package cannot load, and the CLI keeps working with the classic
engine chat.

Nothing in ``custom/`` imports this module at startup — only the ``chat`` and
``ask`` commands do, so command startup stays fast.
"""

from __future__ import annotations

import sys
import os
from pathlib import Path
from typing import Any, Callable

from .config import PROJECT_ROOT

#: Candidate locations for the MAYA INTELLIGENCE package.
def _candidate_intel_roots() -> list[Path]:
    candidates: list[Path] = []
    # Frozen (PyInstaller): bundled under _MEIPASS
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "MAYA INTELLIGENCE")
    # Dev / project root
    candidates.append(PROJECT_ROOT / "MAYA INTELLIGENCE")
    # Next to the executable / app root
    try:
        exe_dir = Path(sys.executable).resolve().parent
        candidates.append(exe_dir / "MAYA INTELLIGENCE")
    except Exception:
        pass
    # Environment override
    env = os.environ.get("MAYA_INTEL_ROOT", "").strip()
    if env:
        candidates.append(Path(env).expanduser())
    # Deduplicate
    seen: set[str] = set()
    unique: list[Path] = []
    for c in candidates:
        key = str(c)
        if key not in seen:
            seen.add(key)
            unique.append(c)
    return unique


def _find_intel_root() -> Path:
    for c in _candidate_intel_roots():
        if (c / "maya_intelligence" / "orchestrator.py").is_file():
            return c
    # Fall back to first candidate
    return _candidate_intel_roots()[0]


_INTEL_ROOT = _find_intel_root()

#: Appended to laptop personas (girlfriend / english_teacher) so the smart
#: layer's accuracy and language rules still apply.
OPERATING_RULES = """## Operating Rules (strict)
1. Mirror the user's language exactly: English -> English, Tamil -> Tamil,
   Tanglish -> Tanglish. Never switch language on your own.
2. Answer first, explain after. Keep simple answers to 1-4 sentences.
3. Be accurate. Never guess a calculation, date, or fact. If unsure, say so.
4. Plain text only: no LaTeX, no $...$ math, no markdown tables unless asked.
5. Never invent memories. Only use facts given in the context.
6. Never claim an action succeeded unless the tool result confirms it.
7. Do not repeat the user's question back to them.
8. Do not pad answers with filler or repeated offers of help."""


def _ask_confirmation(message: str) -> bool:
    """Ask the user before important actions; default to No on any error."""
    try:
        import click

        return bool(click.confirm(message, default=False))
    except Exception:
        return False


class IntelligenceBridge:
    """Thin wrapper around :class:`maya_intelligence.orchestrator.Orchestrator`."""

    def __init__(self, confirm_fn: Callable[[str], bool] | None = None):
        self._confirm_fn = confirm_fn or _ask_confirmation
        self._orchestrator: Any | None = None
        self._persona_prompt: str = ""
        self._init_error: str = ""

    # ── Lifecycle ────────────────────────────────────────────────────
    def _ensure(self):
        """Create the orchestrator on first use."""
        if self._orchestrator is not None:
            return self._orchestrator
        if self._init_error:
            raise RuntimeError(self._init_error)

        try:
            if str(_INTEL_ROOT) not in sys.path:
                sys.path.insert(0, str(_INTEL_ROOT))

            from maya_intelligence.orchestrator import Orchestrator

            persona = None
            if self._persona_prompt:
                persona = f"{self._persona_prompt}\n\n{OPERATING_RULES}"
            self._orchestrator = Orchestrator(
                confirm_fn=self._confirm_fn,
                persona=persona,
            )
            return self._orchestrator
        except Exception as exc:  # pragma: no cover - depends on install
            self._init_error = f"{type(exc).__name__}: {exc}"
            raise

    @property
    def available(self) -> bool:
        """True when the intelligence layer can be loaded."""
        try:
            self._ensure()
            return True
        except Exception:
            return False

    @property
    def init_error(self) -> str:
        """Human-readable load error (empty when everything is fine)."""
        return self._init_error

    def close(self) -> None:
        """Release the engine connection and memory store."""
        if self._orchestrator is not None:
            try:
                self._orchestrator.close()
            except Exception:
                pass
            self._orchestrator = None

    # ── Chat ─────────────────────────────────────────────────────────
    def chat(self, text: str) -> str:
        """Send one message and return Maya's reply."""
        if not text or not text.strip():
            return ""
        try:
            orchestrator = self._ensure()
            return orchestrator.process(text).response
        except Exception as exc:
            return f"[engine error] Maya intelligence unavailable: {exc}"

    def clear(self) -> None:
        """Clear conversation history (persistent memory is kept)."""
        if self._orchestrator is not None:
            self._orchestrator.clear_history()

    def set_persona(self, prompt: str | None) -> None:
        """Set the laptop persona prompt (girlfriend / english_teacher)."""
        prompt = (prompt or "").strip()
        if not prompt:
            return
        self._persona_prompt = prompt
        if self._orchestrator is not None:
            self._orchestrator.set_persona(f"{prompt}\n\n{OPERATING_RULES}")

    def memory_stats(self) -> dict[str, Any]:
        """Return memory statistics for ``/memory`` style commands."""
        if self._orchestrator is None:
            return {}
        try:
            return self._orchestrator.get_memory_stats()
        except Exception:
            return {}
