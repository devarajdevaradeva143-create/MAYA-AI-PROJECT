"""Test configuration for MAYA INTELLIGENCE."""

import os
import sys
import tempfile
from pathlib import Path

import pytest

# Add JARVIS to sys.path so `import custom` works
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
JARVIS_ROOT = PROJECT_ROOT / "JARVIS"
if str(JARVIS_ROOT) not in sys.path:
    sys.path.insert(0, str(JARVIS_ROOT))

# Also add MAYA INTELLIGENCE root
MAYA_INTEL_ROOT = PROJECT_ROOT / "MAYA INTELLIGENCE"
if str(MAYA_INTEL_ROOT) not in sys.path:
    sys.path.insert(0, str(MAYA_INTEL_ROOT))


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    os.environ["MAYA_INTEL_DB"] = str(db_path)
    yield db_path
    # Cleanup
    if db_path.exists():
        db_path.unlink()
    os.environ.pop("MAYA_INTEL_DB", None)


@pytest.fixture
def memory_store(temp_db):
    """Create a MemoryStore with temp database."""
    from maya_intelligence.memory import MemoryStore
    store = MemoryStore(temp_db)
    yield store
    store.close()


@pytest.fixture
def mock_engine():
    """Mock engine adapter for testing."""
    from unittest.mock import MagicMock
    from maya_intelligence.adapters.engine import EngineAdapter, EngineResult

    mock = MagicMock(spec=EngineAdapter)
    mock.chat.return_value = EngineResult(ok=True, text="Mock response")
    mock.health.return_value = EngineResult(ok=True, text="pong")
    mock.close.return_value = None
    return mock


@pytest.fixture
def mock_knowledge():
    """Mock knowledge adapter for testing."""
    from unittest.mock import MagicMock
    mock = MagicMock()
    mock.knowledge_search.return_value = []
    mock.search_files.return_value = []
    return mock


@pytest.fixture
def mock_pc():
    """Mock PC adapter for testing."""
    from unittest.mock import MagicMock
    mock = MagicMock()
    mock.open_app.return_value = {"success": True, "result": "Opened", "verified": True}
    mock.close_app.return_value = {"success": True, "result": "Closed", "verified": True}
    mock.is_app_running.return_value = True
    mock.list_apps.return_value = ["notepad", "calc"]
    mock.read_file.return_value = {"success": True, "content": "test content"}
    mock.edit_file.return_value = {"success": True, "result": "Edited", "verified": True}
    mock.delete_file.return_value = {"success": True, "result": "Deleted", "verified": True}
    mock.create_folder.return_value = {"success": True, "result": "Created", "verified": True}
    mock.run_command.return_value = {"success": True, "result": "OK", "verified": True}
    return mock


@pytest.fixture
def mock_assistant():
    """Mock assistant adapter for testing."""
    from unittest.mock import MagicMock
    mock = MagicMock()
    mock.set_reminder.return_value = {"success": True, "result": "Set", "verified": True}
    mock.list_reminders.return_value = []
    mock.add_todo.return_value = {"success": True, "result": "Added", "verified": True}
    mock.list_todos.return_value = []
    mock.complete_todo.return_value = {"success": True, "result": "Completed", "verified": True}
    mock.set_schedule_item.return_value = {"success": True, "result": "Set", "verified": True}
    mock.get_daily_schedule.return_value = []
    return mock