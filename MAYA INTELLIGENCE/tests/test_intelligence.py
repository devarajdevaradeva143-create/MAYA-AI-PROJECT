"""Tests for the improved orchestrator: math, language, memory, planning, actions."""

from maya_intelligence.adapters.engine import EngineResult
from maya_intelligence.orchestrator import Orchestrator


def _build(temp_db, mock_engine, mock_pc, mock_assistant, mock_knowledge, confirm=None):
    orchestrator = Orchestrator(
        confirm_fn=confirm or (lambda message: True),
        db_path=str(temp_db),
        persona="Test persona",
    )
    orchestrator._engine = mock_engine
    orchestrator._pc = mock_pc
    orchestrator._assistant = mock_assistant
    orchestrator._knowledge = mock_knowledge
    return orchestrator


def test_math_never_hits_the_model(temp_db, mock_engine, mock_pc, mock_assistant, mock_knowledge):
    orchestrator = _build(temp_db, mock_engine, mock_pc, mock_assistant, mock_knowledge)

    result = orchestrator.process("What is 17 * 24?")

    assert "408" in result.response
    assert result.intent == "math"
    mock_engine.chat.assert_not_called()


def test_english_question_retries_tamil_reply(
    temp_db, mock_engine, mock_pc, mock_assistant, mock_knowledge
):
    mock_engine.chat.side_effect = [
        EngineResult(ok=True, text="வணக்கம்! நான் நல்லா இருக்கேன்."),
        EngineResult(ok=True, text="I'm doing well, thanks! How about you?"),
    ]
    orchestrator = _build(temp_db, mock_engine, mock_pc, mock_assistant, mock_knowledge)

    result = orchestrator.process("Hi Maya, how are you?")

    assert result.response == "I'm doing well, thanks! How about you?"
    assert mock_engine.chat.call_count == 2


def test_facts_are_saved_and_recalled(
    temp_db, mock_engine, mock_pc, mock_assistant, mock_knowledge
):
    orchestrator = _build(temp_db, mock_engine, mock_pc, mock_assistant, mock_knowledge)

    first = orchestrator.process("En peru Deva. Naan Python learn panren.")
    assert first.memory_updated is True

    entry = orchestrator._memory.get("personal", "name")
    assert entry is not None and entry.value == "Deva"

    second = orchestrator.process("En peru enna?")
    assert second.intent == "recall"
    assert "Deva" in second.response


def test_explicit_remember_saves_fact(
    temp_db, mock_engine, mock_pc, mock_assistant, mock_knowledge
):
    orchestrator = _build(temp_db, mock_engine, mock_pc, mock_assistant, mock_knowledge)

    result = orchestrator.process("Remember that my birthday is 12 May")

    assert result.intent == "remember"
    assert result.memory_updated is True
    entry = orchestrator._memory.get("personal", "birthday")
    assert entry is not None and entry.value == "12 May"
    mock_engine.chat.assert_not_called()


def test_recall_with_no_memory_is_honest(
    temp_db, mock_engine, mock_pc, mock_assistant, mock_knowledge
):
    orchestrator = _build(temp_db, mock_engine, mock_pc, mock_assistant, mock_knowledge)

    result = orchestrator.process("What is my name?")

    assert result.intent == "recall"
    assert "don't have" in result.response.lower()


def test_plan_request_returns_numbered_steps(
    temp_db, mock_engine, mock_pc, mock_assistant, mock_knowledge
):
    mock_engine.chat.return_value = EngineResult(
        ok=True,
        text="1. Create the input function\n2. Add the operations\n3. Test the calculator",
    )
    orchestrator = _build(temp_db, mock_engine, mock_pc, mock_assistant, mock_knowledge)

    result = orchestrator.process("Plan 3 steps to build a simple Python calculator.")

    assert result.intent == "plan"
    assert "1." in result.response
    assert "3." in result.response
    assert "Test the calculator" in result.response


def test_short_open_command_executes(
    temp_db, mock_engine, mock_pc, mock_assistant, mock_knowledge
):
    confirmations = []
    orchestrator = _build(
        temp_db,
        mock_engine,
        mock_pc,
        mock_assistant,
        mock_knowledge,
        confirm=lambda message: confirmations.append(message) or True,
    )

    result = orchestrator.process("open notepad")

    assert result.intent == "open_app"
    assert len(confirmations) == 1
    mock_pc.open_app.assert_called_once_with("notepad", confirm=False)
    mock_engine.chat.assert_not_called()


def test_tanglish_open_command_extracts_app(
    temp_db, mock_engine, mock_pc, mock_assistant, mock_knowledge
):
    orchestrator = _build(temp_db, mock_engine, mock_pc, mock_assistant, mock_knowledge)

    result = orchestrator.process("notepad open pannu")

    assert result.intent == "open_app"
    mock_pc.open_app.assert_called_once_with("notepad", confirm=False)
    assert "notepad" in result.response.lower()
    assert "open" in result.response.lower()


def test_create_folder_command(
    temp_db, mock_engine, mock_pc, mock_assistant, mock_knowledge
):
    orchestrator = _build(temp_db, mock_engine, mock_pc, mock_assistant, mock_knowledge)

    result = orchestrator.process("create folder test_folder")

    assert result.intent == "create_folder"
    mock_pc.create_folder.assert_called_once()
    assert mock_pc.create_folder.call_args.args[0] == "test_folder"


def test_clean_response_removes_latex():
    cleaned = Orchestrator._clean_response("Answer: $17 \\times 24 = 408$")

    assert "$" not in cleaned
    assert "\\times" not in cleaned
    assert "17 × 24 = 408" in cleaned


def test_clear_history_keeps_memory(
    temp_db, mock_engine, mock_pc, mock_assistant, mock_knowledge
):
    orchestrator = _build(temp_db, mock_engine, mock_pc, mock_assistant, mock_knowledge)
    orchestrator.process("En peru Deva.")

    orchestrator.clear_history()

    entry = orchestrator._memory.get("personal", "name")
    assert entry is not None and entry.value == "Deva"


def test_greeting_is_short_and_deterministic(
    temp_db, mock_engine, mock_pc, mock_assistant, mock_knowledge
):
    orchestrator = _build(temp_db, mock_engine, mock_pc, mock_assistant, mock_knowledge)

    result = orchestrator.process("hii")

    assert result.intent == "greeting"
    assert result.response == "Hi! 😊 How are you? What can I help you with?"
    mock_engine.chat.assert_not_called()


def test_favourite_language_is_saved(
    temp_db, mock_engine, mock_pc, mock_assistant, mock_knowledge
):
    orchestrator = _build(temp_db, mock_engine, mock_pc, mock_assistant, mock_knowledge)

    result = orchestrator.process("Remember this: my favourite language is Python.")

    assert result.intent == "remember"
    assert result.memory_updated is True
    entry = orchestrator._memory.get("personal", "language")
    assert entry is not None and entry.value == "Python"
    assert "I'll remember that." in result.response
