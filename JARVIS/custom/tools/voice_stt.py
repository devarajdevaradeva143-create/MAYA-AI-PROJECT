"""Offline speech-to-text with Vosk.

Ported from the user's earlier PA project (``Laptop/Voice/stt.py``) where it was
tuned against this exact laptop's microphone. Key hardware fact kept from there:

    Capturing at 16 kHz on this machine pitch-distorts the audio
    (a 1 kHz test tone came back as ~1536 Hz). Capture at 48 kHz and
    down-sample offline instead: anti-alias low-pass 7.2 kHz -> 16 kHz ->
    high-pass 120 Hz -> peak normalise.

Privacy: the temporary WAV is deleted as soon as it is transcribed, and no
transcript is written to disk.

Models live inside the project (``MAYA AI/Model/models/vosk-*``), never in the
cloud. Tamil is not supported by official Vosk models — ``available()`` reports
that honestly instead of faking it.
"""

from __future__ import annotations

import array
import ctypes
import json
import math
import os
import tempfile
import time
import wave
from ctypes import wintypes
from pathlib import Path
from typing import Any

from ..config import PROJECT_ROOT

# ── Paths ──────────────────────────────────────────────────────────────────

DEFAULT_MODEL_ROOT = PROJECT_ROOT / "MAYA AI" / "Model" / "models"

#: Official Vosk models that may be dropped in. ``ta`` is documented as absent.
DEFAULT_MODELS = {
    "en": "vosk-en",
    "en-in": "vosk-en-in",
    "ta": "vosk-ta",
}

# ── Audio constants (do not "optimise" without re-testing the mic) ─────────

REC_RATE = 48000
OUT_RATE = 16000
_ANTIALIAS_HZ = 7200
_HIGHPASS_HZ = 120
_NORMALIZE_PEAK = 0.8
SILENCE_PEAK = 150

WAVE_FORMAT_PCM = 1
WAVE_MAPPER = wintypes.UINT(-1).value
CALLBACK_NULL = 0
WHDR_DONE = 0x00000001

_IS_WINDOWS = os.name == "nt"
_winmm = ctypes.windll.winmm if _IS_WINDOWS else None

# Only one model is kept in RAM at a time.
_model: Any = None
_loaded_path: str | None = None


# ── Model paths ────────────────────────────────────────────────────────────

def _model_map() -> dict[str, Path]:
    """Resolve model folders, allowing settings.yaml overrides."""
    try:
        from ..config import load_settings

        settings = load_settings()
    except Exception:  # pragma: no cover - config must never crash voice
        settings = {}

    voice_cfg = settings.get("voice", {}) if isinstance(settings, dict) else {}
    stt_cfg = voice_cfg.get("stt", {}) if isinstance(voice_cfg, dict) else {}
    configured = stt_cfg.get("models", {}) if isinstance(stt_cfg, dict) else {}

    root = stt_cfg.get("model_root") if isinstance(stt_cfg, dict) else None
    root_path = Path(root).expanduser() if root else DEFAULT_MODEL_ROOT
    if not root_path.is_absolute():
        root_path = PROJECT_ROOT / root_path

    mapping: dict[str, Path] = {}
    for lang, default_name in DEFAULT_MODELS.items():
        name = configured.get(lang, default_name) if isinstance(configured, dict) else default_name
        path = Path(name).expanduser()
        mapping[lang] = path if path.is_absolute() else root_path / path
    return mapping


def available() -> dict[str, bool]:
    """Honest per-language model presence (no fake status)."""
    return {lang: path.is_dir() for lang, path in _model_map().items()}


def model_path(lang: str = "en") -> Path:
    mapping = _model_map()
    return mapping.get((lang or "en").lower(), mapping["en"])


# ── Pure DSP helpers (unit-testable, no mic needed) ────────────────────────

def _biquad(samples, b0, b1, b2, a1, a2):
    """Direct-form-II biquad — pure stdlib, no numpy/scipy."""
    out = array.array("d")
    append = out.append
    x1 = x2 = y1 = y2 = 0.0
    for s in samples:
        y = b0 * s + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
        x2, x1 = x1, s
        y2, y1 = y1, y
        append(y)
    return out


