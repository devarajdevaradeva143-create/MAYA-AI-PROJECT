"""W4: LockScreen accepts on right PIN, stays open on wrong PIN."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QDialog

from app.ui.lock_screen import LockScreen


class _FakeSecurity:
    def __init__(self) -> None:
        self._ok = False

    def session_locked(self) -> bool:
        return True

    def verify_pin(self, pin: str) -> str:
        if pin == "1234":
            self._ok = True
            return "Unlocked. Maya is ready."
        return "Wrong PIN. 4 attempt(s) remaining."

    def face_verify(self) -> dict:
        return {"ok": False, "error": "no hello"}

    def unlock(self, method: str = "pin") -> str:
        return "ok"


@pytest.fixture
def screen(qtbot):
    svc = _FakeSecurity()
    dlg = LockScreen(svc)
    qtbot.addWidget(dlg)
    return dlg, svc


def test_wrong_pin_stays_open(screen) -> None:
    dlg, svc = screen
    dlg._pin.setText("0000")
    dlg._unlock_pin()
    assert dlg.result() != int(QDialog.DialogCode.Accepted)
    assert "Wrong" in dlg._msg.text()


def test_right_pin_accepts(screen) -> None:
    dlg, svc = screen
    dlg._pin.setText("1234")
    dlg._unlock_pin()
    assert dlg.result() == int(QDialog.DialogCode.Accepted)
