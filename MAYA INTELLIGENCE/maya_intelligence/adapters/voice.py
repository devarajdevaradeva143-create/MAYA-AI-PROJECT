"""Voice adapter — wraps custom.tools.voice and custom.tools.voice_stt (optional)."""

from typing import Any


class MayaIntelError(Exception):
    """Base exception for MAYA INTELLIGENCE adapters."""


class VoiceAdapter:
    """Thin wrapper over custom.tools.voice / voice_stt.
    
    Note: Tamil TTS/STT is pending (needs Whisper + Tamil .onnx).
    Voice replies are English-only for now.
    """

    def __init__(self):
        try:
            from custom.tools import voice
            self._voice = voice
            self._tts_available = True
        except ImportError:
            self._voice = None
            self._tts_available = False

        try:
            from custom.tools import voice_stt
            self._stt = voice_stt
            self._stt_available = True
        except ImportError:
            self._stt = None
            self._stt_available = False

    def speak(self, text: str, lang: str = "en") -> dict[str, Any]:
        """Speak text via TTS. Returns status dict."""
        if not self._tts_available:
            return {"success": False, "error": "TTS not available"}
        if lang != "en":
            return {"success": False, "error": f"Language '{lang}' not supported (English only for now)"}
        try:
            self._voice.speak(text)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def listen(self) -> dict[str, Any]:
        """Listen via STT. Returns status dict with text."""
        if not self._stt_available:
            return {"success": False, "error": "STT not available"}
        try:
            text = self._stt.listen()
            return {"success": True, "text": text}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def is_tts_available(self) -> bool:
        return self._tts_available

    def is_stt_available(self) -> bool:
        return self._stt_available