def _lowpass(samples, rate, cutoff):
    """Butterworth-ish 2-pole low-pass (anti-alias before down-sampling)."""
    w0 = 2.0 * math.pi * cutoff / rate
    cw = math.cos(w0)
    alpha = math.sin(w0) / (2.0 * 0.7071067811865476)
    a0 = 1.0 + alpha
    return _biquad(
        samples,
        (1.0 - cw) / 2.0 / a0,
        (1.0 - cw) / a0,
        (1.0 - cw) / 2.0 / a0,
        -2.0 * cw / a0,
        (1.0 - alpha) / a0,
    )


def _highpass(samples, rate, cutoff):
    """Butterworth-ish 2-pole high-pass (cuts fan / desk rumble)."""
    w0 = 2.0 * math.pi * cutoff / rate
    cw = math.cos(w0)
    alpha = math.sin(w0) / (2.0 * 0.7071067811865476)
    a0 = 1.0 + alpha
    return _biquad(
        samples,
        (1.0 + cw) / 2.0 / a0,
        -(1.0 + cw) / a0,
        (1.0 + cw) / 2.0 / a0,
        -2.0 * cw / a0,
        (1.0 - alpha) / a0,
    )


def _resample(x, in_rate, out_rate=OUT_RATE):
    """Linear-interpolation resample (48 kHz -> 16 kHz)."""
    if in_rate == out_rate:
        return x
    n_out = int(len(x) * out_rate / in_rate)
    step = in_rate / out_rate
    out = array.array("d", [0.0]) * n_out
    last = len(x) - 1
    for i in range(n_out):
        pos = i * step
        j = int(pos)
        frac = pos - j
        s0 = x[j] if j <= last else 0.0
        s1 = x[j + 1] if j < last else s0
        out[i] = s0 + (s1 - s0) * frac
    return out


def _prepare_for_vosk(data: bytes, rate: int = REC_RATE):
    """Raw PCM bytes -> clean 16 kHz int16 samples.

    Returns ``(samples, raw_peak)``. ``raw_peak`` is measured *before*
    normalisation so silence detection stays honest.
    """
    raw = array.array("h", data)
    if not raw:
        return array.array("h"), 0
    raw_peak = max(abs(s) for s in raw)

    x = [float(s) for s in raw]
    x = _lowpass(x, rate, _ANTIALIAS_HZ)
    x = _resample(x, rate, OUT_RATE)
    x = _highpass(x, OUT_RATE, _HIGHPASS_HZ)

    peak = max((abs(s) for s in x), default=0.0)
    gain = (_NORMALIZE_PEAK * 32767.0 / peak) if peak > 0 else 1.0
    out = array.array("h")
    append = out.append
    for s in x:
        v = int(s * gain)
        append(32767 if v > 32767 else (-32768 if v < -32768 else v))
    return out, raw_peak


# ── Microphone capture (Windows waveIn) ────────────────────────────────────

class WAVEFORMATEX(ctypes.Structure):
    _fields_ = [
        ("wFormatTag", wintypes.WORD),
        ("nChannels", wintypes.WORD),
        ("nSamplesPerSec", wintypes.DWORD),
        ("nAvgBytesPerSec", wintypes.DWORD),
        ("nBlockAlign", wintypes.WORD),
        ("wBitsPerSample", wintypes.WORD),
        ("cbSize", wintypes.WORD),
    ]


class WAVEHDR(ctypes.Structure):
    _fields_ = [
        ("lpData", ctypes.c_char_p),
        ("dwBufferLength", wintypes.DWORD),
        ("dwBytesRecorded", wintypes.DWORD),
        ("dwUser", ctypes.c_void_p),
        ("dwFlags", wintypes.DWORD),
        ("dwLoops", wintypes.DWORD),
        ("lpNext", ctypes.c_void_p),
        ("reserved", ctypes.c_void_p),
    ]


