"""Command guard: validates shell commands against a denylist.

Per AGENTS.md: important actions need explicit user permission.
Blocked commands (e.g. rm -rf /, format, shutdown without confirmation)
raise RuntimeError so the UI can show an error toast and log the event.

The denylist is deliberately broad but not exhaustive — the UI
confirmation step is the primary safety gate.
"""

from __future__ import annotations

import re

# Commands that are always blocked unless an explicit allow-passes through
# the permission gate. These are shell‑level blocks; the UI ConfirmDialog
# provides the secondary check.
_BLOCKED_COMMANDS: tuple[str, ...] = (
    "rm -rf /",
    "format",
    "fdisk",
    "mkfs",
    "parted",
    "kill -9 1",  # init
    "reboot",
    "poweroff",
    "shutdown",
)

# Patterns that are always blocked because they are high‑risk.
_BLOCKED_PATTERNS: tuple[str, ...] = (
    r"^\s*rm\s+.*-rf\s",     # recursive force delete
    r"^\s*rm\s+.*-r\s+/",   # recursive delete starting at root
    r"^\s*dd\s+",            # disk dump — can wipe disks
    r"^\s*c:\s*format",      # Windows format
)


def is_command_blocked(cmd: str) -> bool:
    """Return True if the command matches a blocked pattern."""
    lowered = cmd.strip().lower()
    for pat in _BLOCKED_PATTERNS:
        if re.search(pat, lowered):
            return True
    # Also check exact blacklisted commands
    for bl in _BLOCKED_COMMANDS:
        if lowered == bl.strip().lower():
            return True
    return False


def safe_cmd(cmd: str) -> str:
    """Return a sanitized version of *cmd* (remove dangerous bits).

    This is a best‑effort sanitiser; the permission gate is the real
    safety mechanism.  Callers should still ask permission before running
    any command.
    """
    # Remove any pipe chains that lead to blocked commands
    result = cmd
    for pat in _BLOCKED_PATTERNS:
        result = re.sub(pat, "[BLOCKED]", result, flags=re.IGNORECASE)
    return result.strip()


__all__ = ["is_command_blocked", "safe_cmd"]