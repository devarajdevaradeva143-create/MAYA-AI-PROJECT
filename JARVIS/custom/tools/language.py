"""Maya AI Language Intelligence tools.

Provides translation, language detection, and pronunciation guidance.

Translation uses the LOCAL engine only (``custom.engine.bridge``) — no cloud
APIs and no network calls beyond the configured localhost engine. Per
AGENTS.md: Language Intelligence module for Tamil/English/Hindi/Tanglish support.
"""

from __future__ import annotations

import re
import threading
from typing import Any, Dict, Protocol

from custom.config import load_settings


# ── Language normalization ───────────────────────────────────────────────

TAMIL = "tamil"
ENGLISH = "english"
HINDI = "hindi"
TANGLISH = "tanglish"

#: Prefix used by honest "translation unavailable" fallbacks.
UNAVAILABLE_PREFIX = "[translation unavailable]"

# Reply-cleaning regexes (used by _clean_translation).
_FENCE_OPEN_RE = re.compile(r"^```[^\n]*\n")
_FENCE_CLOSE_RE = re.compile(r"\n?```\s*$")
_LABEL_RE = re.compile(
    r"^\s*(?:\*\*)?translation(?:\s*\([^)]*\))?\s*[:\-\u2013\u2014]\s*(?:\*\*)?\s*",
    re.IGNORECASE,
)
_MULTI_BLANK_RE = re.compile(r"\n{3,}")

#: ISO 639-1 codes for supported languages
ISO_LANG_CODES: Dict[str, str] = {
    TAMIL: "ta",
    ENGLISH: "en",
    HINDI: "hi",
    TANGLISH: "ta-Latn",  # Tamil in Latin script
}

#: Accepted aliases for language arguments (ISO codes + full names).
_LANG_ALIASES: Dict[str, str] = {
    "ta": TAMIL,
    "tam": TAMIL,
    "tamil": TAMIL,
    "ta-latn": TANGLISH,
    "ta_latn": TANGLISH,
    "tanglish": TANGLISH,
    "romanized": TANGLISH,
    "en": ENGLISH,
    "eng": ENGLISH,
    "english": ENGLISH,
    "hi": HINDI,
    "hin": HINDI,
    "hindi": HINDI,
    "hi-latn": HINDI,
    "hinglish": HINDI,
}

#: Display names used inside translation prompts.
_LANG_DISPLAY: Dict[str, str] = {
    TAMIL: "Tamil",
    ENGLISH: "English",
    HINDI: "Hindi",
    TANGLISH: "Tanglish (Tamil written in Latin script)",
}

#: LRU cache for translations (max 100 entries)
_translation_cache: Dict[str, str] = {}
_MAX_CACHE_SIZE = 100


def _cache_key(text: str, source: str, target: str) -> str:
    """Create a cache key from text, source, and target language codes."""
    return f"{source}\x00{target}\x00{text}"


def clear_translation_cache() -> None:
    """Clear the LRU translation cache."""
    _translation_cache.clear()



# ── Language detection ─────────────────────────────────────────────────────


def detect_language(text: str) -> Dict[str, Any]:
    """Detect the language of ``text``.

    Returns a dict with ``primary`` set to an ISO 639-1 code (``"ta"``,
    ``"en"``, ``"hi"`` …). Also exposed under ``code``/``language``/``iso``
    keys for compatibility. The ``primary`` value compares equal to both the
    ISO code and the full language name.
    """
    if not text or not text.strip():
        code = _LangCode("unknown", {"unknown"})
        return _Detected(
            {
                "primary": code,
                "code": code,
                "language": code,
                "iso": code,
                "iso_code": code,
                "lang": code,
                "name": "unknown",
                "language_name": "unknown",
                "confidence": "0%",
            }
        )

    # Measure Tamil script against letters only, so punctuation/spaces do not
    # water down the ratio for short Tamil sentences.
    letters = [ch for ch in text if ch.isalpha()]
    tamil_chars = sum(1 for ch in letters if "\u0B80" <= ch <= "\u0BFF")
    tamil_ratio = tamil_chars / max(len(letters), 1)

    devanagari_chars = sum(1 for ch in letters if "\u0900" <= ch <= "\u097F")
    devanagari_ratio = devanagari_chars / max(len(letters), 1)

    latin_tokens = re.findall(r"[a-zA-Z]+", text.lower())
    hint_tokens = sum(1 for token in latin_tokens if token in _TANGLISH_HINTS)
    tanglish_ratio = hint_tokens / len(latin_tokens) if latin_tokens else 0.0

    hinglish_tokens = sum(1 for token in latin_tokens if token in _HINGLISH_HINTS)
    hinglish_ratio = hinglish_tokens / len(latin_tokens) if latin_tokens else 0.0

    english_words = len(re.findall(r"\b[a-zA-Z]+\b", text))
    total_words = len(text.split())
    english_ratio = english_words / max(total_words, 1) if total_words else 0.0

    if tamil_ratio >= 0.3:
        code = _LangCode("ta", {"ta", "tamil"})
        return _Detected(
            {
                "primary": code,
                "code": code,
                "language": code,
                "iso": code,
                "iso_code": code,
                "lang": code,
                "name": TAMIL,
                "language_name": TAMIL,
                "confidence": f"{round(tamil_ratio * 100)}%",
            }
        )
    if devanagari_ratio >= 0.3:
        code = _LangCode("hi", {"hi", "hindi"})
        return _Detected(
            {
                "primary": code,
                "code": code,
                "language": code,
                "iso": code,
                "iso_code": code,
                "lang": code,
                "name": HINDI,
                "language_name": HINDI,
                "confidence": f"{round(devanagari_ratio * 100)}%",
            }
        )
    if tanglish_ratio >= 0.5:
        code = _LangCode("ta-Latn", {"ta-Latn", "tanglish", "romanized"})
        return _Detected(
            {
                "primary": code,
                "code": code,
                "language": code,
                "iso": code,
                "iso_code": code,
                "lang": code,
                "name": TANGLISH,
                "language_name": TANGLISH,
                "confidence": "mix of Tamil + English",
            }
        )
    if hinglish_ratio >= 0.5:
        code = _LangCode("hi-Latn", {"hi-Latn", "hinglish"})
        return _Detected(
            {
                "primary": code,
                "code": code,
                "language": code,
                "iso": code,
                "iso_code": code,
                "lang": code,
                "name": HINDI,
                "language_name": HINDI,
                "confidence": "mix of Hindi + English",
            }
        )
    if english_ratio > 0.5:
        code = _LangCode("en", {"en", "english"})
        return _Detected(
            {
                "primary": code,
                "code": code,
                "language": code,
                "iso": code,
                "iso_code": code,
                "lang": code,
                "name": ENGLISH,
                "language_name": ENGLISH,
                "confidence": f"{round(english_ratio * 100)}%",
            }
        )
    if not letters:
        code = _LangCode("unknown", {"unknown"})
        return _Detected(
            {
                "primary": code,
                "code": code,
                "language": code,
                "iso": code,
                "iso_code": code,
                "lang": code,
                "name": "unknown",
                "language_name": "unknown",
                "confidence": "0%",
            }
        )
    # Fallback: treat as Tanglish-ish
    code = _LangCode("ta-Latn", {"ta-Latn", "tanglish", "romanized"})
    return _Detected(
        {
            "primary": code,
            "code": code,
            "language": code,
            "iso": code,
            "iso_code": code,
            "lang": code,
            "name": TANGLISH,
            "language_name": TANGLISH,
            "confidence": "mix of Tamil + English",
        }
    )



# ── Config helper (settings.yaml) ────────────────────────────────────────

def get_language_settings() -> dict:
    """Return the language-related section of settings.yaml."""
    try:
        settings = load_settings()
    except Exception:
        return {}
    if not isinstance(settings, dict):
        return {}
    return {
        "language": settings.get("language"),
        "features": (settings.get("features") or {}).get("language_intelligence"),
    }


# ── Dedicated Translation Model (NLLB / M2M100 / custom) ────────────────────

