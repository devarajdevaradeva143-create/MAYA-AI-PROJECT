"""Voice STT/TTS/status endpoint tests."""

from __future__ import annotations

import io
import wave

from tests.fakes import auth, error_code, make_harness, pair_device

STT = "/api/v1/voice/stt"
TTS = "/api/v1/voice/tts"
STATUS = "/api/v1/voice/status"


def wav_bytes(seconds: float = 1.0, rate: int = 16000) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(b"\x00\x00" * int(rate * seconds))
    return buffer.getvalue()


def _upload(harness, token: str, data: bytes, lang: str = "en"):
    return harness.client.post(
        STT,
        files={"audio": ("clip.wav", data, "audio/wav")},
        data={"lang": lang, "duration_ms": "1000"},
        headers=auth(token),
    )


def test_stt_returns_text(tmp_path) -> None:
    harness = make_harness(tmp_path)
    token = pair_device(harness)

    response = _upload(harness, token, wav_bytes())

    assert response.status_code == 200
    assert response.json() == {"text": "enna time", "lang": "en", "engine": "vosk"}


def test_stt_accepts_tamil_lang(tmp_path) -> None:
    harness = make_harness(tmp_path)
    token = pair_device(harness)

    response = _upload(harness, token, wav_bytes(), lang="ta")

    assert response.status_code == 200
    assert response.json()["lang"] == "ta"


def test_stt_rejects_unsupported_language(tmp_path) -> None:
    harness = make_harness(tmp_path)
    token = pair_device(harness)

    response = _upload(harness, token, wav_bytes(), lang="fr")

    assert response.status_code == 400
    assert error_code(response) == 2001


def test_stt_rejects_non_wav_bytes(tmp_path) -> None:
    harness = make_harness(tmp_path)
    token = pair_device(harness)

    response = _upload(harness, token, b"definitely not audio")

    assert response.status_code == 400
    assert error_code(response) == 2001


def test_stt_rejects_audio_over_30_seconds(tmp_path) -> None:
    harness = make_harness(tmp_path)
    token = pair_device(harness)

    response = _upload(harness, token, wav_bytes(seconds=31))

    assert response.status_code == 400
    assert error_code(response) == 2001


def test_stt_rejects_file_over_5mb(tmp_path) -> None:
    harness = make_harness(tmp_path)
    token = pair_device(harness)

    response = _upload(harness, token, b"\x00" * (5 * 1024 * 1024 + 1))

    assert response.status_code == 413
    assert error_code(response) == 2003


def test_stt_missing_audio_is_2001(tmp_path) -> None:
    harness = make_harness(tmp_path)
    token = pair_device(harness)

    response = harness.client.post(STT, data={"lang": "en"}, headers=auth(token))

    assert response.status_code == 400
    assert error_code(response) == 2001


def test_stt_unavailable_maps_to_3003(tmp_path) -> None:
    harness = make_harness(tmp_path, voice_available=False)
    token = pair_device(harness)

    response = _upload(harness, token, wav_bytes())

    assert response.status_code == 503
    assert error_code(response) == 3003


def test_stt_rate_limit_is_10_per_minute(tmp_path) -> None:
    harness = make_harness(tmp_path)
    token = pair_device(harness)
    data = wav_bytes()

    for _ in range(10):
        assert _upload(harness, token, data).status_code == 200

    blocked = _upload(harness, token, data)

    assert blocked.status_code == 429
    assert error_code(blocked) == 1005


def test_stt_temp_file_is_removed(tmp_path) -> None:
    harness = make_harness(tmp_path)
    token = pair_device(harness)

    response = _upload(harness, token, wav_bytes())

    assert response.status_code == 200
    assert harness.voice.last_wav_path is not None
    assert not harness.voice.last_wav_path.exists()


def test_tts_returns_wav_and_cleans_up(tmp_path) -> None:
    harness = make_harness(tmp_path)
    token = pair_device(harness)

    response = harness.client.post(
        TTS,
        json={"text": "Vanakkam da", "engine": "sapi", "voice": "heera", "lang": "en", "speed": 1.2},
        headers=auth(token),
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/wav")
    assert response.content[:4] == b"RIFF"
    assert harness.voice.last_extras == {
        "text": "Vanakkam da",
        "engine": "sapi",
        "voice": "heera",
        "lang": "en",
        "speed": 1.2,
    }
    # BackgroundTask deleted the temp file after the response.
    assert not (tmp_path / "tts-out.wav").exists()


def test_tts_rejects_empty_and_long_text(tmp_path) -> None:
    harness = make_harness(tmp_path)
    token = pair_device(harness)

    empty = harness.client.post(TTS, json={"text": ""}, headers=auth(token))
    too_long = harness.client.post(TTS, json={"text": "a" * 1001}, headers=auth(token))

    assert empty.status_code == 400
    assert error_code(empty) == 2001
    assert too_long.status_code == 400
    assert error_code(too_long) == 2001


def test_tts_rejects_bad_speed_and_engine(tmp_path) -> None:
    harness = make_harness(tmp_path)
    token = pair_device(harness)

    slow = harness.client.post(TTS, json={"text": "hi", "speed": 0.4}, headers=auth(token))
    bad_engine = harness.client.post(
        TTS,
        json={"text": "hi", "engine": "cloud"},
        headers=auth(token),
    )

    assert slow.status_code == 400
    assert error_code(slow) == 2001
    assert bad_engine.status_code == 400
    assert error_code(bad_engine) == 2001


def test_tts_unavailable_maps_to_3004(tmp_path) -> None:
    harness = make_harness(tmp_path, voice_available=False)
    token = pair_device(harness)

    response = harness.client.post(TTS, json={"text": "hi"}, headers=auth(token))

    assert response.status_code == 503
    assert error_code(response) == 3004


def test_voice_status_shape(tmp_path) -> None:
    harness = make_harness(tmp_path)
    token = pair_device(harness)

    response = harness.client.get(STATUS, headers=auth(token))

    assert response.status_code == 200
    body = response.json()
    assert body["stt"]["engine"] in {"auto", "vosk", "whisper"}
    assert body["stt"]["available"] is True
    assert body["tts"]["engine"] == "sapi"
    assert body["tts"]["voices"] == ["heera"]


def test_tts_missing_body_is_2001(tmp_path) -> None:
    harness = make_harness(tmp_path)
    token = pair_device(harness)

    response = harness.client.post(TTS, json={}, headers=auth(token))

    assert response.status_code == 400
    assert error_code(response) == 2001


def test_voice_requires_auth(tmp_path) -> None:
    harness = make_harness(tmp_path)

    response = harness.client.get(STATUS)

    assert response.status_code == 401
    assert error_code(response) == 1001
