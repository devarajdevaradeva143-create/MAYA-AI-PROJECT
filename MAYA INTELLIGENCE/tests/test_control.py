"""Tests for new screen/system control intents."""


def test_screenshot_intent(mock_engine, mock_pc, mock_assistant, mock_knowledge):
    from maya_intelligence.orchestrator import Orchestrator

    mock_pc.open_app.return_value = {"success": True, "result": "Opened", "verified": True}
    mock_engine.chat.return_value.text = "Done"

    orchestrator = Orchestrator(confirm_fn=lambda m: True, max_tokens=512)
    orchestrator._engine = mock_engine
    orchestrator._pc = mock_pc
    orchestrator._assistant = mock_assistant
    orchestrator._knowledge = mock_knowledge
    # screen adapter mock
    from unittest.mock import MagicMock
    sa = MagicMock()
    sa.screenshot.return_value = {"success": True, "path": "C:/tmp/shot.png", "verified": True}
    orchestrator._screen = sa
    orchestrator._system = MagicMock()
    orchestrator._aq._screen = sa
    orchestrator._aq._system = orchestrator._system

    result = orchestrator.process("take a screenshot")
    assert result.intent == "screenshot"


def test_set_volume_intent(mock_engine, mock_pc, mock_assistant, mock_knowledge):
    from maya_intelligence.orchestrator import Orchestrator
    from unittest.mock import MagicMock

    orchestrator = Orchestrator(confirm_fn=lambda m: True, max_tokens=512)
    orchestrator._engine = mock_engine
    orchestrator._pc = mock_pc
    orchestrator._assistant = mock_assistant
    orchestrator._knowledge = mock_knowledge
    sysa = MagicMock()
    sysa.set_volume.return_value = {"success": True, "result": "Volume request: 50", "verified": True}
    orchestrator._system = sysa
    orchestrator._screen = None
    orchestrator._aq._system = sysa
    orchestrator._aq._screen = None

    result = orchestrator.process("set volume to 50")
    assert result.intent == "set_volume"


def test_lock_screen_intent(mock_engine, mock_pc, mock_assistant, mock_knowledge):
    from maya_intelligence.orchestrator import Orchestrator
    from unittest.mock import MagicMock

    orchestrator = Orchestrator(confirm_fn=lambda m: True, max_tokens=512)
    orchestrator._engine = mock_engine
    orchestrator._pc = mock_pc
    orchestrator._assistant = mock_assistant
    orchestrator._knowledge = mock_knowledge
    sysa = MagicMock()
    sysa.lock_workstation.return_value = {"success": True, "result": "locked", "verified": True}
    orchestrator._system = sysa
    orchestrator._screen = None
    orchestrator._aq._system = sysa
    orchestrator._aq._screen = None

    result = orchestrator.process("lock screen")
    assert result.intent == "lock_screen"


def test_shutdown_intent(mock_engine, mock_pc, mock_assistant, mock_knowledge):
    from maya_intelligence.orchestrator import Orchestrator
    from unittest.mock import MagicMock

    orchestrator = Orchestrator(confirm_fn=lambda m: True, max_tokens=512)
    orchestrator._engine = mock_engine
    orchestrator._pc = mock_pc
    orchestrator._assistant = mock_assistant
    orchestrator._knowledge = mock_knowledge
    sysa = MagicMock()
    sysa.shutdown_pc.return_value = {"success": True, "result": "shutdown", "verified": True}
    orchestrator._system = sysa
    orchestrator._screen = None
    orchestrator._aq._system = sysa
    orchestrator._aq._screen = None

    result = orchestrator.process("shutdown pc")
    assert result.intent == "shutdown_pc"


def test_read_clipboard_intent(mock_engine, mock_pc, mock_assistant, mock_knowledge):
    from maya_intelligence.orchestrator import Orchestrator
    from unittest.mock import MagicMock

    orchestrator = Orchestrator(confirm_fn=lambda m: True, max_tokens=512)
    orchestrator._engine = mock_engine
    orchestrator._pc = mock_pc
    orchestrator._assistant = mock_assistant
    orchestrator._knowledge = mock_knowledge
    sysa = MagicMock()
    sysa.read_clipboard.return_value = "hello"
    orchestrator._system = sysa
    orchestrator._screen = None
    orchestrator._aq._system = sysa
    orchestrator._aq._screen = None

    result = orchestrator.process("read clipboard")
    assert result.intent == "read_clipboard"


def test_list_windows_intent(mock_engine, mock_pc, mock_assistant, mock_knowledge):
    from maya_intelligence.orchestrator import Orchestrator
    from unittest.mock import MagicMock

    orchestrator = Orchestrator(confirm_fn=lambda m: True, max_tokens=512)
    orchestrator._engine = mock_engine
    orchestrator._pc = mock_pc
    orchestrator._assistant = mock_assistant
    orchestrator._knowledge = mock_knowledge
    sysa = MagicMock()
    sysa.list_windows.return_value = ["Window1"]
    orchestrator._system = sysa
    orchestrator._screen = None
    orchestrator._aq._system = sysa
    orchestrator._aq._screen = None

    result = orchestrator.process("list windows")
    assert result.intent == "list_windows"


def test_kill_process_intent(mock_engine, mock_pc, mock_assistant, mock_knowledge):
    from maya_intelligence.orchestrator import Orchestrator
    from unittest.mock import MagicMock

    orchestrator = Orchestrator(confirm_fn=lambda m: True, max_tokens=512)
    orchestrator._engine = mock_engine
    orchestrator._pc = mock_pc
    orchestrator._assistant = mock_assistant
    orchestrator._knowledge = mock_knowledge
    sysa = MagicMock()
    sysa.kill_process.return_value = {"success": True, "result": "killed", "verified": True}
    orchestrator._system = sysa
    orchestrator._screen = None
    orchestrator._aq._system = sysa
    orchestrator._aq._screen = None

    result = orchestrator.process("kill process notepad")
    assert result.intent == "kill_process"


def test_keyboard_type_intent(mock_engine, mock_pc, mock_assistant, mock_knowledge):
    from maya_intelligence.orchestrator import Orchestrator
    from unittest.mock import MagicMock

    orchestrator = Orchestrator(confirm_fn=lambda m: True, max_tokens=512)
    orchestrator._engine = mock_engine
    orchestrator._pc = mock_pc
    orchestrator._assistant = mock_assistant
    orchestrator._knowledge = mock_knowledge
    sa = MagicMock()
    sa.keyboard_type.return_value = {"success": True, "result": "typed", "verified": True}
    orchestrator._screen = sa
    orchestrator._system = None
    orchestrator._aq._screen = sa
    orchestrator._aq._system = None

    result = orchestrator.process("type text hello")
    assert result.intent == "keyboard_type"
