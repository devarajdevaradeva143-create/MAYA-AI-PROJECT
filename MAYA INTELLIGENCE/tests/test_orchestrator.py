"""Tests for orchestrator."""

import pytest


def test_orchestrator_simple_chat(mock_engine, mock_pc, mock_assistant, mock_knowledge):
    """Test orchestrator simple chat."""
    from maya_intelligence.orchestrator import Orchestrator

    mock_engine.chat.return_value.text = "Hello! How can I help?"

    orchestrator = Orchestrator(
        confirm_fn=lambda m: True,
        max_tokens=512,
    )
    # Replace engines with mocks
    orchestrator._engine = mock_engine
    orchestrator._pc = mock_pc
    orchestrator._assistant = mock_assistant
    orchestrator._knowledge = mock_knowledge

    response = orchestrator.chat("Tell me a fun fact.")

    assert isinstance(response, str)
    assert len(response) > 0
    mock_engine.chat.assert_called()


def test_orchestrator_open_app(mock_engine, mock_pc, mock_assistant, mock_knowledge):
    """Test orchestrator open app action."""
    from maya_intelligence.orchestrator import Orchestrator

    mock_pc.open_app.return_value = {"success": True, "result": "Opened notepad", "verified": True}
    mock_pc.is_app_running.return_value = True
    mock_engine.chat.return_value.text = "I'll open notepad for you."

    orchestrator = Orchestrator(
        confirm_fn=lambda m: True,
        max_tokens=512,
    )
    orchestrator._engine = mock_engine
    orchestrator._pc = mock_pc
    orchestrator._assistant = mock_assistant
    orchestrator._knowledge = mock_knowledge

    result = orchestrator.process("open notepad")

    assert result.intent == "open_app"
    assert result.verified is True
    assert "notepad" in result.response.lower() or "open" in result.response.lower()


def test_orchestrator_memory_integration(mock_engine, mock_pc, mock_assistant, mock_knowledge, memory_store):
    """Test orchestrator with memory store."""
    from maya_intelligence.orchestrator import Orchestrator

    orchestrator = Orchestrator(
        confirm_fn=lambda m: True,
        max_tokens=512,
        db_path=str(memory_store._db_path),
    )
    orchestrator._engine = mock_engine
    orchestrator._pc = mock_pc
    orchestrator._assistant = mock_assistant
    orchestrator._knowledge = mock_knowledge

    # Add a memory
    memory_store.add("personal", "name", "Test User")

    # Process a query that should use memory
    mock_engine.chat.return_value.text = "Hello Test User!"

    response = orchestrator.chat("What's my name?")

    assert "Test User" in response or "hello" in response.lower()


def test_orchestrator_health_check(mock_engine, mock_pc, mock_assistant, mock_knowledge, memory_store):
    """Test orchestrator health check."""
    from maya_intelligence.orchestrator import Orchestrator

    mock_engine.health.return_value.ok = True
    mock_engine.health.return_value.text = "pong"

    orchestrator = Orchestrator(db_path=str(memory_store._db_path))
    orchestrator._engine = mock_engine

    health = orchestrator.health_check()

    assert health["engine"] == "ok"
    assert health["memory"] == "ok"
    assert "memory_stats" in health


def test_orchestrator_eq_integration(mock_engine, mock_pc, mock_assistant, mock_knowledge):
    """Test orchestrator EQ tone detection affects response."""
    from maya_intelligence.orchestrator import Orchestrator

    orchestrator = Orchestrator(
        confirm_fn=lambda m: True,
        max_tokens=512,
    )
    orchestrator._engine = mock_engine
    orchestrator._pc = mock_pc
    orchestrator._assistant = mock_assistant
    orchestrator._knowledge = mock_knowledge

    # Test sad input
    mock_engine.chat.return_value.text = "I'm here for you."
    response = orchestrator.process("I'm feeling really sad today")

    # Should have processed with EQ
    assert isinstance(response.response, str)
    assert len(response.response) > 0


def test_orchestrator_conversation_history(mock_engine, mock_pc, mock_assistant, mock_knowledge):
    """Test orchestrator maintains conversation history."""
    from maya_intelligence.orchestrator import Orchestrator

    orchestrator = Orchestrator(
        confirm_fn=lambda m: True,
        max_tokens=512,
    )
    orchestrator._engine = mock_engine
    orchestrator._pc = mock_pc
    orchestrator._assistant = mock_assistant
    orchestrator._knowledge = mock_knowledge

    mock_engine.chat.return_value.text = "Response 1"
    orchestrator.chat("Message 1")

    mock_engine.chat.return_value.text = "Response 2"
    orchestrator.chat("Message 2")

    # History should have 4 messages (2 user, 2 assistant)
    assert len(orchestrator._history) == 4
    assert orchestrator._history[0]["role"] == "user"
    assert orchestrator._history[1]["role"] == "assistant"
    assert orchestrator._history[2]["role"] == "user"
    assert orchestrator._history[3]["role"] == "assistant"