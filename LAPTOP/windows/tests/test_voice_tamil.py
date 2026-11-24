"""Tamil voice smoke tests (TTS + STT routing)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.voice_service import VoiceAdapter, VoiceError


def test_piper_tamil_synthesize_wav(tmp_path: Path) -> None:
    model = Path("MAYA AI/voice/tamil/ta_IN-ValluvarNeural-medium.onnx")
    if not model.is_file():
        pytest.skip("Tamil Piper model not installed")
    from custom.tools import voice as voice_tools

    tts = voice_tools.tts_tamil
    if not tts.is_available():
        pytest.skip("Piper Tamil not available")
    target = tmp_path / "out.wav"
    err = tts.synthesize_wav("வணக்கம்", target)
    assert err == ""
    assert target.is_file() and target.stat().st_size > 44


def test_tamil_status_reports_availability() -> None:
    adapter = VoiceAdapter()
    st = adapter.status()
    assert "whisper_available" in st["stt"]
    assert "tamil_stt_available" in st["stt"]
    assert "tamil_available" in st["tts"]


def test_tamil_without_whisper_raises(monkeypatch) -> None:
    import custom.tools.voice as voice_tools

    monkeypatch.setattr(voice_tools, "HAS_WHISPER", False)
    adapter = VoiceAdapter()
    with pytest.raises(VoiceError):
        adapter.listen_once(seconds=1, lang="ta")