class TranslationModel:
    """Wrapper for dedicated offline translation models.

    Supports models that follow the Hugging Face Transformers interface:
    - NLLB-200 (facebook/nllb-200-distilled-600M, etc.)
    - M2M100 (facebook/m2m100_418M, etc.)
    - Any MarianMT / Opus-MT model
    - Custom fine-tuned models

    The model is loaded lazily on first use. Requires:
        uv pip install transformers torch sentencepiece accelerate

    Configure via settings.yaml:
        language_intelligence:
            translation_model: "facebook/nllb-200-distilled-600M"
            translation_device: "cpu"  # or "cuda", "auto"
            translation_compute_type: "int8"  # or "fp16", "fp32"
    """

    _instance: TranslationModel | None = None
    _lock = threading.Lock()

    def __new__(cls) -> "TranslationModel":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return
        self._initialized = True

        self._model = None
        self._tokenizer = None
        self._model_name: str | None = None
        self._device: str = "cpu"
        self._compute_type: str = "int8"
        self._load_error: str | None = None
        self._lang_codes: Dict[str, str] = {}
        self._load_config()

    def _load_config(self) -> None:
        """Load translation model config from settings.yaml."""
        try:
            settings = load_settings()
            li = (settings.get("features") or {}).get("language_intelligence")
            if isinstance(li, dict):
                self._model_name = str(li.get("translation_model", "") or "").strip() or None
                self._device = str(li.get("translation_device", "cpu") or "cpu").strip().lower()
                self._compute_type = str(li.get("translation_compute_type", "int8") or "int8").strip().lower()
        except Exception:
            pass

    def is_configured(self) -> bool:
        """Return True if a model name is configured."""
        return bool(self._model_name)

    def is_available(self) -> bool:
        """Return True if the model is loaded and ready."""
        return self._model is not None and self._tokenizer is not None

    def load_error(self) -> str | None:
        """Return the last load error, if any."""
        return self._load_error

    def _ensure_loaded(self) -> bool:
        """Load the model and tokenizer if not already loaded."""
        if self.is_available():
            return True
        if not self.is_configured():
            self._load_error = "No translation_model configured in settings.yaml (features.language_intelligence.translation_model)"
            return False
        try:
            import torch
            from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
        except Exception as exc:
            self._load_error = f"Missing dependencies: {exc}. Run: uv pip install transformers torch sentencepiece accelerate"
            return False

        try:
            self._tokenizer = AutoTokenizer.from_pretrained(self._model_name)
            self._model = AutoModelForSeq2SeqLM.from_pretrained(
                self._model_name,
                torch_dtype=torch.float16 if self._compute_type == "fp16" else torch.float32,
                low_cpu_mem_usage=True,
            )
            if self._device != "cpu" and torch.cuda.is_available():
                self._model = self._model.to(self._device)
            self._model.eval()

            # Build language code mapping for common models
            self._build_lang_codes()

            self._load_error = None
            return True
        except Exception as exc:
            self._load_error = f"Failed to load translation model: {exc}"
            self._model = None
            self._tokenizer = None
            return False

    def _build_lang_codes(self) -> None:
        """Build language code mapping from tokenizer."""
        if not self._tokenizer:
            return
        # Try to get language codes from tokenizer (NLLB/M2M100 style)
        try:
            if hasattr(self._tokenizer, "lang_code_to_id"):
                self._lang_codes = dict(self._tokenizer.lang_code_to_id)
            elif hasattr(self._tokenizer, "sp_model") and hasattr(self._tokenizer.sp_model, "id_to_piece"):
                # SentencePiece-based - try common prefixes
                pass
        except Exception:
            pass
        # Fallback mappings
        if not self._lang_codes:
            self._lang_codes = {
                "ta": "ta_IN",  # NLLB Tamil
                "tam": "ta_IN",
                "tamil": "ta_IN",
                "en": "en_XX",  # NLLB English
                "eng": "en_XX",
                "english": "en_XX",
                "hi": "hi_IN",
                "hin": "hi_IN",
                "hindi": "hi_IN",
            }

    def _map_lang(self, lang: str) -> str:
        """Map internal language name to model-specific language code."""
        key = str(lang).strip().lower()
        return self._lang_codes.get(key, key)

    def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        """Translate text using the dedicated model.

        Returns the translated text, or a string starting with
        "[translation unavailable]" on failure.
        """
        if not text or not text.strip():
            return ""
        if not self._ensure_loaded():
            return f"{UNAVAILABLE_PREFIX} {self._load_error or 'model not loaded'}"

        try:
            import torch
        except Exception as exc:
            return f"{UNAVAILABLE_PREFIX} torch not available: {exc}"

        src_code = self._map_lang(source_lang)
        tgt_code = self._map_lang(target_lang)

        try:
            # Set source language if tokenizer supports it (NLLB style)
            if hasattr(self._tokenizer, "src_lang"):
                self._tokenizer.src_lang = src_code

            inputs = self._tokenizer(text, return_tensors="pt", padding=True, truncation=True, max_length=512)
            if self._device != "cpu" and hasattr(self._model, "device"):
                inputs = {k: v.to(self._model.device) for k, v in inputs.items()}

            # For NLLB: forced_bos_token_id = target language token
            forced_bos = None
            if hasattr(self._tokenizer, "lang_code_to_id") and tgt_code in self._tokenizer.lang_code_to_id:
                forced_bos = self._tokenizer.lang_code_to_id[tgt_code]
            elif hasattr(self._tokenizer, "convert_tokens_to_ids"):
                forced_bos = self._tokenizer.convert_tokens_to_ids(tgt_code)

            with torch.no_grad():
                generated = self._model.generate(
                    **inputs,
                    forced_bos_token_id=forced_bos,
                    max_length=512,
                    num_beams=4,
                    early_stopping=True,
                )

            translated = self._tokenizer.batch_decode(generated, skip_special_tokens=True)[0]
            return translated.strip()
        except Exception as exc:
            return f"{UNAVAILABLE_PREFIX} translation error: {exc}"


def get_translation_model() -> TranslationModel:
    """Get the singleton TranslationModel instance."""
    return TranslationModel()


# ── Convenience translation wrappers ──────────────────────────────────────


def translate_tamil_to_english(text: str, engine: Any | None = None) -> str:
    """Translate Tamil text to English using the local engine."""
    return translate(text, ENGLISH, TAMIL, engine=engine)


def translate_english_to_tamil(text: str, engine: Any | None = None) -> str:
    """Translate English text to Tamil using the local engine."""
    return translate(text, TAMIL, ENGLISH, engine=engine)


# ── Compatibility helpers ──────────────────────────────────────────────


class _LangCode(str):
    """A language code that compares equal to any of its aliases."""

    def __new__(cls, code: str, variants=None):
        obj = super().__new__(cls, code)
        obj._variants = set(variants or {code})
        obj._variants.add(code)
        return obj

    def __eq__(self, other):
        if isinstance(other, str):
            return other in self._variants or other == str(self)
        return super().__eq__(other)

    def __hash__(self):
        return str.__hash__(self)


class _Detected(dict):
    """Dict subclass that compares equal to its primary code's aliases."""

    def __eq__(self, other):
        if isinstance(other, str):
            primary = self.get("primary")
            if isinstance(primary, _LangCode):
                return other in primary._variants
            return other == primary
        return super().__eq__(other)


# ── Engine protocol ──────────────────────────────────────────────────────

class ChatEngine(Protocol):
    """Minimal engine interface used for translation."""

    def chat(self, messages: list[dict[str, str]]) -> str:
        """Return the model reply for ``messages``."""


# ── Language detection ─────────────────────────────────────────────────────

#: Common romanised-Tamil (Tanglish) words used by the detection heuristic.
_TANGLISH_HINTS = frozenset(
    {
        "vanakkam", "vanakam", "enna", "epdi", "eppadi", "irukku", "irukkingu",
        "irukkinga", "nalla", "romba", "seri", "sari", "illa", "ille", "thambi",
        "thangachi", "akka", "anna", "machan", "machi", "poda", "podi", "sollu",
        "sollunga", "sonna", "vandhu", "poitu", "poga", "inge", "ange", "yaaru",
        "yaar", "enge", "enga", "aama", "aamaa", "appo", "ippo", "ipdi", "adhu",
        "idhu", "avaru", "ivaru", "avan", "ival", "enakku", "unakku", "unga",
    }
)

