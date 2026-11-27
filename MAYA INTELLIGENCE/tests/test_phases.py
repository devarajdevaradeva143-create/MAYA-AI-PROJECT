"""Tests for phases 4-7 (browser, files, office, agent)."""


def _setup(orchestrator, mock_engine, mock_pc, mock_assistant, mock_knowledge):
    orchestrator._engine = mock_engine
    orchestrator._pc = mock_pc
    orchestrator._assistant = mock_assistant
    orchestrator._knowledge = mock_knowledge
    from unittest.mock import MagicMock
    orchestrator._screen = None
    orchestrator._system = None
    orchestrator._browser = MagicMock()
    orchestrator._files = MagicMock()
    orchestrator._office = MagicMock()
    orchestrator._aq._screen = None
    orchestrator._aq._system = None
    orchestrator._aq._browser = orchestrator._browser
    orchestrator._aq._files = orchestrator._files
    orchestrator._aq._office = orchestrator._office
    return orchestrator


def test_open_url_intent(mock_engine, mock_pc, mock_assistant, mock_knowledge):
    from maya_intelligence.orchestrator import Orchestrator
    o = _setup(Orchestrator(confirm_fn=lambda m: True, max_tokens=512),
               mock_engine, mock_pc, mock_assistant, mock_knowledge)
    o._browser.open_url.return_value = {"success": True, "result": "Opened", "verified": True}
    r = o.process("open url example.com")
    assert r.intent == "open_url"


def test_fetch_page_intent(mock_engine, mock_pc, mock_assistant, mock_knowledge):
    from maya_intelligence.orchestrator import Orchestrator
    o = _setup(Orchestrator(confirm_fn=lambda m: True, max_tokens=512),
               mock_engine, mock_pc, mock_assistant, mock_knowledge)
    o._browser.fetch_page.return_value = {"success": True, "content": "hi", "verified": True}
    r = o.process("fetch page example.com")
    assert r.intent == "fetch_page"


def test_move_file_intent(mock_engine, mock_pc, mock_assistant, mock_knowledge):
    from maya_intelligence.orchestrator import Orchestrator
    o = _setup(Orchestrator(confirm_fn=lambda m: True, max_tokens=512),
               mock_engine, mock_pc, mock_assistant, mock_knowledge)
    o._files.move_file.return_value = {"success": True, "result": "Moved", "verified": True}
    r = o.process("move file a.txt to b.txt")
    assert r.intent == "move_file"


def test_zip_intent(mock_engine, mock_pc, mock_assistant, mock_knowledge):
    from maya_intelligence.orchestrator import Orchestrator
    o = _setup(Orchestrator(confirm_fn=lambda m: True, max_tokens=512),
               mock_engine, mock_pc, mock_assistant, mock_knowledge)
    o._files.zip_path.return_value = {"success": True, "result": "Zipped", "verified": True}
    r = o.process("zip file folder")
    assert r.intent == "zip_path"


def test_excel_write_intent(mock_engine, mock_pc, mock_assistant, mock_knowledge):
    from maya_intelligence.orchestrator import Orchestrator
    o = _setup(Orchestrator(confirm_fn=lambda m: True, max_tokens=512),
               mock_engine, mock_pc, mock_assistant, mock_knowledge)
    o._office.excel_write.return_value = {"success": True, "result": "ok", "verified": True}
    r = o.process("excel write file.xlsx A1 hello")
    assert r.intent == "excel_write"


def test_word_create_intent(mock_engine, mock_pc, mock_assistant, mock_knowledge):
    from maya_intelligence.orchestrator import Orchestrator
    o = _setup(Orchestrator(confirm_fn=lambda m: True, max_tokens=512),
               mock_engine, mock_pc, mock_assistant, mock_knowledge)
    o._office.word_create_doc.return_value = {"success": True, "result": "ok", "verified": True}
    r = o.process("word create doc.docx hello")
    assert r.intent == "word_create_doc"


def test_agent_intent(mock_engine, mock_pc, mock_assistant, mock_knowledge):
    from maya_intelligence.orchestrator import Orchestrator
    o = _setup(Orchestrator(confirm_fn=lambda m: True, max_tokens=512),
               mock_engine, mock_pc, mock_assistant, mock_knowledge)
    # mock plan_actions to return one action
    o._iq.plan_actions = lambda goal, context="", language_directive="": [
        {"intent": "open_app", "params": {"name": "notepad"}, "description": "open notepad"}
    ]
    o._pc.open_app.return_value = {"success": True, "result": "Opened", "verified": True}
    r = o.process("open notepad and type hello")
    assert r.intent == "agent"


def test_agent_fallback_text_plan(mock_engine, mock_pc, mock_assistant, mock_knowledge):
    from maya_intelligence.orchestrator import Orchestrator
    o = _setup(Orchestrator(confirm_fn=lambda m: True, max_tokens=512),
               mock_engine, mock_pc, mock_assistant, mock_knowledge)
    o._iq.plan_actions = lambda goal, context="", language_directive="": []
    mock_engine.chat.return_value.text = "1. Step one\n2. Step two"
    r = o.process("agent do something complex")
    assert r.intent == "agent"
    assert "Step one" in r.response
