"""Tests for chat-tuned language detection and response directives."""

import pytest


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Hi Maya, how are you?", "english"),
        ("Explain in one line why the sky is blue.", "english"),
        ("I feel tired today.", "english"),
        ("En peru Deva. Naan Python learn panren.", "tanglish"),
        ("Ippo time enna?", "tanglish"),
        ("Notepad open pannu.", "tanglish"),
        ("நான் நலமாக இருக்கிறேன்", "tamil"),
        ("நீ யார்?", "tamil"),
    ],
)
def test_detect_language(text, expected):
    from maya_intelligence.language import detect_language

    assert detect_language(text) == expected


def test_english_directive_forbids_tamil():
    from maya_intelligence.language import language_directive

    directive = language_directive("english")
    assert "ONLY in English" in directive
    assert "Tamil script" in directive


def test_tanglish_directive_keeps_technical_words():
    from maya_intelligence.language import language_directive

    directive = language_directive("tanglish")
    assert "Tanglish" in directive
    assert "Tamil script" in directive


def test_tamil_directive_requires_tamil_script():
    from maya_intelligence.language import language_directive

    directive = language_directive("tamil")
    assert "Tamil script" in directive


def test_language_adapter_normalises_jarvis_dict():
    """The JARVIS tool returns a dict-like object; the adapter must return str."""
    from maya_intelligence.adapters.language import LanguageAdapter

    adapter = LanguageAdapter()
    assert adapter.detect("Hi Maya, how are you?") == "english"
    assert adapter.get_response_language("Ippo time enna?") == "tanglish"