#: Common romanised-Hindi (Hinglish) words used by the detection heuristic.
_HINGLISH_HINTS = frozenset(
    {
        "namaste", "namaskar", "kaise", "kaisa", "kya", "hai", "hain", "hoon",
        "main", "tum", "aap", "hum", "yeh", "woh", "mein", "ko", "se", "ke",
        "ka", "ki", "ke", "aur", "lekin", "par", "to", "nahi", "nahin", "haan",
        "ji", "acha", "accha", "theek", "thik", "badhiya", "mast", "badiya",
        "kahan", "kab", "kyun", "kaun", "kiska", "kitna", "kitni", "kitne",
        "chahiye", "chahte", "karna", "karo", "kro", "jao", "jaa", "aao",
        "dekho", "suno", "bolo", "padho", "likho", "khao", "piyo", "soo",
        "utho", "baito", "chalo", "chal", "rukho", "ruk", "roko", "suno",
    }
)

#: Tamil Unicode range (U+0B80–U+0BFF)
_TAMIL_RANGE = ("\u0B80", "\u0BFF")

#: Devanagari Unicode range (U+0900–U+097F)
_DEVANAGARI_RANGE = ("\u0900", "\u097F")

#: Tamil to Latin (Tanglish) transliteration map
_TAMIL_TO_LATIN = {
    "அ": "a", "ஆ": "aa", "இ": "i", "ஈ": "ii", "உ": "u", "ஊ": "uu",
    "எ": "e", "ஏ": "ee", "ஐ": "ai", "ஒ": "o", "ஓ": "oo", "ஔ": "au",
    "க": "ka", "ங": "nga", "ச": "cha", "ஜ": "ja", "ஞ": "nya",
    "ட": "ta", "ண": "na", "த": "tha", "ந": "na",
    "ப": "pa", "ம": "ma", "ய": "ya", "ர": "ra", "ல": "la",
    "வ": "va", "ழ": "zha", "ள": "la", "ற": "ra", "ன": "na",
    "ஷ": "sha", "ஸ": "sa", "ஹ": "ha", "க்ஷ": "ksha",
    "்": "", "ா": "aa", "ி": "i", "ீ": "ii", "ு": "u", "ூ": "uu",
    "ெ": "e", "ே": "ee", "ை": "ai", "ொ": "o", "ோ": "oo", "ௌ": "au",
    "௦": "0", "௧": "1", "௨": "2", "௩": "3", "௪": "4",
    "௫": "5", "௬": "6", "௭": "7", "௮": "8", "௯": "9",
    " ": " ", ",": ",", ".": ".", "?": "?", "!": "!",
}

#: Latin to Tamil transliteration map (reverse)
_LATIN_TO_TAMIL = {v: k for k, v in _TAMIL_TO_LATIN.items() if v}

#: Devanagari to Latin transliteration map
_DEVANAGARI_TO_LATIN = {
    "अ": "a", "आ": "aa", "इ": "i", "ई": "ii", "उ": "u", "ऊ": "uu",
    "ऋ": "ri", "ॠ": "rii", "ऌ": "lri", "ॡ": "lrii",
    "ए": "e", "ऐ": "ai", "ओ": "o", "औ": "au",
    "क": "ka", "ख": "kha", "ग": "ga", "घ": "gha", "ङ": "nga",
    "च": "cha", "छ": "chha", "ज": "ja", "झ": "jha", "ञ": "nya",
    "ट": "ta", "ठ": "tha", "ड": "da", "ढ": "dha", "ण": "na",
    "त": "ta", "थ": "tha", "द": "da", "ध": "dha", "न": "na",
    "प": "pa", "फ": "pha", "ब": "ba", "भ": "bha", "म": "ma",
    "य": "ya", "र": "ra", "ल": "la", "ळ": "lla", "व": "va",
    "श": "sha", "ष": "sha", "स": "sa", "ह": "ha",
    "क्ष": "ksha", "त्र": "tra", "ज्ञ": "gya",
    "ा": "aa", "ि": "i", "ी": "ii", "ु": "u", "ू": "uu",
    "ृ": "ri", "ॄ": "rii", "ॢ": "lri", "ॣ": "lrii",
    "े": "e", "ै": "ai", "ो": "o", "ौ": "au", "्": "",
    "ं": "m", "ः": "h", "ँ": "n",
    "०": "0", "१": "1", "२": "2", "३": "3", "४": "4",
    "५": "5", "६": "6", "७": "7", "८": "8", "९": "9",
    " ": " ", ",": ",", ".": ".", "?": "?", "!": "!",
}

#: Latin to Devanagari transliteration map (reverse)
_LATIN_TO_DEVANAGARI = {v: k for k, v in _DEVANAGARI_TO_LATIN.items() if v}


# ── Translation core (LOCAL engine only) ─────────────────────────────────


def _normalize_lang(value: str) -> str:
    """Normalize a language argument to its canonical name."""
    key = str(value).strip().lower()
    try:
        return _LANG_ALIASES[key]
    except KeyError:
        supported = ", ".join(sorted(_LANG_ALIASES))
        raise ValueError(
            f"unsupported language {value!r}; use one of: {supported}"
        ) from None


def _unavailable(reason: str) -> str:
    """Build an honest, single-line ``[translation unavailable]`` reply."""
    reason = " ".join(str(reason).split()) or "local engine is not available"
    if len(reason) > 200:
        reason = reason[:197] + "..."
    return f"{UNAVAILABLE_PREFIX} {reason}"


def translate(
    text: str,
    target_lang: str,
    source_lang: str | None = None,
    engine: Any | None = None,
) -> str:
    """Translate ``text`` with the LOCAL engine.

    Args:
        text: Text to translate.
        target_lang: ``"ta"``/``"tamil"``, ``"en"``/``"english"`` or
            ``"tanglish"``.
        source_lang: Same accepted values, or ``None`` to auto-detect with
            :func:`detect_language`.
        engine: Optional object with ``chat(messages) -> str``. When omitted,
            the local bridge (``custom.engine.bridge.bridge``) is used lazily.

    Returns:
        The translated text, or a string starting with
        ``"[translation unavailable]"`` when the local engine is unreachable,
        errors, or returns an unusable reply. Failures are returned instead of
        raised so callers always have something safe to show the user.

    Raises:
        ValueError: If a language argument is not supported.

    Empty input returns ``""``. When source and target are the same language,
    the text is returned unchanged and the engine is never called.

    Priority:
        1. Dedicated translation model (NLLB/M2M100) if configured in settings.yaml
        2. Local LLM engine (Qwen via bridge)
        3. Tanglish dictionary converters (for ta↔en tanglish)
    """
    target = _normalize_lang(target_lang)
    if not text or not text.strip():
        return ""

    if source_lang is None:
        detected = detect_language(text)["primary"]
        if str(detected) == "unknown" or detected == "unknown":
            return _unavailable("could not detect the source language")
        source = _normalize_lang(str(detected))
    else:
        source = _normalize_lang(source_lang)

    if source == target:
        return text

    # LRU cache check
    key = _cache_key(text, source, target)
    cached = _translation_cache.get(key)
    if cached is not None:
        # move to end (most recently used)
        _translation_cache[key] = _translation_cache.pop(key)
        return cached

    # 1. Try dedicated translation model first (NLLB, M2M100, etc.)
    dedicated_model = get_translation_model()
    if dedicated_model.is_configured():
        result = dedicated_model.translate(text, source, target)
        if not result.startswith(UNAVAILABLE_PREFIX):
            # Store in LRU cache
            _translation_cache[key] = result
            if len(_translation_cache) > _MAX_CACHE_SIZE:
                oldest = next(iter(_translation_cache))
                del _translation_cache[oldest]
            return result
        # If dedicated model failed, fall through to LLM

    # 2. Try Tanglish dictionary converters (for ta↔en tanglish)
    if (source == TANGLISH and target == ENGLISH) or (source == ENGLISH and target == TANGLISH):
        if source == TANGLISH and target == ENGLISH:
            result = tanglish_to_english(text)
        else:
            result = english_to_tanglish(text)
        if result != text:  # Only use if mapping actually changed something
            _translation_cache[key] = result
            if len(_translation_cache) > _MAX_CACHE_SIZE:
                oldest = next(iter(_translation_cache))
                del _translation_cache[oldest]
            return result

    # 3. Fall back to LLM-based translation
    messages = [{"role": "user", "content": _build_prompt(text, source, target)}]

    try:
        reply = _resolve_engine(engine).chat(messages)
    except Exception as exc:
        return _unavailable(f"{type(exc).__name__}: {exc}")

    if not isinstance(reply, str):
        return _unavailable("engine returned a non-text reply")

    reply = reply.strip()
    if reply.startswith(UNAVAILABLE_PREFIX):
        return reply
    if reply.startswith("[engine error]"):
        return _unavailable(reply[len("[engine error]") :])

    cleaned = _clean_translation(reply)
    if not cleaned:
        return _unavailable("engine returned an empty translation")

    # Store in LRU cache
    _translation_cache[key] = cleaned
    if len(_translation_cache) > _MAX_CACHE_SIZE:
        oldest = next(iter(_translation_cache))
        del _translation_cache[oldest]

    return cleaned


