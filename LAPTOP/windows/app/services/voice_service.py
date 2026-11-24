"""Voice adapter: existing Vosk/Whisper STT and SAPI/Piper TTS.

The phone contract needs a WAV file (not direct speaker playback), so this
module adds `synthesize_wav`. Everything stays local.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import threading
import time
import wave
from pathlib import Path
from typing import Any

from custom.config import load_settings
from custom.tools import voice as voice_tools
from custom.tools import voice_stt

SAPI_TIMEOUT_S = 90
TTS_TEXT_MAX = 1000
SPEAK_TEXT_MAX = 1000


class VoiceError(RuntimeError):
    """Honest voice failure with a message the UI can show as-is."""


def _temp_dir() -> Path:
    folder = Path(tempfile.gettempdir()) / "maya"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _ps_quote(value: str) -> str:
    return value.replace("'", "''")


def _voice_lang_key(lang: str) -> str:
    value = (lang or "en").lower().strip()
    if value in {"ta", "tamil"}:
        return "ta"
    if value in {"en-in", "en_in", "indian"}:
        return "en-in"
    return "en"


def _default_lang(preference: str) -> str:
    value = (preference or "").lower().strip()
    if value == "tamil":
        return "ta"
    if value == "english":
        return "en"
    return "en-in"


class VoiceAdapter:
    """VoicePort implementation for the desktop app and phone server."""

    def __init__(self) -> None:
        settings = load_settings()
        voice = settings.get("voice")
        if not isinstance(voice, dict):
            voice = {}
        tts = voice.get("tts")
        if not isinstance(tts, dict):
            tts = {}
        self._preferred_voices = [
            str(name) for name in (tts.get("preferred_voices") or []) if str(name).strip()
        ]
        self._configured_engine = str(tts.get("engine", "auto"))

        stt = voice.get("stt")
        if not isinstance(stt, dict):
            stt = {}
        self._listen_seconds = max(1, min(15, int(stt.get("listen_seconds", 6))))
        self._default_lang = _default_lang(str(settings.get("language", "tanglish")))

        self._speak_lock = threading.Lock()
        self._speak_busy = threading.Lock()
        self._stop_event: threading.Event | None = None

    @property
    def listen_seconds(self) -> int:
        """Recording length for push-to-talk (config: voice.stt.listen_seconds)."""
        return self._listen_seconds

    @property
    def default_lang(self) -> str:
        """STT language key from the top-level `language` setting."""
        return self._default_lang

    # -- status -------------------------------------------------------

    def status(self) -> dict[str, Any]:
        info = voice_tools.voice_status()
        models = info.get("stt_models") or {}
        languages = [lang for lang, present in models.items() if present]

        piper_model = self._piper_model("en")
        piper_available = piper_model is not None or voice_tools.tts_english.is_available()
        sapi_available = info.get("sapi_available", sys.platform == "win32")

        configured = str(self._stt_engine()).lower()
        if configured == "whisper":
            engine_label = "whisper"
        elif configured == "vosk":
            engine_label = "vosk"
        else:
            engine_label = "auto"

        return {
            "stt": {
                "engine": engine_label,
                "configured_engine": configured,
                "available": bool(languages or info.get("whisper_available")),
                "languages": languages,
                "default_lang": self._default_lang,
                "listen_seconds": self._listen_seconds,
                "whisper_available": bool(info.get("whisper_available")),
                "whisper_model": info.get("whisper_model"),
                "tamil_stt_available": bool(info.get("tamil_stt_available", info.get("whisper_available"))),
            },
            "tts": {
                "engine": "piper" if (piper_available or voice_tools.tts_tamil.is_available()) else ("sapi" if sapi_available else "none"),
                "available": piper_available or sapi_available or voice_tools.tts_tamil.is_available(),
                "voices": self._preferred_voices,
                "tamil_available": voice_tools.tts_tamil.is_available(),
                "piper": {
                    "available": piper_available or voice_tools.tts_tamil.is_available(),
                    "voices": [voice_tools.tts_tamil.model_path.stem] if voice_tools.tts_tamil.model_path else ([piper_model.stem] if piper_model else []),
                },
            },
        }

    def _stt_engine(self) -> str:
        settings = load_settings()
        voice = settings.get("voice", {}) if isinstance(settings, dict) else {}
        stt = voice.get("stt", {}) if isinstance(voice, dict) else {}
        return str(stt.get("engine", "auto") or "auto")

    # -- STT ----------------------------------------------------------

    def listen_once(self, seconds: int | None = None, lang: str | None = None) -> str:
        """Record from the mic and return the transcript.

        Raises `VoiceError` with the real reason (no mic, missing model,
        silence) so the UI never fails silently.
        """
        key = _voice_lang_key(lang or self._default_lang)
        length = self._listen_seconds if seconds is None else int(seconds)

        # Tamil uses Whisper (Vosk has no Tamil model).
        if key == "ta":
            if not voice_tools.HAS_WHISPER:
                raise VoiceError(
                    "Tamil STT needs faster-whisper. Install it into the app venv."
                )
            configured = self._stt_engine()
            if configured == "vosk":
                raise VoiceError(
                    "Tamil needs Whisper; set voice.stt.engine to auto or whisper."
                )
            try:
                wav, _peak = voice_stt.record(seconds=length)
            except Exception as exc:
                raise VoiceError(f"Could not record audio: {exc}") from exc
            try:
                text = voice_tools.stt.transcribe(wav, language="ta")
            finally:
                try:
                    Path(wav).unlink(missing_ok=True)
                except OSError:
                    pass
            if text.startswith("[STT]"):
                raise VoiceError(text)
            result = text.strip()
            if not result:
                raise VoiceError("Could not understand the audio — speak closer to the mic.")
            return result

        configured = self._stt_engine()
        if configured == "whisper" and voice_tools.HAS_WHISPER:
            try:
                wav, _peak = voice_stt.record(seconds=length)
            except Exception as exc:
                raise VoiceError(f"Could not record audio: {exc}") from exc
            try:
                text = voice_tools.stt.transcribe(wav, language="en")
            finally:
                try:
                    Path(wav).unlink(missing_ok=True)
                except OSError:
                    pass
            if text.startswith("[STT]"):
                raise VoiceError(text)
            result = text.strip()
            if not result:
                raise VoiceError("Could not understand the audio — speak closer to the mic.")
            return result

        if not voice_stt.available().get(key):
            raise VoiceError(
                f"No '{key}' speech model installed. "
                "Add a Vosk model under MAYA AI/Model/models or use English."
            )
        text, error = voice_stt.listen(seconds=length, lang=key)
        if error:
            raise VoiceError(error)
        result = (text or "").strip()
        if not result:
            raise VoiceError("Could not understand the audio — speak closer to the mic.")
        return result

    def transcribe_file(self, path: str | Path, lang: str | None = None) -> str:
        """Transcribe an existing WAV file (used by tests and future tools)."""
        try:
            result = self.transcribe(Path(path), lang or self._default_lang)
        except RuntimeError as exc:
            raise VoiceError(str(exc)) from exc
        text = str(result.get("text", "")).strip()
        if not text:
            raise VoiceError("No speech recognised in that file.")
        return text

    # -- TTS ----------------------------------------------------------

    def transcribe(self, wav_path: Path, lang: str) -> dict[str, Any]:
        key = _voice_lang_key(lang)

        configured = self._stt_engine()
        use_whisper = (key == "ta") or (configured in {"whisper", "auto"} and voice_tools.HAS_WHISPER)

        if use_whisper and voice_tools.HAS_WHISPER:
            text = voice_tools.stt.transcribe(str(wav_path), language=key if key == "ta" else "en")
            if text.startswith("[STT]"):
                raise RuntimeError(text)
            return {"text": text.strip(), "lang": lang, "engine": "whisper"}

        if not voice_stt.available().get(key):
            raise RuntimeError(f"No '{key}' speech model installed")

        text = voice_stt.transcribe_file(str(wav_path), key)
        return {"text": text.strip(), "lang": lang, "engine": "vosk"}

    # -- TTS ----------------------------------------------------------

    def synthesize_wav(
        self,
        text: str,
        *,
        engine: str = "auto",
        voice: str | None = None,
        lang: str = "en",
        speed: float = 1.0,
    ) -> Path:
        text = text.strip()
        if not text:
            raise RuntimeError("Empty text")
        if len(text) > TTS_TEXT_MAX:
            raise RuntimeError("Text too long")

        choice = (engine or "auto").lower()
        if choice not in {"auto", "sapi", "piper"}:
            raise RuntimeError(f"Unknown TTS engine: {engine}")

        target = _temp_dir() / f"tts-{int(time.time() * 1000)}-{id(text) & 0xFFFF}.wav"

        if choice in {"auto", "piper"}:
            if self._piper_wav(text, lang, target):
                return target
            if choice == "piper":
                raise RuntimeError("Piper TTS is not installed")

        if not self._sapi_wav(text, voice, speed, target):
            raise RuntimeError("Windows SAPI is not available")
        return target

    # -- local playback ----------------------------------------------

    def speak(self, text: str, lang: str = "english", *, engine: str = "auto") -> str:
        """Render text to WAV and play it through the laptop speakers.

        Blocking; call it from a worker thread. `stop_speaking()` interrupts it.
        Raises `VoiceError` when TTS is unavailable.
        """
        text = (text or "").strip()
        if not text:
            raise VoiceError("Nothing to say")
        if len(text) > SPEAK_TEXT_MAX:
            text = text[:SPEAK_TEXT_MAX].rstrip()

        if not self._speak_busy.acquire(blocking=False):
            raise VoiceError("Maya is already speaking")
        stop = threading.Event()
        with self._speak_lock:
            self._stop_event = stop
        try:
            try:
                wav = self.synthesize_wav(text, engine=engine, lang=lang)
            except RuntimeError as exc:
                raise VoiceError(str(exc)) from exc

            try:
                if stop.is_set():
                    return "[TTS] Stopped"
                self._play_wav(wav, stop)
                return f"[TTS] Spoke: {text[:60]}"
            finally:
                try:
                    wav.unlink(missing_ok=True)
                except OSError:
                    pass
        finally:
            with self._speak_lock:
                if self._stop_event is stop:
                    self._stop_event = None
            self._speak_busy.release()

    def stop_speaking(self) -> bool:
        """Stop the current playback. Returns True when something was playing."""
        with self._speak_lock:
            event = self._stop_event
        if event is None:
            return False
        event.set()
        _purge_audio()
        return True

    @property
    def is_speaking(self) -> bool:
        with self._speak_lock:
            return self._stop_event is not None

    def _play_wav(self, path: Path, stop: threading.Event) -> None:
        if sys.platform != "win32":
            self._play_wav_unix(path, stop)
            return

        import winsound

        winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)
        deadline = time.monotonic() + _wav_duration(path) + 0.5
        try:
            while time.monotonic() < deadline:
                if stop.wait(0.05):
                    break
        finally:
            _purge_audio()

    @staticmethod
    def _play_wav_unix(path: Path, stop: threading.Event) -> None:
        player = shutil.which("aplay") or shutil.which("paplay")
        if not player:
            raise VoiceError("No audio player found (install aplay or paplay)")
        process = subprocess.Popen(
            [player, str(path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            while process.poll() is None:
                if stop.wait(0.05):
                    process.terminate()
                    break
            process.wait(timeout=5)
        finally:
            if process.poll() is None:
                process.kill()

    def _sapi_wav(
        self,
        text: str,
        voice: str | None,
        speed: float,
        target: Path,
    ) -> bool:
        if sys.platform != "win32":
            return False

        rate = max(-10, min(10, round((float(speed) - 1.0) * 10)))
        script = [
            "Add-Type -AssemblyName System.Speech;",
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;",
            f"$s.Rate = {rate};",
        ]
        if voice:
            script.append(f"try {{ $s.SelectVoice('{_ps_quote(voice)}') }} catch {{}}")
        script.extend(
            [
                f"$s.SetOutputToWaveFile('{_ps_quote(str(target))}');",
                f"$s.Speak('{_ps_quote(text)}');",
                "$s.Dispose();",
            ]
        )
        try:
            completed = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", " ".join(script)],
                capture_output=True,
                text=True,
                timeout=SAPI_TIMEOUT_S,
            )
        except (OSError, subprocess.SubprocessError):
            return False

        if completed.returncode != 0 or not target.is_file():
            return False
        return self._valid_wav(target)

    def _piper_wav(self, text: str, lang: str, target: Path) -> bool:
        # Use the piper Python API (the 1.8 CLI is broken for file output).
        key = _voice_lang_key(lang)
        tts = voice_tools.tts_tamil if key == "ta" else voice_tools.tts_english
        if not tts.is_available():
            return False
        err = tts.synthesize_wav(text, target)
        if err:
            return False
        return self._valid_wav(target)

    @staticmethod
    def _piper_command() -> list[str] | None:
        executable = shutil.which("piper")
        if executable:
            return [executable]
        try:
            import piper  # noqa: F401
        except ImportError:
            return None
        return [sys.executable, "-m", "piper"]

    @staticmethod
    def _piper_model(lang: str) -> Path | None:
        folder = (
            voice_tools.TAMIL_VOICE_DIR
            if _voice_lang_key(lang) == "ta"
            else voice_tools.ENGLISH_VOICE_DIR
        )
        if not folder.is_dir():
            return None
        models = sorted(folder.glob("*.onnx"))
        return models[0] if models else None

    @staticmethod
    def _valid_wav(path: Path) -> bool:
        try:
            with wave.open(str(path), "rb") as wav:
                return wav.getnframes() > 0
        except (OSError, EOFError, wave.Error):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
            return False


def _purge_audio() -> None:
    """Stop async playback for this process (Windows only; best effort)."""
    if sys.platform != "win32":
        return
    try:
        import winsound

        winsound.PlaySound(None, 0)
    except (ImportError, RuntimeError):
        pass


def _wav_duration(path: Path) -> float:
    try:
        with wave.open(str(path), "rb") as wav:
            rate = wav.getframerate() or 1
            return wav.getnframes() / float(rate)
    except (OSError, EOFError, wave.Error):
        return 0.0
