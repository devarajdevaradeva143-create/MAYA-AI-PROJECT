"""Shared test setup."""

from __future__ import annotations

import os

import pytest

# Qt must never need a display in tests.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(autouse=True)
def _isolate_chat_history(tmp_path, monkeypatch):
    """Never let a test write to the real MAYA AI/memory/offline store."""
    monkeypatch.setenv("MAYA_CHAT_HISTORY", str(tmp_path / "chat_history.json"))
    yield
