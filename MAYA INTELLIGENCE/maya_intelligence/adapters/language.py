"""Language adapter — wraps custom.tools.language."""

from typing import Any

from ..language import detect_language as _detect_chat_language


class MayaIntelError(Exception):
    """Base exception for MAYA INTELLIGENCE adapters."""


class LanguageAdapter:
    """Thin wrapper over custom.tools.language.

    ``custom.tools.language.detect_language`` returns a dict-like object; this
    adapter normalises it to a plain language name because the rest of Maya
    only needs ``tamil`` / ``tanglish`` / ``english``.
    """

    def __init__(self):
        from custom.tools import language

        self._language = language

    def detect(self, text: str) -> str:
        """Detect language of text.

        Uses Maya's chat-tuned detector first (it handles short Tanglish
        messages better), then falls back to the JARVIS tool.
        """
        try:
            return _detect_chat_language(text)
        except Exception:
            pass
        try:
            result = self._language.detect_language(text)
            if isinstance(result, dict):
                name = result.get("name") or result.get("language_name")
                if name:
                    return str(name).lower()
                primary = result.get("primary")
                mapping = {"ta": "tamil", "ta-latn": "tanglish", "en": "english"}
                return mapping.get(str(primary).lower(), "english")
            return str(result).lower()
        except Exception:
            return "english"

    def translate(self, text: str, target: str) -> str:
        """Translate text to target language."""
        return self._language.translate(text, target)

    def is_tamil(self, text: str) -> bool:
        """Check if text is primarily Tamil."""
        return self.detect(text) == "tamil"

    def is_tanglish(self, text: str) -> bool:
        """Check if text is Tanglish (mixed Tamil-English)."""
        return self.detect(text) == "tanglish"

    def to_tamil(self, text: str) -> str:
        """Translate to Tamil."""
        return self._language.to_tamil(text)

    def to_english(self, text: str) -> str:
        """Translate to English."""
        return self._language.to_english(text)

    def get_response_language(self, user_text: str) -> str:
        """Determine response language based on user input."""
        return self.detect(user_text)
