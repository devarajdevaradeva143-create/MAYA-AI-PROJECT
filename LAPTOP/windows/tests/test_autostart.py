"""Autostart registry tests (winreg mocked)."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest

from app.services import autostart_service as svc


@pytest.fixture
def fake_winreg(monkeypatch):
    """Provide a fake winreg module so tests run on any OS."""
    fake = MagicMock()
    fake.HKEY_CURRENT_USER = "HKCU"
    fake.KEY_SET_VALUE = 1
    fake.REG_SZ = "REG_SZ"
    fake.OpenKey = MagicMock()
    fake.QueryValueEx = MagicMock()
    fake.SetValueEx = MagicMock()
    fake.DeleteValue = MagicMock()
    fake.FileNotFoundError = FileNotFoundError
    monkeypatch.setattr(svc, "sys", sys)  # keep platform check
    # Force win32 path.
    monkeypatch.setattr(svc, "_is_windows", lambda: True, raising=False)
    return fake


def test_enable_disable_roundtrip(monkeypatch, fake_winreg):
    # Patch sys.platform to win32 for the duration.
    monkeypatch.setattr(svc.sys, "platform", "win32")
    monkeypatch.setattr("builtins.__import__", lambda name, *a, **k: fake_winreg if name == "winreg" else __import__(name, *a, **k))

    # OpenKey returns a context manager.
    cm = MagicMock()
    fake_winreg.OpenKey.return_value.__enter__.return_value = cm

    assert svc.enable_autostart() is True
    assert fake_winreg.SetValueEx.called

    # disable is idempotent.
    fake_winreg.DeleteValue.side_effect = FileNotFoundError
    assert svc.disable_autostart() is True


def test_is_enabled_false_when_missing(monkeypatch, fake_winreg):
    monkeypatch.setattr(svc.sys, "platform", "win32")
    monkeypatch.setattr("builtins.__import__", lambda name, *a, **k: fake_winreg if name == "winreg" else __import__(name, *a, **k))
    cm = MagicMock()
    fake_winreg.OpenKey.return_value.__enter__.return_value = cm
    fake_winreg.QueryValueEx.side_effect = FileNotFoundError
    assert svc.is_autostart_enabled() is False
