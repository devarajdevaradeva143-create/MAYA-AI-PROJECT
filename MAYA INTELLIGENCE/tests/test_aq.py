"""Tests for AQ engine."""

import pytest


def test_aq_open_app(mock_pc, mock_assistant, mock_knowledge):
    """Test AQ open app action."""
    from maya_intelligence.engines import AQEngine

    confirm_called = []

    def confirm_fn(msg):
        confirm_called.append(msg)
        return True

    aq = AQEngine(mock_pc, mock_assistant, mock_knowledge, confirm_fn=confirm_fn)
    result = aq.execute("open_app", {"name": "notepad"})

    assert result.success is True
    assert result.verified is True
    assert len(confirm_called) == 1
    mock_pc.open_app.assert_called_once_with("notepad", confirm=False)


def test_aq_open_app_cancelled(mock_pc, mock_assistant, mock_knowledge):
    """Test AQ open app cancelled by user."""
    from maya_intelligence.engines import AQEngine

    def confirm_fn(msg):
        return False

    aq = AQEngine(mock_pc, mock_assistant, mock_knowledge, confirm_fn=confirm_fn)
    result = aq.execute("open_app", {"name": "notepad"})

    assert result.success is False
    assert result.verified is False
    assert "Cancelled" in result.message


def test_aq_close_app(mock_pc, mock_assistant, mock_knowledge):
    """Test AQ close app action."""
    from maya_intelligence.engines import AQEngine

    aq = AQEngine(mock_pc, mock_assistant, mock_knowledge, confirm_fn=lambda m: True)
    result = aq.execute("close_app", {"name": "notepad"})

    assert result.success is True
    assert result.verified is True
    mock_pc.close_app.assert_called_once_with("notepad", confirm=False)


def test_aq_search_files(mock_pc, mock_assistant, mock_knowledge):
    """Test AQ search files action."""
    from maya_intelligence.engines import AQEngine

    mock_knowledge.search_files.return_value = [{"path": "test.txt", "content": "hello"}]

    aq = AQEngine(mock_pc, mock_assistant, mock_knowledge, confirm_fn=lambda m: True)
    result = aq.execute("search_files", {"query": "test"})

    assert result.success is True
    assert result.verified is True
    assert len(result.result) == 1
    mock_knowledge.search_files.assert_called_once()


def test_aq_create_folder(mock_pc, mock_assistant, mock_knowledge):
    """Test AQ create folder action."""
    from maya_intelligence.engines import AQEngine

    aq = AQEngine(mock_pc, mock_assistant, mock_knowledge, confirm_fn=lambda m: True)
    result = aq.execute("create_folder", {"path": "/home/user/newfolder"})

    assert result.success is True
    assert result.verified is True
    mock_pc.create_folder.assert_called_once_with("/home/user/newfolder", confirm=False)


def test_aq_delete_file(mock_pc, mock_assistant, mock_knowledge):
    """Test AQ delete file action."""
    from maya_intelligence.engines import AQEngine

    aq = AQEngine(mock_pc, mock_assistant, mock_knowledge, confirm_fn=lambda m: True)
    result = aq.execute("delete_file", {"path": "/home/user/test.txt"})

    assert result.success is True
    assert result.verified is True
    mock_pc.delete_file.assert_called_once_with("/home/user/test.txt", confirm=False)


def test_aq_todo_add(mock_pc, mock_assistant, mock_knowledge):
    """Test AQ todo add action."""
    from maya_intelligence.engines import AQEngine

    aq = AQEngine(mock_pc, mock_assistant, mock_knowledge, confirm_fn=lambda m: True)
    result = aq.execute("todo", {"action": "add", "text": "Buy milk"})

    assert result.success is True
    assert result.verified is True
    mock_assistant.add_todo.assert_called_once_with("Buy milk")


def test_aq_todo_list(mock_pc, mock_assistant, mock_knowledge):
    """Test AQ todo list action."""
    from maya_intelligence.engines import AQEngine

    mock_assistant.list_todos.return_value = ["Task 1", "Task 2"]

    aq = AQEngine(mock_pc, mock_assistant, mock_knowledge, confirm_fn=lambda m: True)
    result = aq.execute("todo", {"action": "list"})

    assert result.success is True
    assert result.verified is True
    assert len(result.result) == 2


def test_aq_reminder_add(mock_pc, mock_assistant, mock_knowledge):
    """Test AQ reminder add action."""
    from maya_intelligence.engines import AQEngine

    aq = AQEngine(mock_pc, mock_assistant, mock_knowledge, confirm_fn=lambda m: True)
    result = aq.execute("reminder", {"action": "add", "text": "Meeting", "when": "tomorrow"})

    assert result.success is True
    assert result.verified is True
    mock_assistant.set_reminder.assert_called_once_with("Meeting", "tomorrow")


def test_aq_unknown_intent(mock_pc, mock_assistant, mock_knowledge):
    """Test AQ unknown intent."""
    from maya_intelligence.engines import AQEngine

    aq = AQEngine(mock_pc, mock_assistant, mock_knowledge, confirm_fn=lambda m: True)
    result = aq.execute("unknown_intent", {})

    assert result.success is False
    assert "Unknown action" in result.message


def test_aq_missing_params(mock_pc, mock_assistant, mock_knowledge):
    """Test AQ with missing required parameters."""
    from maya_intelligence.engines import AQEngine

    aq = AQEngine(mock_pc, mock_assistant, mock_knowledge, confirm_fn=lambda m: True)

    # open_app without name
    result = aq.execute("open_app", {})
    assert result.success is False
    assert "required" in result.message.lower()

    # search_files without query
    result = aq.execute("search_files", {})
    assert result.success is False
    assert "required" in result.message.lower()