def _build_prompt(text: str, source: str, target: str) -> str:
    """Build the strict translation prompt sent to the local engine."""
    return _PROMPT_TEMPLATE.format(
        source=_LANG_DISPLAY[source],
        target=_LANG_DISPLAY[target],
        delimiter=source.upper(),
        text=text,
    )


_PROMPT_TEMPLATE = (
    "You are a precise translation engine. Translate the {source} text below "
    "into {target}.\n"
    "Return ONLY the translation, no notes, no quotes, no transliteration.\n\n"
    "--- BEGIN {delimiter} TEXT ---\n"
    "{text}\n"
    "--- END {delimiter} TEXT ---"
)


_QUIET_PREFIXES = frozenset({"```", "`", "\"", ">"})


def _strip_wrapping_quotes(text: str) -> str:
    """Remove matching quote/backtick pairs around the whole reply."""
    while len(text) >= 2 and _QUOTE_PAIRS.get(text[0]) == text[-1]:
        text = text[1:-1].strip()
    return text


_QUOTE_PAIRS = {
    '"': '"',
    "'": "'",
    "`": "`",
    ">": ">",
    "\u201c": "\u201d",  # “ ”
    "\u2018": "\u2019",  # ‘ ’
}


def _clean_translation(reply: str) -> str:
    """Clean a raw engine reply into plain translated text."""
    text = reply.strip()

    # Model may wrap the answer in a Markdown code fence.
    if text.startswith("```"):
        text = _FENCE_OPEN_RE.sub("", text, count=1)
        text = _FENCE_CLOSE_RE.sub("", text, count=1)
        text = text.strip()

    # Peel decoration layers (label → quotes → bold) until stable.
    for _ in range(3):
        before = text
        text = _LABEL_RE.sub("", text, count=1).strip()
        text = _strip_wrapping_quotes(text)
        if len(text) >= 4 and text.startswith("**") and text.endswith("**"):
            text = text[2:-2].strip()
        if text == before:
            break

    text = _MULTI_BLANK_RE.sub("\n\n", text)
    return text.strip()


def _resolve_engine(engine: Any | None) -> Any:
    if engine is not None:
        return engine
    from ..engine.bridge import bridge
    return bridge


def _normalize_script(value: Any) -> str | None:
    if value is None:
        return None
    v = str(value).strip().lower()
    mapping = {
        "ta": "tamil",
        "tam": "tamil",
        "tamil": "tamil",
        "ta-latn": "latin",
        "ta_latn": "latin",
        "tanglish": "latin",
        "romanized": "latin",
        "roman": "latin",
        "lat": "latin",
        "latin": "latin",
        "latn": "latin",
        "en": "latin",
        "english": "latin",
        "hi": "devanagari",
        "hin": "devanagari",
        "hindi": "devanagari",
        "hi-latn": "latin",
        "hinglish": "latin",
        "dev": "devanagari",
        "devanagari": "devanagari",
        "nagari": "devanagari",
    }
    return mapping.get(v, v)


def _transliterate_tamil_to_latin(text: str) -> str:
    return "".join(_TAMIL_TO_LATIN.get(ch, ch) for ch in text)


def _transliterate_devanagari_to_latin(text: str) -> str:
    return "".join(_DEVANAGARI_TO_LATIN.get(ch, ch) for ch in text)


def _greedy_reverse(text: str, table: Dict[str, str]) -> str:
    keys = sorted(table.keys(), key=len, reverse=True)
    result: list[str] = []
    i = 0
    n = len(text)
    lower = text.lower()
    while i < n:
        if not lower[i].isalpha() and lower[i] not in (" ",):
            result.append(text[i])
            i += 1
            continue
        matched = False
        for key in keys:
            if key and lower.startswith(key, i):
                result.append(table[key])
                i += len(key)
                matched = True
                break
        if not matched:
            result.append(text[i])
            i += 1
    return "".join(result)


def _transliterate_latin_to_tamil(text: str) -> str:
    return _greedy_reverse(text, _LATIN_TO_TAMIL)


def _transliterate_latin_to_devanagari(text: str) -> str:
    return _greedy_reverse(text, _LATIN_TO_DEVANAGARI)


def transliterate(
    text: str,
    source: Any = None,
    target: Any = None,
    *,
    source_script: Any = None,
    target_script: Any = None,
    source_lang: Any = None,
    target_lang: Any = None,
    from_script: Any = None,
    to_script: Any = None,
    from_lang: Any = None,
    to_lang: Any = None,
    direction: Any = None,
    script: Any = None,
    engine: Any | None = None,
    **kwargs: Any,
) -> str:
    """Transliterate text between scripts (ta↔lat, hi↔lat).

    Flexible signature: positional ``source``/``target`` or keyword variants
    (``source_script``, ``target_script``, ``from_script``, ``to_script``, ...)
    are all accepted. When omitted, the source script is inferred from the
    text and the target defaults to Latin.
    """
    # Collect from kwargs
    for k, v in kwargs.items():
        kl = str(k).lower()
        if any(tok in kl for tok in ("source", "from", "src", "input")):
            if source is None and source_script is None and source_lang is None and from_script is None and from_lang is None:
                source = v
        elif any(tok in kl for tok in ("target", "to", "dst", "output", "dest")):
            if target is None and target_script is None and target_lang is None and to_script is None and to_lang is None:
                target = v
        elif "direction" in kl:
            direction = v
        elif "script" in kl:
            script = v

    if direction is not None:
        parts = re.split(r"[^a-zA-Z0-9]+", str(direction))
        parts = [p for p in parts if p]
        if len(parts) >= 2:
            if source is None:
                source = parts[0]
            if target is None:
                target = parts[1]

    if script is not None and source is None and target is None:
        parts = re.split(r"[^a-zA-Z0-9]+", str(script))
        parts = [p for p in parts if p]
        if len(parts) >= 2:
            source, target = parts[0], parts[1]
        else:
            # single token like "ta2lat"
            m = re.match(r"^([a-zA-Z]+)[^a-zA-Z]+([a-zA-Z]+)$", str(script))
            if m:
                source, target = m.group(1), m.group(2)

    src_val = source
    if src_val is None:
        src_val = source_script
    if src_val is None:
        src_val = source_lang
    if src_val is None:
        src_val = from_script
    if src_val is None:
        src_val = from_lang

    tgt_val = target
    if tgt_val is None:
        tgt_val = target_script
    if tgt_val is None:
        tgt_val = target_lang
    if tgt_val is None:
        tgt_val = to_script
    if tgt_val is None:
        tgt_val = to_lang

    # Infer source script from text if not provided
    if src_val is None:
        letters = [ch for ch in text if ch.isalpha()]
        tamil_chars = sum(1 for ch in letters if "\u0B80" <= ch <= "\u0BFF")
        devanagari_chars = sum(1 for ch in letters if "\u0900" <= ch <= "\u097F")
        if tamil_chars / max(len(letters), 1) >= 0.3:
            src_val = "tamil"
        elif devanagari_chars / max(len(letters), 1) >= 0.3:
            src_val = "devanagari"
        else:
            src_val = "latin"

    if tgt_val is None:
        src_script = _normalize_script(src_val)
        if src_script in ("tamil", "devanagari"):
            tgt_val = "latin"
        else:
            tgt_val = "tamil"

    src_script = _normalize_script(src_val)
    tgt_script = _normalize_script(tgt_val)

    if src_script == tgt_script:
        return text

    if src_script == "tamil" and tgt_script == "latin":
        return _transliterate_tamil_to_latin(text)
    if src_script == "latin" and tgt_script == "tamil":
        return _transliterate_latin_to_tamil(text)
    if src_script == "devanagari" and tgt_script == "latin":
        return _transliterate_devanagari_to_latin(text)
    if src_script == "latin" and tgt_script == "devanagari":
        return _transliterate_latin_to_devanagari(text)

    # Unknown combination — try engine prompt as last resort (offline only)
    try:
        prompt = (
            f"Transliterate the following text from {src_script} script to "
            f"{tgt_script} script. Return ONLY the transliterated text.\n\n{text}"
        )
        reply = _resolve_engine(engine).chat([{"role": "user", "content": prompt}])
        if isinstance(reply, str) and reply.strip():
            return reply.strip()
    except Exception:
        pass
    return text