class WAVEINCAPSW(ctypes.Structure):
    _fields_ = [
        ("wMid", wintypes.WORD),
        ("wPid", wintypes.WORD),
        ("vDriverVersion", wintypes.UINT),
        ("szPname", wintypes.WCHAR * 32),
        ("dwFormats", wintypes.DWORD),
        ("wChannels", wintypes.WORD),
        ("wReserved1", wintypes.WORD),
    ]


if _winmm is not None:  # pragma: no branch - Windows only
    _winmm.waveInGetNumDevs.restype = wintypes.UINT
    _winmm.waveInGetDevCapsW.argtypes = [wintypes.UINT, ctypes.POINTER(WAVEINCAPSW), wintypes.UINT]
    _winmm.waveInOpen.argtypes = [
        ctypes.POINTER(ctypes.c_void_p), wintypes.UINT, ctypes.POINTER(WAVEFORMATEX),
        ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD,
    ]
    _winmm.waveInPrepareHeader.argtypes = [ctypes.c_void_p, ctypes.POINTER(WAVEHDR), wintypes.UINT]
    _winmm.waveInUnprepareHeader.argtypes = [ctypes.c_void_p, ctypes.POINTER(WAVEHDR), wintypes.UINT]
    _winmm.waveInAddBuffer.argtypes = [ctypes.c_void_p, ctypes.POINTER(WAVEHDR), wintypes.UINT]


def input_devices() -> list[tuple[int, str]]:
    """Microphone device names (honest status)."""
    if _winmm is None:
        return []
    out: list[tuple[int, str]] = []
    for i in range(_winmm.waveInGetNumDevs()):
        caps = WAVEINCAPSW()
        if _winmm.waveInGetDevCapsW(i, ctypes.byref(caps), ctypes.sizeof(caps)) == 0:
            out.append((i, caps.szPname))
    return out


def _pick_device() -> tuple[int, str]:
    devices = input_devices()
    for idx, name in devices:
        if "mic" in name.lower():
            return idx, name
    if devices:
        return devices[0]
    return WAVE_MAPPER, "(default)"


