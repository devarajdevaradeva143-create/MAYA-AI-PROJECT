"""Voiceprint wizard tests."""

from __future__ import annotations

from unittest.mock import MagicMock

from PySide6.QtWidgets import QDialog

from app.services.security_service import SecurityService
from app.ui.voiceprint_wizard import VoiceprintWizard


def _fake_security(ready: bool = True) -> MagicMock:
    sec = MagicMock(spec=SecurityService)
    sec.voice_enroll_ready.return_value = {
        "ready": ready,
        "speaker_model": ready,
        "mic": ready,
        "reasons": [] if ready else ["no mic"],
    }
    sec.voice_capture_sample.return_value = {
        "ok": True,
        "text": "maya open the door",
        "vector": [0.1, 0.2],
        "error": None,
    }
    sec.voice_enroll.return_value = {"ok": True}
    return sec


def test_not_ready_disables_record(qtbot) -> None:
    sec = _fake_security(ready=False)
    w = VoiceprintWizard(sec)
    qtbot.addWidget(w)
    assert not w._record_btn.isEnabled()


def test_three_samples_enable_finish(qtbot) -> None:
    sec = _fake_security(ready=True)
    w = VoiceprintWizard(sec)
    qtbot.addWidget(w)
    w._samples_needed = 3
    w._progress.setRange(0, 3)
    for _ in range(3):
        w._record()
        # simulate worker callback synchronously
        w._on_captured(sec.voice_capture_sample(5), w._generation)
    assert w._finish_btn.isEnabled()


def test_finish_calls_enroll(qtbot) -> None:
    sec = _fake_security(ready=True)
    w = VoiceprintWizard(sec)
    qtbot.addWidget(w)
    w._samples_needed = 1
    w._progress.setRange(0, 1)
    w._record()
    w._on_captured(sec.voice_capture_sample(5), w._generation)
    w._finish()
    assert sec.voice_enroll.called
    assert w.result() == QDialog.DialogCode.Accepted