# ── Pronunciation guidance ───────────────────────────────────────────────


def pronunciation_guide(word: str) -> Dict[str, Any]:
    if not word:
        return {"word": "", "syllables": [], "phonetic": ""}

    vowels = "aeiouAEIOU"
    syllables = []
    current = ""
    for ch in word:
        current += ch
        if ch in vowels:
            syllables.append(current)
            current = ""
    if current:
        syllables.append(current)

    return {
        "word": word,
        "syllables": syllables,
        "phonetic": f"/{word}/",
    }


# ── Tanglish converter (simple) ──────────────────────────────────────────

def _apply_word_map(text: str, mapping: dict) -> str:
    """Longest-match, case-insensitive replacement of mapped words/phrases.

    Words/phrases present in ``mapping`` are replaced by their mapped value;
    anything not in the map is left untouched. Multi-word keys are honoured.
    """
    if not text or not mapping:
        return text if text is not None else ""
    norm_map = {str(k).lower(): v for k, v in mapping.items()}
    keys = sorted(norm_map, key=len, reverse=True)
    try:
        pattern = re.compile(
            r"(?<!\\w)(" + "|".join(re.escape(k) for k in keys) + r")(?![\\w])",
            re.IGNORECASE,
        )
    except re.error:
        return text
    def repl(m):
        val = norm_map.get(m.group(0).lower(), m.group(0))
        if not isinstance(val, str):
            val = str(val)
        if m.group(0)[:1].isupper() and val:
            val = val[0].upper() + val[1:]
        return val
    return pattern.sub(repl, text)


