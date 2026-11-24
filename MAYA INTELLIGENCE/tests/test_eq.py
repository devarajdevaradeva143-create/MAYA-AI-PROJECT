"""Tests for EQ engine."""

import pytest


def test_eq_analyze_sad():
    """Test sad tone detection."""
    from maya_intelligence.engines import EQEngine
    eq = EQEngine()
    result = eq.analyze("I'm feeling really sad and depressed today")
    assert result.tone == "sad"
    assert "gentle warmth" in result.directive.lower()


def test_eq_analyze_stressed():
    """Test stressed tone detection."""
    from maya_intelligence.engines import EQEngine
    eq = EQEngine()
    result = eq.analyze("I'm so overwhelmed and stressed with all this work")
    assert result.tone == "stressed"
    assert "calmly" in result.directive.lower()


def test_eq_analyze_angry():
    """Test angry tone detection."""
    from maya_intelligence.engines import EQEngine
    eq = EQEngine()
    result = eq.analyze("This is so frustrating! I'm really angry!")
    assert result.tone == "angry"
    assert "calm" in result.directive.lower()


def test_eq_analyze_tired():
    """Test tired tone detection."""
    from maya_intelligence.engines import EQEngine
    eq = EQEngine()
    result = eq.analyze("I'm exhausted and burnt out")
    assert result.tone == "tired"
    assert "gentle" in result.directive.lower()


def test_eq_analyze_happy():
    """Test happy tone detection."""
    from maya_intelligence.engines import EQEngine
    eq = EQEngine()
    result = eq.analyze("I'm so happy and excited about this!")
    assert result.tone == "happy"
    assert "positive" in result.directive.lower()


def test_eq_analyze_confused():
    """Test confused tone detection."""
    from maya_intelligence.engines import EQEngine
    eq = EQEngine()
    result = eq.analyze("I don't understand this at all, I'm confused")
    assert result.tone == "confused"
    assert "patient" in result.directive.lower()


def test_eq_analyze_neutral():
    """Test neutral tone (no strong emotion)."""
    from maya_intelligence.engines import EQEngine
    eq = EQEngine()
    result = eq.analyze("What's the weather like today?")
    assert result.tone == "neutral"
    assert result.directive == ""


def test_eq_directive_mapping():
    """Test all directive mappings exist."""
    from maya_intelligence.engines import EQEngine
    eq = EQEngine()
    for tone in ("sad", "stressed", "angry", "tired", "happy", "confused", "neutral"):
        directive = eq.get_directive(tone)
        assert isinstance(directive, str)