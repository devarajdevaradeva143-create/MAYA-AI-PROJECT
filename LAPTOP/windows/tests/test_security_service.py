"""W4: SecurityService wraps SecurityManager; no plaintext PIN."""

from __future__ import annotations

from pathlib import Path

import pytest
from custom.tools.security import SecurityManager

from app.services.security_service import SecurityService


@pytest.fixture
def service(tmp_path: Path):
    store = tmp_path / "security.json"
    mgr = SecurityManager(path=store)
    return SecurityService(manager=mgr), store


def test_pin_set_and_verify(service) -> None:
    svc, store = service
    assert svc.pin_is_set() is False
    msg = svc.set_pin("1234")
    assert "PIN set" in msg or "locked" in msg.lower()
    assert svc.pin_is_set() is True
    assert svc.verify_pin("1234").lower().startswith("unlocked")
    assert svc.verify_pin("9999").lower().startswith("wrong")


def test_no_plaintext_pin(service) -> None:
    svc, store = service
    svc.set_pin("4321")
    text = store.read_text(encoding="utf-8")
    assert "4321" not in text
    assert "pin_hash" in text
    assert "salt" in text


def test_change_pin_requires_old(service) -> None:
    svc, store = service
    svc.set_pin("1111")
    # wrong old pin
    msg = svc.set_pin("2222", old_pin="0000")
    assert "wrong" in msg.lower() or "current pin" in msg.lower()
    assert svc.verify_pin("1111").lower().startswith("unlocked")
    # correct old pin
    msg = svc.set_pin("2222", old_pin="1111")
    assert "pin set" in msg.lower() or "locked" in msg.lower()
    assert svc.verify_pin("2222").lower().startswith("unlocked")


def test_lockout_after_five_failures(service) -> None:
    svc, store = service
    svc.set_pin("1234")
    for _ in range(5):
        svc.verify_pin("0000")
    msg = svc.verify_pin("0000")
    assert "locked out" in msg.lower() or "locked" in msg.lower()


def test_session_locked_flag(service) -> None:
    svc, store = service
    assert svc.session_locked() is False
    svc.set_pin("1234")
    assert svc.session_locked() is True
    svc.unlock("pin")  # already verified? unlock may say already
    # verify_pin unlocks
    svc.verify_pin("1234")
    assert svc.session_locked() is False
