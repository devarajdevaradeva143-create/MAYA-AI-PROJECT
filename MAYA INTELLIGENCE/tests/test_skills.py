"""Tests for deterministic chat skills (math, date/time, identity)."""

import re
from datetime import datetime


def test_math_multiplication_is_exact():
    from maya_intelligence.engines.skills import resolve_skill

    answer, skill = resolve_skill("What is 17 * 24?")

    assert skill == "math"
    assert "408" in answer
    assert "508" not in answer


def test_math_supports_spaced_minus_and_decimals():
    from maya_intelligence.engines.skills import try_math

    assert try_math("10 - 4") == "10 - 4 = 6"
    assert try_math("7 / 2") == "7 ÷ 2 = 3.5"


def test_math_percent_of():
    from maya_intelligence.engines.skills import try_math

    assert try_math("20% of 150") == "20% of 150 = 30"


def test_math_division_by_zero_is_friendly():
    from maya_intelligence.engines.skills import try_math

    answer = try_math("8 / 0")
    assert answer is not None
    assert "division by zero" in answer.lower()


def test_dates_are_not_treated_as_math():
    from maya_intelligence.engines.skills import try_math

    assert try_math("2026-11-24") is None
    assert try_math("What is today's date?") is None


def test_non_math_text_is_ignored():
    from maya_intelligence.engines.skills import try_math

    assert try_math("Tell me about Python 3") is None
    assert try_math("How are you?") is None


def test_datetime_uses_real_clock():
    from maya_intelligence.engines.skills import try_datetime

    answer = try_datetime("What is today's date?", "english")
    assert answer is not None
    assert str(datetime.now().year) in answer


def test_datetime_tanglish():
    from maya_intelligence.engines.skills import try_datetime

    answer = try_datetime("Ippo time enna?", "tanglish")
    assert answer is not None
    assert answer.startswith("Ippo ")


def test_identity_matches_language():
    from maya_intelligence.engines.skills import try_identity

    english = try_identity("Who are you?", "english")
    tanglish = try_identity("Nee yaaru?", "tanglish")
    tamil = try_identity("நீ யார்?", "tamil")

    assert english is not None and "Maya" in english
    assert tanglish is not None and "Maya" in tanglish
    assert tamil is not None and "மாயா" in tamil
    # No Tamil script leaks into an English answer.
    assert not re.search(r"[\u0B80-\u0BFF]", english)