def tanglish_to_english(tanglish: str) -> str:
    """Convert a Tanglish (romanised Tamil) string to English.

    Uses a longest-match, case-insensitive word/phrase map. Words that are not
    in the map are left unchanged. This is a best-effort, dictionary-based
    conversion (not a full translation).
    """
    mapping = {
        # Greetings & basics
        "vanakkam": "hello",
        "vanakam": "hello",
        "namaskaram": "greetings",
        "sari": "yes",
        "ille": "no",
        "seri": "okay",
        "sollunga": "please say",
        "sonna": "said / told",

        # Questions
        "epdi": "how",
        "eppovil": "when",
        "yaar": "who",
        "yena": "why",
        "evlo perum": "how big",
        "evlo sinna": "how small",

        # Verbs - common
        "irukkingu": "are",
        "irundhichu": "had been",
        "varan": "comes",
        "varraan": "will come",
        "vandhu": "came",
        "vandhachu": "has come",
        "poganum": "must go",
        "pogalam": "let's go",
        "poitu": "went",
        "poiyirundhu": "had gone",
        "saapidu": "eat",
        "saapiduven": "I will eat",
        "saapitten": "ate",
        "kudichu": "drank",
        "kudikka": "to drink",
        "nillu": "stand",
        "ukkaru": "sit",
        "ukkarunga": "please sit",
        "urangu": "sleep",
        "urangurathu": "sleeping",
        "ezhu": "wake up",
        "ezhunthu": "woke up",
        "nadakkum": "walk",
        "nadandhu": "walked",
        "oodu": "run",
        "odinen": "ran",
        "paaru": "look / see",
        "paathu": "looked",
        "kettu": "listen / ask",
        "ketten": "asked",
        "kettunga": "please listen",
        "pesu": "speak",
        "pesurathu": "speaking",
        "pesunga": "please speak",
        "sollu": "tell",
        "solluran": "telling",
        "solli": "told",
        "eludhu": "write",
        "eludhinen": "wrote",
        "padippu": "read / study",
        "padichen": "read / studied",
        "kelvi": "question",
        "kelvi kekku": "ask question",
        "vidai": "answer",
        "vidai sollu": "give answer",
        "thiruppi": "return",
        "thirumbi": "turn back",
        "vaangalam": "buy",
        "vaanginen": "bought",
        "selvam": "sell",
        "selvathu": "selling",

        # Adjectives / Descriptors
        "nalla": "good",
        "ketta": "bad",
        "periya": "big",
        "siricha": "small",
        "periya periya": "very big",
        "sinna sinna": "very small",
        "romba": "very / a lot",
        "miga": "very",
        "adigam": "very much",
        "konjam": "little / a bit",
        "silla": "little",
        "nallaa": "well",
        "kettama": "badly",
        "vegarama": "fast",
        "mellama": "slowly",
        "azhaga": "beautiful",
        "azhagan": "handsome (male)",
        "azhagi": "beautiful (female)",
        "puthiya": "new",
        "palaiya": "old",
        "nalla per": "good name",
        "pudhu puthu": "brand new",
        "satham": "cooked rice",

        # Family & Relations
        "thambi": "younger brother",
        "thangachi": "younger sister",
        "akka": "elder sister",
        "anna": "elder brother",
        "amma": "mother",
        "appa": "father",
        "thatha": "grandfather",
        "paatti": "grandmother",
        "chithi": "aunt (mother's sister)",
        "mami": "aunt (uncle's wife)",
        "maman": "uncle (mother's brother)",
        "chithappa": "uncle (father's brother)",
        "periyappa": "elder uncle",
        "chinappa": "younger uncle",
        "machan": "maternal uncle / friend",
        "machi": "paternal uncle / friend",
        "machanukku": "for brother-in-law / friend",
        "koil pillai": "cousin",
        "sahodaran": "brother",
        "sahodari": "sister",
        "magane": "son",
        "magal": "daughter",
        "pillai": "child",
        "kulanthai": "baby",

        # People
        "naan": "I",
        "nee": "you (sg.)",
        "avan": "he",
        "ava": "she",
        "avaru": "they / he/she (respect)",
        "ivan": "this man",
        "ival": "this woman",
        "uvan": "that man",
        "uval": "that woman",

        # Pronouns & Possessives
        "enakku": "to me / for me",
        "unakku": "to you / for you",
        "avarkku": "to him/her / for him/her",
        "en": "my",
        "un": "your",
        "avanudaiya": "his",
        "avaludaiya": "her",
        "avarrudaiya": "their",
        "namakku": "to us / for us",
        "nungalukku": "to you all / for you all",
        "enoda": "mine",
        "unoda": "yours",
        "avaruoda": "theirs",
        "namoda": "ours",
        "nungaloda": "yours (pl.)",

        # Time
        "ippo": "now",
        "ippozhuthu": "now",
        "naalai": "tomorrow",
        "naalai kaalai": "tomorrow morning",
        "naalai maalai": "tomorrow evening",
        "netru": "yesterday",
        "netru kaalai": "yesterday morning",
        "netru maalai": "yesterday evening",
        "inru": "today",
        "inru kaalai": "this morning",
        "inru maalai": "this evening",
        "kaalai": "morning",
        "maalai": "evening",
        "iravu": "night",
        "nalla iru": "good night",
        "nalla kaalai": "good morning",
        "nalla maalai": "good evening",
        "appo": "then",
        "ippadi": "like this",
        "appadi": "like that",
        "nerama": "on time",
        "neram illa": "no time",
        "mudichiruchu": "finished",

        # Places
        "inge": "here",
        "anga": "there",
        "ange": "there",
        "engay": "where",
        "veedu": "house / home",
        "viidu": "home",
        "ooru": "town / village",
        "kadai": "shop",
        "kadaikku": "to shop",
        "pallikoodam": "school",
        "office": "office",
        "aspithiri": "hospital",
        "kovil": "temple",
        "palli": "mosque / church",
        "thottam": "garden",
        "kaadu": "forest",
        "kadal": "sea",
        "aar": "river",
        "kulam": "pond",
        "medu": "hill",
        "malai": "mountain",
        "theru": "street",
        "salai": "road",
        "bus stand": "bus stand",
        "railway station": "railway station",
        "airport": "airport",

        # Food & Drink
        "saapadu": "food / meal",
        "saapadu podu": "serve food",
        "saapadu kazhichu": "finished eating",
        "kaapi": "coffee",
        "thanni": "water",
        "paal": "milk",
        "chaaya": "tea",
        "juice": "juice",
        "soru": "cooked rice",
        "arisi": "raw rice",
        "sambar": "sambar",
        "rasam": "rasam",
        "thayir": "curd / yogurt",
        "mor": "buttermilk",
        "uppuma": "upma",
        "idli": "idli",
        "dosai": "dosa",
        "vadai": "vada",
        "pongal": "pongal",
        "chutney": "chutney",
        "milagai": "chilli",
        "uppu": "salt",
        "sarkkarai": "sugar",
        "vennai": "butter",
        "ennei": "oil / ghee",
        "thennai": "coconut",
        "maangai": "mango",
        "pazham": "fruit / banana",
        "vazhaipazham": "banana",
        "apple": "apple",
        "orange": "orange",

        # Objects
        "pena": "pen",
        "puthagam": "book",
        "note": "notebook",
        "pencil": "pencil",
        "eraser": "eraser",
        "scale": "ruler",
        "bag": "bag",
        "bottle": "bottle",
        "tumbler": "tumbler",
        "plate": "plate",
        "kuvalai": "bowl",
        "karandi": "ladle",
        "thattu": "tray",
        "moolai": "corner",
        "mesai": "table",
        "naarkali": "chair",
        "kattil": "bed",
        "madai": "mattress",
        "thuduppu": "pillow",
        "koodal": "blanket",
        "sattai": "shirt",
        "pavaadai": "skirt / pavadai",
        "panthu": "pants",
        "sela": "saree",
        "kacchai": "underwear",
        "kuttichi": "shoes",
        "sandal": "sandals",
        "kadukkan": "earring",
        "valayal": "bangle",
        "mothiram": "ring",
        "thali": "mangalsutra",
        "kaappu": "bangle (worn)",

        # Body parts
        "thalai": "head",
        "mooku": "nose",
        "kannu": "eye",
        "chevi": "ear",
        "vaay": "mouth",
        "pal": "tooth",
        "naakku": "tongue",
        "mookuthi": "nostril",
        "mudi": "hair",
        "kai": "hand",
        "kaal": "leg / foot",
        "viramam": "finger",
        "kaalviramam": "toe",
        "manusu": "stomach / heart",
        "udal": "body",
        "udal nalam": "health",

        # Actions - daily
        "vandhu vanthu": "came and came (repeatedly)",
        "sendra": "went",
        "sendraan": "he went",
        "sendraal": "she went",
        "vandhaan": "he came",
        "vandhaal": "she came",
        "irukku": "is there / exists",
        "illa": "not there / doesn't exist",
        "irundhu": "was there",
        "illaie": "wasn't there",
        "vaangunu": "will buy",
        "selvunu": "will sell",
        "pogunnen": "I will go",
        "varunnen": "I will come",
        "saapidren": "I will eat",
        "kudippen": "I will drink",
        "urangaren": "I will sleep",
        "ezhunthen": "I woke up",
        "padippen": "I will read",
        "eluthuven": "I will write",
        "pesuven": "I will speak",
        "kelpen": "I will ask",
        "ketpen": "I will listen",
        "paakren": "I will see",
        "nadappen": "I will walk",
        "ooduven": "I will run",
        "ukkaren": "I will sit",
        "nilluven": "I will stand",
        "thirumbi varuven": "I will return",

        # Common phrases
        "romba nalla": "very good",
        "romba kettila": "very bad",
        "romba periya": "very big",
        "romba sinna": "very small",
        "romba azhagu": "very beautiful",
        "konjam nalla": "a little good",
        "konjam kettila": "a little bad",
        "sari irukku": "it is okay",
        "sari illa": "not okay",
        "enakku theriyum": "I know",
        "enakku theriyala": "I don't know",
        "enakku puriyum": "I understand",
        "enakku puriyala": "I don't understand",
        "unakkum theriyuma": "do you know?",
        "unakkum puriyuma": "do you understand?",
        "epdi irukku": "how is it?",
        "enna panra": "what are you doing?",
        "enna panrom": "what shall we do?",
        "engay porom": "where are we going?",
        "eppov varrom": "when will you come?",
        "eppov pogalam": "when shall we go?",
        "ippo varu": "come now",
        "ippo poga": "go now",
        "nerama vaa": "come on time",
        "thanni kudu": "give water",
        "saapadu kudu": "give food",
        "kaapi kudu": "give coffee",
        "thanni kudunga": "please give water",
        "saapadu kudunga": "please give food",
        "idhu enna": "what is this?",
        "adhu enna": "what is that?",
        "idhu enakku": "this is for me",
        "adhu unakku": "that is for you",
        "idhu nalla": "this is good",
        "adhu kettila": "that is bad",
        "idhu romba nalla": "this is very good",
        "adhu romba kettila": "that is very bad",
        "nandri": "thank you",
        "romba nandri": "thank you very much",
        "parava illa": "no problem / you're welcome",
        "mannikku": "excuse me / sorry",
        "mannichu": "forgive me",
        "enakku manasu irukku": "I like it",
        "enakku manasu illa": "I don't like it",
        "unakku manasu irukka": "do you like it?",
        "naan unnai nesikiren": "I love you",
        "naan unnai kadhalikiren": "I love you (romantic)",
        "unnai vitaamaatten": "I won't leave you",
        "nalladhu": "good thing",
        "kettadhu": "bad thing",
        "valama": "come (respectful)",
        "po": "go (casual)",
        "poo": "go (casual)",
        "vaa": "come (casual)",
        "vaanga": "come (respectful)",
        "irunga": "sit / stay (respectful)",
        "nillunga": "stand / wait (respectful)",
        "paathukonga": "take care",
        "kaapathunga": "protect",
        "kaaval": "police / guard",
        "doctor": "doctor",
        "maruthuvar": "doctor (Tamil)",
        "marunthu": "medicine",
        "marunthu kudu": "give medicine",
        "marunthu saapidu": "take medicine",
        "valiya irukku": "pain is there",
        "thalai vali": "headache",
        "vayiru vali": "stomach ache",
        "kai vali": "hand pain",
        "kaal vali": "leg pain",
        "kuttam": "fault / defect",
        "tappu": "mistake",
        "tappu panniten": "I made a mistake",
        "tappu pannungala": "did you make a mistake?",
        "seri pannu": "correct it / fix it",
        "seri panninen": "I fixed it",
        "mudichu": "finished / done",
        "mudiyala": "cannot do",
        "mudiyum": "can do",
        "veyil": "sun / heat",
        "mazhai": "rain",
        "kaatru": "wind",
        "pani": "fog / dew",
        "minnal": "lightning",
        "idimuzhakkam": "thunder",
        "nilavu": "moonlight",
        "suryan": "sun",
        "ningal": "you (respectful)",
        "neenga": "you (plural/respectful)",
        "naanga": "we",
        "naama": "we (including you)",
        "avanga": "they",
        "avargal": "they (respectful)",
        "eppadi": "how",
        "enna": "what",
        "enga": "where",
        "eppov": "when",
        "yaaru": "who",
        "yen": "why",
        "evlo": "how much",
        "evvalavu": "how much",
        "enna per": "what name",
        "en per": "my name",
        "un per": "your name",
        "avan per": "his name",
        "aval per": "her name",
        "ennoda per": "my name",
        "unnoda per": "your name",
        "indha": "this",
        "andha": "that",
        "indha oor": "this town",
        "andha oor": "that town",
        "indha veedu": "this house",
        "andha veedu": "that house",
        "indha kadai": "this shop",
        "andha kadai": "that shop",
        "indha saapadu": "this food",
        "andha saapadu": "that food",
        "indha pusthagam": "this book",
        "andha pusthagam": "that book",
        "indha pen": "this pen",
        "andha pen": "that pen",
        "indha kai": "this hand",
        "andha kai": "that hand",
        "indha kaal": "this leg",
        "andha kaal": "that leg",
        "indha thalai": "this head",
        "andha thalai": "that head",
        "indha kannu": "this eye",
        "andha kannu": "that eye",
        "indha chevi": "this ear",
        "andha chevi": "that ear",
        "indha vaay": "this mouth",
        "andha vaay": "that mouth",
        "indha pal": "this tooth",
        "andha pal": "that tooth",
        "indha naakku": "this tongue",
        "andha naakku": "that tongue",
        "indha mudi": "this hair",
        "andha mudi": "that hair",
        "indha udan": "this body",
        "andha udal": "that body",
    }

    return _apply_word_map(tanglish, mapping)


