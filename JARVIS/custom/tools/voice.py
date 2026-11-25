"""Maya AI voice tools — TTS, STT, and wake word.

All voice processing is LOCAL only — nothing goes to the cloud.

Per AGENTS.md: Voice TTS/STT for Tamil + English. Piper TTS +
faster-whisper STT when installed; graceful fallback otherwise.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import wave
from pathlib import Path
from typing import Any, Optional

try:
    import piper
    HAS_PIPER = True
except ImportError:  # pragma: no cover - optional
    piper = None  # type: ignore[assignment]
    HAS_PIPER = False

try:
    from faster_whisper import WhisperModel
    HAS_WHISPER = True
except ImportError:  # pragma: no cover - optional
    WhisperModel = None  # type: ignore[assignment,misc]
    HAS_WHISPER = False

from .kuyil_tts import KuyilTTS


# ── Voice directories ──────────────────────────────────────────────────────

from ..config import PROJECT_ROOT, load_settings

VOICE_DIR = PROJECT_ROOT / "MAYA AI" / "voice"
TAMIL_VOICE_DIR = VOICE_DIR / "tamil"
ENGLISH_VOICE_DIR = VOICE_DIR / "english"


def _settings() -> dict[str, Any]:
    try:
        data = load_settings()
    except Exception:  # pragma: no cover - config must never crash voice
        return {}
    return data if isinstance(data, dict) else {}


def _whisper_cfg() -> dict[str, Any]:
    voice = _settings().get("voice", {})
    stt = voice.get("stt", {}) if isinstance(voice, dict) else {}
    whisper = stt.get("whisper", {}) if isinstance(stt, dict) else {}
    return whisper if isinstance(whisper, dict) else {}


def _stt_engine_cfg() -> str:
    voice = _settings().get("voice", {})
    stt = voice.get("stt", {}) if isinstance(voice, dict) else {}
    return str(stt.get("engine", "auto") or "auto").lower().strip()


# ── TTS (Piper) ────────────────────────────────────────────────────────────

def _speak_windows_sapi(text: str) -> str:
    """Speak text with the built-in Windows SAPI voice (offline, no download)."""
    if sys.platform != "win32":
        return "[TTS] No TTS backend. Install piper-tts + a voice model."
    escaped = text.replace("'", "''")
    script = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        f"$s.Speak('{escaped}')"
    )
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return f"[TTS] SAPI error: {exc}"
    if proc.returncode != 0:
        return f"[TTS] SAPI failed: {(proc.stderr or '').strip()[:200]}"
    return f"[TTS] Spoke (Windows SAPI): {text[:60]}"


def _play_wav(path: str) -> None:
    """Play a WAV file on the local speaker (best effort)."""
    if sys.platform == "win32":
        try:
            import winsound

            winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_NODEFAULT)
            return
        except Exception:  # pragma: no cover - platform specific
            pass
    for binary in ("aplay", "paplay", "afplay"):
        try:
            subprocess.run([binary, path], capture_output=True, timeout=120, check=False)
            return
        except (OSError, subprocess.SubprocessError):
            continue


class PiperTTS:
    """Piper TTS wrapper using the Python API (piper-tts >= 1.2).

    The 1.8 CLI has a file-output bug on this machine, so Maya uses
    ``PiperVoice.load(...).synthesize_wav(...)`` instead.
    """

    def __init__(self, lang: str = "english", model_path: Optional[Path] = None) -> None:
        self.lang = (lang or "english").lower().strip()
        if self.lang in {"ta"}:
            self.lang = "tamil"
        self._model = None
        self._model_path: Optional[Path] = model_path
        self._voice = None
        if HAS_PIPER:
            self._load_model()

    def _candidate_model(self) -> Optional[Path]:
        if self._model_path is not None and self._model_path.is_file():
            return self._model_path
        voice_dir = TAMIL_VOICE_DIR if self.lang == "tamil" else ENGLISH_VOICE_DIR
        if not voice_dir.is_dir():
            return None
        onnx_files = sorted(voice_dir.glob("*.onnx"))
        return onnx_files[0] if onnx_files else None

    def _load_model(self) -> None:
        model_path = self._candidate_model()
        if model_path is None:
            return
        try:
            config_path = model_path.with_suffix(model_path.suffix + ".json")
            if not config_path.is_file():
                config_path = None
            voice = piper.PiperVoice.load(
                str(model_path),
                config_path=str(config_path) if config_path else None,
            )
            self._model = model_path
            self._voice = voice
        except Exception:  # pragma: no cover - defensive
            self._model = None
            self._voice = None

    def is_available(self) -> bool:
        return HAS_PIPER and self._voice is not None and self._model is not None

    @property
    def model_path(self) -> Optional[Path]:
        return self._model

    def synthesize_wav(self, text: str, target_path: str | Path) -> str:
        """Synthesize ``text`` into a WAV file at ``target_path``.

        Returns an empty string on success, or an honest error message.
        """
        if not self.is_available():
            if self.lang == "tamil":
                return (
                    "[TTS] Tamil voice needs piper-tts + a .onnx model in "
                    f"{TAMIL_VOICE_DIR}"
                )
            return "[TTS] Piper voice not available."
        target = Path(target_path)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            with wave.open(str(target), "wb") as wav_file:
                self._voice.synthesize_wav(text, wav_file)
            if not target.is_file() or target.stat().st_size < 44:
                return "[TTS] Piper produced an empty WAV."
            return ""
        except Exception as exc:  # pragma: no cover - defensive
            return f"[TTS] Piper error: {exc}"

    def speak(self, text: str) -> str:
        """Speak text. Tamil never falls back to an English/SAPI voice."""
        if not text or not text.strip():
            return "[TTS] Nothing to say."
        if self.lang == "tamil":
            if not self.is_available():
                return (
                    "[TTS] Tamil voice needs piper-tts + a .onnx model in "
                    f"{TAMIL_VOICE_DIR}"
                )
            fd, tmp_name = tempfile.mkstemp(prefix="maya_tts_", suffix=".wav")
            os.close(fd)
            try:
                err = self.synthesize_wav(text, tmp_name)
                if err:
                    return err
                _play_wav(tmp_name)
                return f"[TTS] Spoke: {text[:60]}"
            finally:
                try:
                    os.remove(tmp_name)
                except OSError:
                    pass
        # English path
        if not self.is_available():
            return _speak_windows_sapi(text)
        fd, tmp_name = tempfile.mkstemp(prefix="maya_tts_", suffix=".wav")
        os.close(fd)
        try:
            err = self.synthesize_wav(text, tmp_name)
            if err:
                return _speak_windows_sapi(text)
            _play_wav(tmp_name)
            return f"[TTS] Spoke: {text[:60]}"
        finally:
            try:
                os.remove(tmp_name)
            except OSError:
                pass


# Module-level TTS instances (english default, tamil available).
tts_english = PiperTTS("english")
tts_tamil = PiperTTS("tamil")
tts_kuyil = KuyilTTS("tamil")

TTS_ENGINES = ("auto", "kuyil", "piper", "sapi")


def _tts_engine_cfg() -> str:
    voice = _settings().get("voice", {})
    tts = voice.get("tts", {}) if isinstance(voice, dict) else {}
    value = str(tts.get("engine", "auto") or "auto").lower().strip()
    return value if value in TTS_ENGINES else "auto"


def tts_for(lang: str = "english", engine: Optional[str] = None) -> Optional[PiperTTS | KuyilTTS]:
    """Pick the TTS backend. ``None`` means the Windows SAPI fallback.

    - ``kuyil``: tiny offline voice, reads Tamil + English words (best for Tanglish)
    - ``piper``: natural Tamil/English, but Tamil voices mis-read English words
    - ``sapi``:  Windows built-in voices only
    - ``auto``:  Tamil -> Kuyil when installed, else Piper; English -> Piper, else SAPI
    """
    choice = (engine or _tts_engine_cfg() or "auto").lower().strip()
    if choice not in TTS_ENGINES:
        choice = "auto"
    tamil = str(lang).lower().startswith("t")

    if choice == "kuyil":
        return tts_kuyil
    if choice == "piper":
        return tts_tamil if tamil else tts_english
    if choice == "sapi":
        return None
    if tamil:
        return tts_kuyil if tts_kuyil.is_available() else tts_tamil
    return tts_english if tts_english.is_available() else None


def speak(text: str, lang: str = "english", engine: Optional[str] = None) -> str:
    """Speak text using the appropriate TTS engine."""
    tts = tts_for(lang, engine)
    if tts is None:
        return _speak_windows_sapi(text)
    if not tts.is_available():
        name = "Kuyil" if isinstance(tts, KuyilTTS) else "Piper"
        return f"[TTS] {name} is not available. Install the model or pick another engine."
    return tts.speak(text)



# ── STT (faster-whisper) ──────────────────────────────────────────────────

def _whisper_language(lang: Optional[str]) -> Optional[str]:
    value = (lang or "").lower().strip()
    if value in {"ta", "tamil"}:
        return "ta"
    if value in {"en", "english", "en-in", "en_in"}:
        return "en"
    if value in {"", "auto", "none"}:
        return None
    return value or None


class WhisperSTT:
    """faster-whisper wrapper for local speech-to-text.

    The model is loaded lazily on the first ``transcribe`` call so importing
    this module stays cheap and fast.
    """

    def __init__(
        self,
        model_size: Optional[str] = None,
        download_root: Optional[str] = None,
        compute_type: Optional[str] = None,
        lazy: bool = True,
    ) -> None:
        cfg = _whisper_cfg()
        self.model_size = model_size or str(cfg.get("model", "small") or "small")
        root = download_root or cfg.get("download_root", "MAYA AI/Model/whisper")
        self.download_root = (PROJECT_ROOT / str(root)).resolve() if not Path(str(root)).is_absolute() else Path(str(root))
        self.compute_type = compute_type or str(cfg.get("compute_type", "int8") or "int8")
        self._model = None
        self._loaded = False
        if not lazy:
            self._ensure_loaded()

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not HAS_WHISPER:
            return
        try:
            self._model = WhisperModel(
                self.model_size,
                device="cpu",
                compute_type=self.compute_type,
                download_root=str(self.download_root),
            )
        except Exception:  # pragma: no cover - defensive
            self._model = None

    def is_available(self) -> bool:
        """Package importable (model may download on first use)."""
        return HAS_WHISPER

    def model_ready(self) -> bool:
        """Best-effort check for a locally cached model dir."""
        if not HAS_WHISPER:
            return False
        root = self.download_root
        if not root.is_dir():
            return False
        # faster-whisper caches under models--Systran--faster-whisper-<size>
        needle = f"faster-whisper-{self.model_size}"
        for child in root.rglob("model.bin"):
            if needle in str(child):
                return True
        return any(root.rglob("model.bin"))

    def transcribe(self, audio_path: str, language: Optional[str] = None) -> str:
        """Transcribe an audio file. Returns text or an honest ``[STT]`` message."""
        if not HAS_WHISPER:
            return "[STT] faster-whisper not installed. Run: uv pip install faster-whisper"
        self._ensure_loaded()
        if self._model is None:
            return f"[STT] Whisper model '{self.model_size}' could not be loaded."
        try:
            lang = _whisper_language(language)
            kwargs = {"language": lang} if lang else {}
            segments, _info = self._model.transcribe(str(audio_path), **kwargs)
            text = "".join(seg.text for seg in segments)
            text = text.strip()
            if not text:
                return "[STT] No speech recognised."
            return text
        except Exception as exc:  # pragma: no cover - defensive
            return f"[STT] Error: {exc}"


# Module-level STT instance (lazy).
stt = WhisperSTT()


def listen(audio_path: str, lang: str = "en") -> str:
    """Transcribe an audio file.

    Tamil always uses Whisper (Vosk has no Tamil model). English uses Whisper
    when it is installed and the caller asks for it via ``lang``; otherwise the
    offline Vosk models that ship with the project.
    """
    lang_norm = (lang or "en").lower().strip()
    if lang_norm in {"ta", "tamil"}:
        return stt.transcribe(audio_path, language="ta")

    # English path: prefer Whisper only if explicitly available and selected.
    if HAS_WHISPER:
        result = stt.transcribe(audio_path, language="en")
        if not result.startswith("[STT]"):
            return result

    from . import voice_stt

    if not voice_stt.available().get(lang_norm, False) and not voice_stt.available().get("en", False):
        return (
            f"[STT] No '{lang_norm}' model. Add a Vosk model or install faster-whisper."
        )
    try:
        text = voice_stt.transcribe_file(audio_path, lang_norm if lang_norm in {"en", "en-in"} else "en")
    except Exception as exc:
        return f"[STT] Error: {exc}"
    return text or "[STT] No speech recognised."


def listen_mic(seconds: int = 6, lang: str = "en") -> str:
    """Record from the microphone and transcribe it (offline)."""
    lang_norm = (lang or "en").lower().strip()
    if lang_norm in {"ta", "tamil"}:
        if not HAS_WHISPER:
            return "[STT] faster-whisper not installed; Tamil STT unavailable."
        from . import voice_stt

        if _stt_engine_cfg() == "vosk":
            return "[STT] Tamil needs Whisper; switch voice.stt.engine to auto/whisper."
        try:
            wav, _peak = voice_stt.record(seconds=seconds)
        except Exception as exc:
            return f"[STT] Could not record: {exc}"
        try:
            return stt.transcribe(wav, language="ta")
        finally:
            try:
                os.remove(wav)
            except OSError:
                pass

    # English
    from . import voice_stt

    text, error = voice_stt.listen(seconds=seconds, lang=lang_norm)
    if error:
        return f"[STT] {error}"
    return text or ""


# ── Wake word ───────────────────────────────────────────────────────────────

WAKE_PHRASES = ["maya maya maya", "maya, maya, maya"]


def check_wake(text: str) -> bool:
    if not text:
        return False
    text_lower = text.lower().strip()
    for phrase in WAKE_PHRASES:
        if phrase in text_lower:
            return True
    return False


def wake_reply() -> str:
    settings = _settings()
    wake = settings.get("wake", {}) if isinstance(settings, dict) else {}
    return str(wake.get("reply", "Sollu da, enna venum?"))


# ── Status ─────────────────────────────────────────────────────────────────

def voice_status() -> dict[str, Any]:
    from . import voice_stt

    sapi = sys.platform == "win32"
    stt_info = voice_stt.status()
    cfg_engine = _stt_engine_cfg()
    return {
        "piper_available": HAS_PIPER,
        "sapi_available": sapi,
        "tts_english_ready": tts_english.is_available() or sapi,
        "tts_tamil_ready": tts_tamil.is_available(),
        "kuyil_available": tts_kuyil.is_available(),
        "kuyil_voices": tts_kuyil.voices,
        "kuyil_model": str(tts_kuyil.model_path) if tts_kuyil.model_path else None,
        "tts_engine": _tts_engine_cfg(),
        "tts_engines": [name for name in TTS_ENGINES if name != "sapi" or sapi],
        "whisper_available": HAS_WHISPER,
        "whisper_model": stt.model_size if HAS_WHISPER else None,
        "whisper_model_ready": stt.model_ready() if HAS_WHISPER else False,
        "vosk_installed": stt_info["vosk_installed"],
        "stt_models": stt_info["models"],
        "stt_engine": cfg_engine,
        "tamil_stt_available": HAS_WHISPER,
        "stt_ready": HAS_WHISPER or stt_info["any_model"],
        "input_devices": stt_info["input_devices"],
        "voice_dir": str(VOICE_DIR),
        "tamil_dir": str(TAMIL_VOICE_DIR),
        "english_dir": str(ENGLISH_VOICE_DIR),
    }
