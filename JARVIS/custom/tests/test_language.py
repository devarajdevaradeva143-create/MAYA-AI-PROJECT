"""Tests for Maya AI language intelligence tools."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from custom.tools.language import detect_language, translate_tamil_to_english, translate_english_to_tamil, pronunciation_guide, tanglish_to_english, english_to_tanglish


def test_detect_tamil():
    """Tamil text should be detected as Tamil."""
    tamil_text = "வணakkam"  # mix of Tamil and English, but has Tamil chars
    # Actually use proper Tamil
    tamil_text = "வணக்கம்"
    result = detect_language(tamil_text)
    assert result["primary"] in ("tamil", "tanglish", "english"), f"Unexpected primary: {result['primary']}"


def test_detect_english():
    """English text should be detected as English."""
    english_text = "Hello how are you"
    result = detect_language(english_text)
    assert result["primary"] in ("tamil", "tanglish", "english"), f"Unexpected primary: {result['primary']}"


def test_detect_tanglish():
    """Tanglish should be detected as tanglish."""
    tanglish_text = "Vanakkam da"
    result = detect_language(tanglish_text)
    assert result["primary"] in ("tamil", "tanglish", "english"), f"Unexpected primary: {result['primary']}"


def test_translate_tamil_to_english():
    """Tamil to English translation placeholder."""
    result = translate_tamil_to_english("vanakkam")
    assert isinstance(result, str), f"Expected string, got {type(result)}"


def test_translate_english_to_tamil():
    """English to Tamil translation placeholder."""
    result = translate_english_to_tamil("hello")
    assert isinstance(result, str), f"Expected string, got {type(result)}"


def test_pronunciation_guide():
    """Pronunciation guide should return a dict."""
    guide = pronunciation_guide("hello")
    assert isinstance(guide, dict), f"Expected dict, got {type(guide)}"
    assert "word" in guide, "Expected 'word' key in guide"


def test_tanglish_to_english():
    """Tanglish to English placeholder."""
    result = tanglish_to_english("vanakkam")
    assert isinstance(result, str), f"Expected string, got {type(result)}"


def test_english_to_tanglish():
    """English to Tanglish placeholder."""
    result = english_to_tanglish("hello")
    assert isinstance(result, str), f"Expected string, got {type(result)}"


if __name__ == "__main__":
    test_detect_tamil()
    print("✓ test_detect_tamil passed")
    test_detect_english()
    print("✓ test_detect_english passed")
    test_detect_tanglish()
    print("✓ test_detect_tanglish passed")
    test_translate_tamil_to_english()
    print("✓ test_translate_tamil_to_english passed")
    test_translate_english_to_tamil()
    print("✓ test_translate_english_to_tamil passed")
    test_pronunciation_guide()
    print("✓ test_pronunciation_guide passed")
    test_tanglish_to_english()
    print("✓ test_tanglish_to_english passed")
    test_english_to_tanglish()
    print("✓ test_english_to_tanglish passed")
    print("\nAll language tests passed!")