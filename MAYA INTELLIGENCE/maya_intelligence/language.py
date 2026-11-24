"""Reply-language detection and directives for Maya.

The JARVIS language tool is fine for long paragraphs but under-detects short
Tanglish chat ("En peru Deva. Naan Python learn panren."). This module is a
small, dependency-free detector tuned for Maya's chat traffic.
"""

from __future__ import annotations

import re

TAMIL_RANGE = ("\u0B80", "\u0BFF")

#: Distinctive Romanised-Tamil words. Deliberately excludes ambiguous English
#: words so normal English sentences are never misread as Tanglish.
TANGLISH_HINTS = frozenset(
    {
        "aana", "aandu", "adhu", "andha", "anga", "avan", "aval", "avanga",
        "azhaga", "azhudhu", "enna", "ennoda", "ennaku", "enakku", "epdi",
        "eppadi", "epo", "eppo", "ethu", "edhu", "ethukku", "edhukku",
        "illa", "illai", "innikku", "ippo", "irukku", "irukken", "irukkanga",
        "kaalai", "kaalaila", "kaduppu", "kashtam", "kathukiren",
        "kathukkanum", "kobam", "kopam", "konjam", "mudiyala", "naalai",
        "naan", "nalla", "nee", "neenga", "ninaivu", "nyabagam", "pannu",
        "pannunga", "panren", "panra", "panna", "pannitten", "padikkiren",
        "pesalam", "pesu", "pidikkum", "puriyala", "puriyudhu", "romba",
        "saayangaalam", "santhosham", "sari", "seri", "sollu", "sollunga",
        "sorvu", "soukiyam", "thambi", "thangachi", "theriyala", "theriyum",
        "thookam", "un", "unga", "ungaloda", "vanakkam", "valikuthu",
        "vela", "venum", "vendum", "vendam", "vera", "yaaru",
    }
)

_TAMIL_SCRIPT_RE = re.compile(r"[\u0B80-\u0BFF]")
_WORD_RE = re.compile(r"[A-Za-z]+")


def tamil_char_ratio(text: str) -> float:
    """Return the share of letters that are Tamil script (0.0-1.0)."""
    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return 0.0
    tamil = sum(1 for ch in letters if TAMIL_RANGE[0] <= ch <= TAMIL_RANGE[1])
    return tamil / len(letters)


def detect_language(text: str) -> str:
    """Detect chat language as ``english``, ``tanglish`` or ``tamil``.

    - Mostly Tamil script -> ``tamil``
    - Any Tamil script or distinctive Romanised-Tamil words -> ``tanglish``
    - Otherwise -> ``english``
    """
    if not text or not text.strip():
        return "english"

    ratio = tamil_char_ratio(text)
    if ratio >= 0.5:
        return "tamil"

    words = [w.lower() for w in _WORD_RE.findall(text)]
    if ratio > 0:
        return "tanglish"
    if words:
        hits = sum(1 for w in words if w in TANGLISH_HINTS)
        # One distinctive word is enough in a short chat message; in long
        # English paragraphs require a real mix before switching.
        if hits >= 1 and (len(words) <= 12 or hits / len(words) >= 0.15):
            return "tanglish"

    return "english"


def language_directive(language: str) -> str:
    """Return a strict system-prompt instruction for the reply language."""
    if language == "tamil":
        return (
            "The user wrote in Tamil. Reply fully in Tamil script. "
            "Do not switch to English except for product names or code."
        )
    if language == "tanglish":
        return (
            "The user wrote in Tanglish (Tamil + English). Reply in natural "
            "Tanglish: keep Tamil words in Tamil script and English/technical "
            "words in Latin letters, exactly like the user. Do NOT write the "
            "whole reply in Tamil script; keep English words in English."
        )
    return (
        "The user wrote in English. Reply ONLY in English. "
        "Do not use Tamil script or Tanglish words."
    )


def has_tamil_script(text: str) -> bool:
    """True when the text contains at least one Tamil-script character."""
    return bool(_TAMIL_SCRIPT_RE.search(text or ""))


def language_name(language: str) -> str:
    """Human-readable language label for prompts/messages."""
    return {
        "tamil": "Tamil",
        "tanglish": "Tanglish",
        "english": "English",
    }.get(language, "English")