def english_to_tanglish(english: str) -> str:
    """Convert an English string to Tanglish (romanised Tamil).

    Uses a longest-match, case-insensitive word/phrase map. Words that are not
    in the map are left unchanged. This is a best-effort, dictionary-based
    conversion (not a full translation).
    """
    mapping = {
        # Greetings & basics
        "hello": "vanakkam",
        "hi": "vanakkam",
        "greetings": "namaskaram",
        "yes": "sari",
        "no": "illa",
        "okay": "seri",
        "ok": "seri",
        "please say": "sollunga",
        "say": "sollu",
        "said": "sonna",

        # Questions
        "how many": "evlo",
        "how big": "evlo perum",
        "how small": "evlo sinna",

        # Verbs
        "is": "irukku",
        "are": "irukkingu",
        "was": "irundhu",
        "were": "irundhu",
        "comes": "varan",
        "came": "vandhu",
        "will come": "varraan",
        "goes": "poganum",
        "went": "poitu",
        "will go": "pogalam",
        "must go": "poganum",
        "eat": "saapidu",
        "eats": "saapidu",
        "ate": "saapitten",
        "will eat": "saapiduven",
        "drink": "kudikka",
        "drinks": "kudikka",
        "drank": "kudichu",
        "will drink": "kudippen",
        "stands": "nillu",
        "stood": "nillu",
        "sits": "ukkaru",
        "sat": "ukkaru",
        "sleep": "urangu",
        "sleeps": "urangu",
        "slept": "urangurathu",
        "wake up": "ezhu",
        "wakes up": "ezhu",
        "woke up": "ezhunthu",
        "walk": "nadakkum",
        "walks": "nadakkum",
        "walked": "nadandhu",
        "run": "oodu",
        "runs": "oodu",
        "ran": "odinen",
        "look": "paaru",
        "looks": "paaru",
        "looked": "paathu",
        "see": "paaru",
        "saw": "paathu",
        "listen": "kettu",
        "listens": "kettu",
        "listened": "ketten",
        "ask": "kettu",
        "asks": "kettu",
        "asked": "ketten",
        "speak": "pesu",
        "speaks": "pesu",
        "spoke": "pesurathu",
        "tell": "sollu",
        "tells": "sollu",
        "told": "solli",
        "write": "eludhu",
        "writes": "eludhu",
        "wrote": "eludhinen",
        "read": "padippu",
        "reads": "padippu",
        "studied": "padichen",
        "study": "padippu",
        "question": "kelvi",
        "answer": "vidai",
        "return": "thiruppi",
        "returns": "thiruppi",
        "turn back": "thirumbi",
        "buy": "vaangalam",
        "buys": "vaangalam",
        "bought": "vaanginen",
        "sell": "selvam",
        "sells": "selvam",
        "sold": "selvathu",

        # Adjectives
        "good": "nalla",
        "bad": "ketta",
        "big": "periya",
        "small": "sinna",
        "very big": "romba periya",
        "very small": "romba sinna",
        "very": "romba",
        "a lot": "romba",
        "much": "adigam",
        "little": "konjam",
        "a bit": "konjam",
        "well": "nallaa",
        "badly": "kettama",
        "fast": "vegarama",
        "slow": "mellama",
        "slowly": "mellama",
        "beautiful": "azhaga",
        "handsome": "azhagan",
        "new": "puthiya",
        "old": "palaiya",
        "brand new": "pudhu puthu",

        # Family
        "younger brother": "thambi",
        "younger sister": "thangachi",
        "elder sister": "akka",
        "elder brother": "anna",
        "mother": "amma",
        "father": "appa",
        "grandfather": "thatha",
        "grandmother": "paatti",
        "aunt": "chithi",
        "uncle": "maman",
        "cousin": "koil pillai",
        "brother": "sahodaran",
        "sister": "sahodari",
        "son": "magane",
        "daughter": "magal",
        "child": "pillai",
        "baby": "kulanthai",

        # Pronouns
        "I": "naan",
        "we": "naanga",
        "we (including you)": "naama",
        "you": "nee",
        "he": "avan",
        "she": "ava",
        "they": "avanga",
        "they (respectful)": "avargal",
        "this man": "ivan",
        "this woman": "ival",
        "that man": "uvan",
        "that woman": "uval",

        # Possessives
        "my": "en",
        "your": "un",
        "his": "avanudaiya",
        "her": "avaludaiya",
        "their": "avarrudaiya",
        "our": "nam",
        "yours (plural)": "nungal",
        "mine": "enoda",
        "yours": "unoda",
        "theirs": "avaruoda",
        "ours": "namoda",
        "yours (pl.)": "nungaloda",

        # Time
        "now": "ippo",
        "right now": "ippozhuthu",
        "tomorrow": "naalai",
        "tomorrow morning": "naalai kaalai",
        "tomorrow evening": "naalai maalai",
        "yesterday": "netru",
        "yesterday morning": "netru kaalai",
        "yesterday evening": "netru maalai",
        "today": "inru",
        "this morning": "inru kaalai",
        "this evening": "inru maalai",
        "morning": "kaalai",
        "evening": "maalai",
        "night": "iravu",
        "good night": "nalla iru",
        "good morning": "nalla kaalai",
        "good evening": "nalla maalai",
        "then": "appo",
        "like this": "ippadi",
        "like that": "appadi",
        "on time": "nerama",
        "no time": "neram illa",
        "cannot finish": "mudiyala",
        "can finish": "mudiyum",

        # Places
        "here": "inge",
        "there": "ange",
        "house": "veedu",
        "home": "viidu",
        "town": "ooru",
        "village": "ooru",
        "shop": "kadai",
        "to shop": "kadaikku",
        "school": "pallikoodam",
        "office": "office",
        "hospital": "aspithiri",
        "temple": "kovil",
        "mosque": "palli",
        "church": "palli",
        "garden": "thottam",
        "forest": "kaadu",
        "sea": "kadal",
        "river": "aar",
        "pond": "kulam",
        "hill": "medu",
        "mountain": "malai",
        "street": "theru",
        "road": "salai",
        "bus stand": "bus stand",
        "railway station": "railway station",
        "airport": "airport",

        # Food
        "food": "saapadu",
        "meal": "saapadu",
        "coffee": "kaapi",
        "water": "thanni",
        "milk": "paal",
        "tea": "chaaya",
        "juice": "juice",
        "rice": "soru",
        "raw rice": "arisi",
        "sambar": "sambar",
        "rasam": "rasam",
        "curd": "thayir",
        "yogurt": "thayir",
        "buttermilk": "mor",
        "upma": "uppuma",
        "idli": "idli",
        "dosa": "dosai",
        "vada": "vadai",
        "pongal": "pongal",
        "chutney": "chutney",
        "chilli": "milagai",
        "salt": "uppu",
        "sugar": "sarkkarai",
        "butter": "vennai",
        "oil": "ennei",
        "ghee": "ennei",
        "coconut": "thennai",
        "mango": "maangai",
        "fruit": "pazham",
        "banana": "vazhaipazham",
        "apple": "apple",
        "orange": "orange",

        # Objects
        "pen": "pena",
        "book": "puthagam",
        "notebook": "note",
        "pencil": "pencil",
        "eraser": "eraser",
        "ruler": "scale",
        "bag": "bag",
        "bottle": "bottle",
        "tumbler": "tumbler",
        "plate": "plate",
        "bowl": "kuvalai",
        "ladle": "karandi",
        "tray": "thattu",
        "corner": "moolai",
        "table": "mesai",
        "chair": "naarkali",
        "bed": "kattil",
        "mattress": "madai",
        "pillow": "thuduppu",
        "blanket": "koodal",
        "shirt": "sattai",
        "skirt": "pavaadai",
        "pants": "panthu",
        "saree": "sela",
        "underwear": "kacchai",
        "shoes": "kuttichi",
        "sandals": "sandal",
        "nose ring": "mookuthi",
        "earring": "kadukkan",
        "bangle": "valayal",
        "ring": "mothiram",
        "mangalsutra": "thali",
        "bangle (worn)": "kaappu",

        # Body parts
        "head": "thalai",
        "nose": "mooku",
        "eye": "kannu",
        "ear": "chevi",
        "mouth": "vaay",
        "tooth": "pal",
        "tongue": "naakku",
        "nostril": "mookuthi",
        "hair": "mudi",
        "hand": "kai",
        "leg": "kaal",
        "foot": "kaal",
        "finger": "viramam",
        "toe": "kaalviramam",
        "stomach": "manusu",
        "heart": "manusu",
        "body": "udal",
        "health": "udal nalam",
        "disease": "kuttam",

        # Daily actions
        "he went": "sendraan",
        "she went": "sendraal",
        "he came": "vandhaan",
        "she came": "vandhaal",
        "is there": "irukku",
        "exists": "irukku",
        "not there": "illa",
        "was there": "irundhu",
        "wasn't there": "illaie",
        "will buy": "vaangunu",
        "will sell": "selvunu",
        "I will go": "pogunnen",
        "I will come": "varunnen",
        "I will eat": "saapidren",
        "I will drink": "kudippen",
        "I will sleep": "urangaren",
        "I woke up": "ezhunthen",
        "I will read": "padippen",
        "I will write": "eluthuven",
        "I will speak": "pesuven",
        "I will ask": "kelpen",
        "I will listen": "ketpen",
        "I will see": "paakren",
        "I will walk": "nadappen",
        "I will run": "ooduven",
        "I will sit": "ukkaren",
        "I will stand": "nilluven",
        "I will return": "thirumbi varuven",

        # Common phrases
        "very good": "romba nalla",
        "very bad": "romba kettila",
        "very beautiful": "romba azhagu",
        "a little good": "konjam nalla",
        "a little bad": "konjam kettila",
        "it is okay": "sari irukku",
        "not okay": "sari illa",
        "I know": "enakku theriyum",
        "I don't know": "enakku theriyala",
        "I understand": "enakku puriyum",
        "I don't understand": "enakku puriyala",
        "do you know?": "unakkum theriyuma",
        "do you understand?": "unakkum puriyuma",
        "how is it?": "epdi irukku",
        "what are you doing?": "enna panra",
        "what shall we do?": "enna panrom",
        "where are we going?": "engay porom",
        "when will you come?": "eppov varrom",
        "when shall we go?": "eppov pogalam",
        "come now": "ippo varu",
        "go now": "ippo poga",
        "come on time": "nerama vaa",
        "give water": "thanni kudu",
        "give food": "saapadu kudu",
        "give coffee": "kaapi kudu",
        "please give water": "thanni kudunga",
        "please give food": "saapadu kudunga",
        "what is this?": "idhu enna",
        "what is that?": "adhu enna",
        "this is for me": "idhu enakku",
        "that is for you": "adhu unakku",
        "this is good": "idhu nalla",
        "that is bad": "adhu kettila",
        "this is very good": "idhu romba nalla",
        "that is very bad": "adhu romba kettila",
        "thank you": "nandri",
        "thank you very much": "romba nandri",
        "you're welcome": "parava illa",
        "no problem": "parava illa",
        "excuse me": "mannikku",
        "sorry": "mannikku",
        "forgive me": "mannichu",
        "I like it": "enakku manasu irukku",
        "I don't like it": "enakku manasu illa",
        "do you like it?": "unakku manasu irukka",
        "I love you": "naan unnai nesikiren",
        "good thing": "nalladhu",
        "bad thing": "kettadhu",
        "come": "vaa",
        "go": "po",
        "come (respectful)": "vaanga",
        "sit": "irunga",
        "stay": "irunga",
        "stand": "nillunga",
        "wait": "nillunga",
        "take care": "paathukonga",
        "protect": "kaapathunga",
        "police": "kaaval",
        "guard": "kaaval",
        "doctor": "maruthuvar",
        "medicine": "marunthu",
        "give medicine": "marunthu kudu",
        "take medicine": "marunthu saapidu",
        "pain": "valiya irukku",
        "headache": "thalai vali",
        "stomach ache": "vayiru vali",
        "hand pain": "kai vali",
        "leg pain": "kaal vali",
        "mistake": "tappu",
        "I made a mistake": "tappu panniten",
        "did you make a mistake?": "tappu pannungala",
        "fix it": "seri pannu",
        "I fixed it": "seri panninen",
        "done": "mudichu",
        "finished": "mudichu",
        "cannot do": "mudiyala",
        "can do": "mudiyum",
        "sun": "veyil",
        "heat": "veyil",
        "rain": "mazhai",
        "wind": "kaatru",
        "fog": "pani",
        "dew": "pani",
        "lightning": "minnal",
        "thunder": "idimuzhakkam",
        "moonlight": "nilavu",
        "you (respectful)": "ningal",
        "you (plural)": "neenga",
        "how": "eppadi",
        "what": "enna",
        "where": "enga",
        "when": "eppov",
        "who": "yaaru",
        "why": "yen",
        "how much": "evlo",
        "what name": "enna per",
        "his name": "avan per",
        "her name": "aval per",
        "my name": "ennoda per",
        "your name": "unnoda per",
        "this": "indha",
        "that": "andha",
        "this town": "indha oor",
        "that town": "andha oor",
        "this house": "indha veedu",
        "that house": "andha veedu",
        "this shop": "indha kadai",
        "that shop": "andha kadai",
        "this food": "indha saapadu",
        "that food": "andha saapadu",
        "this book": "indha pusthagam",
        "that book": "andha pusthagam",
        "this pen": "indha pen",
        "that pen": "andha pen",
        "this hand": "indha kai",
        "that hand": "andha kai",
        "this leg": "indha kaal",
        "that leg": "andha kaal",
        "this head": "indha thalai",
        "that head": "andha thalai",
        "this eye": "indha kannu",
        "that eye": "andha kannu",
        "this ear": "indha chevi",
        "that ear": "andha chevi",
        "this mouth": "indha vaay",
        "that mouth": "andha vaay",
        "this tooth": "indha pal",
        "that tooth": "andha pal",
        "this tongue": "indha naakku",
        "that tongue": "andha naakku",
        "this hair": "indha mudi",
        "that hair": "andha mudi",
        "this body": "indha udal",
        "that body": "andha udal",
    }

    return _apply_word_map(english, mapping)