def record(seconds: int = 6, rate: int = REC_RATE) -> tuple[str, int]:
    """Record from the mic and write a clean 16 kHz WAV to a temp file.

    Returns ``(wav_path, raw_peak)``. The caller must delete the WAV.
    """
    if _winmm is None:
        raise RuntimeError("Microphone capture is Windows-only right now")

    seconds = max(1, min(15, int(seconds or 6)))
    dev_id, dev_name = _pick_device()
    wav = os.path.join(
        tempfile.gettempdir(),
        f"maya_mic_{os.getpid()}_{int(time.time() * 1000)}.wav",
    )

    fmt = WAVEFORMATEX(WAVE_FORMAT_PCM, 1, rate, rate * 2, 2, 16, 0)
    hwi = ctypes.c_void_p()
    rc = _winmm.waveInOpen(ctypes.byref(hwi), dev_id, ctypes.byref(fmt), 0, 0, CALLBACK_NULL)
    if rc != 0:
        raise RuntimeError(f"waveInOpen failed (code {rc}) device={dev_name}")

    buf = ctypes.create_string_buffer(rate * 2 * seconds)
    hdr = WAVEHDR(
        lpData=ctypes.cast(buf, ctypes.c_char_p),
        dwBufferLength=len(buf.raw),
        dwBytesRecorded=0,
        dwUser=None,
        dwFlags=0,
        dwLoops=0,
        lpNext=None,
        reserved=None,
    )
    try:
        if _winmm.waveInPrepareHeader(hwi, ctypes.byref(hdr), ctypes.sizeof(hdr)) != 0:
            raise RuntimeError("waveInPrepareHeader failed")
        if _winmm.waveInAddBuffer(hwi, ctypes.byref(hdr), ctypes.sizeof(hdr)) != 0:
            raise RuntimeError("waveInAddBuffer failed")
        if _winmm.waveInStart(hwi) != 0:
            raise RuntimeError("waveInStart failed")
        deadline = time.time() + seconds + 2
        while not (hdr.dwFlags & WHDR_DONE) and time.time() < deadline:
            time.sleep(0.05)
        _winmm.waveInStop(hwi)
        _winmm.waveInReset(hwi)
        data = buf.raw[: int(hdr.dwBytesRecorded)]
    finally:
        _winmm.waveInUnprepareHeader(hwi, ctypes.byref(hdr), ctypes.sizeof(hdr))
        _winmm.waveInClose(hwi)

    if not data:
        raise RuntimeError("Silence - 0 bytes recorded (mic muted?)")

    samples, raw_peak = _prepare_for_vosk(data, rate)
    if not samples:
        raise RuntimeError("Silence - 0 samples after processing")

    with wave.open(wav, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(OUT_RATE)
        wf.writeframes(samples.tobytes())
    return wav, raw_peak


# ── Transcription ──────────────────────────────────────────────────────────

def _load_model(path: Path):
    global _model, _loaded_path
    key = str(path)
    if _model is None or _loaded_path != key:
        from vosk import Model, SetLogLevel

        SetLogLevel(-1)
        _model = Model(key)
        _loaded_path = key
    return _model


def transcribe_wav(wav_path: str, lang: str = "en") -> str:
    """Transcribe an existing 16 kHz mono WAV with Vosk."""
    from vosk import KaldiRecognizer

    model = _load_model(model_path(lang))
    with wave.open(wav_path, "rb") as wf:
        rec = KaldiRecognizer(model, wf.getframerate())
        parts: list[str] = []
        while True:
            data = wf.readframes(8000)
            if not data:
                break
            if rec.AcceptWaveform(data):
                parts.append(json.loads(rec.Result()).get("text", ""))
        parts.append(json.loads(rec.FinalResult()).get("text", ""))
    return " ".join(p for p in parts if p).strip()


def transcribe_file(path: str, lang: str = "en") -> str:
    """Transcribe any WAV file (no resampling — caller should give 16 kHz)."""
    return transcribe_wav(path, lang)


def listen(seconds: int = 6, lang: str = "en") -> tuple[str | None, str | None]:
    """Record from the mic and transcribe.

    Returns ``(text, None)`` on success or ``(None, reason)`` — the reason is a
    real explanation, never a silent failure.
    """
    seconds = max(1, min(15, int(seconds or 6)))
    lang = (lang or "en").lower().strip() or "en"

    if _winmm is None:
        return None, "Microphone recording is Windows-only right now."

    path = model_path(lang)
    if not path.is_dir():
        return None, (
            f"No '{lang}' STT model. Expected folder: {path}\n"
            "Put a Vosk model there (vosk-en / vosk-en-in already ship with Maya)."
        )

    try:
        wav, raw_peak = record(seconds)
    except Exception as exc:
        return None, f"Could not open the microphone: {exc}"

    if raw_peak < SILENCE_PEAK:
        try:
            os.remove(wav)
        except OSError:
            pass
        return None, f"No mic signal (peak {raw_peak}) - check the mic is not muted."

    try:
        text = transcribe_wav(wav, lang)
    except ImportError:
        return None, "Vosk is not installed (pip install vosk)."
    except Exception as exc:  # noqa: BLE001 - report the real reason
        import traceback

        detail = f"{exc.__class__.__name__}: {exc}"
        try:
            tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
            # Keep it short but include the failing file/line.
            last_lines = "\n".join(tb.strip().splitlines()[-6:])
            detail = f"{detail}\n{last_lines}"
        except Exception:  # pragma: no cover - never crash reporting
            pass
        return None, f"Transcription failed: {detail}"
    finally:
        try:
            os.remove(wav)  # privacy: delete the audio immediately
        except OSError:
            pass

    if not text:
        return None, f"Could not understand the audio (peak {raw_peak}) - speak closer to the mic."
    return text, None


def status() -> dict[str, Any]:
    """Voice-input status for the CLI."""
    models = available()
    return {
        "vosk_installed": _vosk_installed(),
        "models": models,
        "any_model": any(models.values()),
        "windows_mic": _winmm is not None,
        "input_devices": [name for _, name in input_devices()],
        "model_root": str(DEFAULT_MODEL_ROOT),
    }


def _vosk_installed() -> bool:
    try:
        import vosk  # noqa: F401

        return True
    except ImportError:
        return False
