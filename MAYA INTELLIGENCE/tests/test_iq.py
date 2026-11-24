"""Tests for IQ engine."""

import pytest


def test_iq_answer(mock_engine, mock_knowledge):
    """Test IQ answer method."""
    from maya_intelligence.engines import IQEngine

    iq = IQEngine(mock_engine, mock_knowledge, "Test persona")
    result = iq.answer("What is Python?", context="User likes programming")

    assert isinstance(result.text, str)
    assert len(result.text) > 0
    mock_engine.chat.assert_called_once()


def test_iq_answer_with_rag(mock_engine, mock_knowledge):
    """Test IQ answer with RAG."""
    from maya_intelligence.engines import IQEngine

    mock_knowledge.knowledge_search.return_value = [
        {"path": "doc1.txt", "content": "Python is a language"}
    ]

    iq = IQEngine(mock_engine, mock_knowledge, "Test persona")
    result = iq.answer("What is Python?", use_rag=True)

    assert result.used_rag is True
    assert len(result.sources) > 0
    mock_knowledge.knowledge_search.assert_called_once()


def test_iq_plan(mock_engine, mock_knowledge):
    """Test IQ plan method."""
    from maya_intelligence.engines import IQEngine

    # Mock engine to return a numbered list
    mock_engine.chat.return_value.text = "1. Step one\n2. Step two\n3. Step three"

    iq = IQEngine(mock_engine, mock_knowledge, "Test persona")
    steps = iq.plan("Build a web app")

    assert len(steps) == 3
    assert "Step one" in steps[0]
    assert "Step two" in steps[1]
    assert "Step three" in steps[2]


def test_iq_plan_fallback(mock_engine, mock_knowledge):
    """Test IQ plan fallback when no numbered list returned."""
    from maya_intelligence.engines import IQEngine

    mock_engine.chat.return_value.text = "Just some text without numbers"

    iq = IQEngine(mock_engine, mock_knowledge, "Test persona")
    steps = iq.plan("Do something")

    assert steps == ["Do something"]


def test_iq_with_eq_directive(mock_engine, mock_knowledge):
    """Test IQ answer includes EQ directive."""
    from maya_intelligence.engines import IQEngine

    iq = IQEngine(mock_engine, mock_knowledge, "Test persona")
    result = iq.answer("Hello", eq_directive="Be supportive")

    # Check that the call was made with the directive
    call_args = mock_engine.chat.call_args
    messages = call_args[0][0]
    system_msg = messages[0]["content"]
    assert "Be supportive" in system_msg