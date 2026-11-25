"""Tests for memory store."""

import pytest


def test_memory_crud(memory_store):
    """Test basic CRUD operations."""
    # Add
    entry = memory_store.add("personal", "name", "Test User")
    assert entry.category == "personal"
    assert entry.key == "name"
    assert entry.value == "Test User"

    # Get
    retrieved = memory_store.get("personal", "name")
    assert retrieved is not None
    assert retrieved.value == "Test User"

    # Update
    updated = memory_store.update("personal", "name", "Updated User")
    assert updated.value == "Updated User"

    # List
    entries = memory_store.list("personal")
    assert len(entries) == 1
    assert entries[0].value == "Updated User"

    # Delete
    assert memory_store.delete("personal", "name") is True
    assert memory_store.get("personal", "name") is None


def test_memory_categories(memory_store):
    """Test all four categories."""
    for cat in ("personal", "conversation", "project", "knowledge"):
        memory_store.add(cat, f"key_{cat}", f"value_{cat}")

    stats = memory_store.stats()
    assert stats["total"] == 4
    for cat in ("personal", "conversation", "project", "knowledge"):
        assert stats["by_category"][cat] == 1


def test_memory_search(memory_store):
    """Test FTS5 search and LIKE fallback."""
    memory_store.add("knowledge", "python", "Python is a programming language")
    memory_store.add("knowledge", "javascript", "JavaScript is a scripting language")
    memory_store.add("project", "task1", "Build a Python app")

    # FTS search
    results = memory_store.search("Python")
    assert len(results) >= 1
    assert any("Python" in r.value for r in results)

    # Category filter
    results = memory_store.search("Python", category="knowledge")
    assert len(results) >= 1
    assert all(r.category == "knowledge" for r in results)


def test_memory_secret_guard(memory_store):
    """Test secret detection and blocking."""
    # Should reject obvious secrets
    with pytest.raises(Exception, match="secret"):
        memory_store.add("personal", "api_key", "sk-1234567890abcdef1234567890abcdef")

    with pytest.raises(Exception, match="secret"):
        memory_store.add("personal", "password", "mysecretpassword123")

    # Should allow with allow_secret=True
    entry = memory_store.add("personal", "token", "Bearer abc123", allow_secret=True)
    assert entry.value == "Bearer abc123"


def test_memory_invalid_category(memory_store):
    """Test invalid category rejection."""
    with pytest.raises(Exception, match="Invalid category"):
        memory_store.add("invalid", "key", "value")


def test_memory_invalid_sensitivity(memory_store):
    """Test invalid sensitivity rejection."""
    with pytest.raises(Exception, match="Invalid sensitivity"):
        memory_store.add("personal", "key", "value", sensitivity="extreme")


def test_memory_stats(memory_store):
    """Test stats method."""
    stats = memory_store.stats()
    assert "total" in stats
    assert "by_category" in stats
    assert "db_path" in stats
    assert all(cat in stats["by_category"] for cat in ("personal", "conversation", "project", "knowledge"))


def test_memory_override_env(temp_db):
    """Test MAYA_INTEL_DB environment variable override."""
    from maya_intelligence.memory import MemoryStore

    # Store should use the temp_db from env
    store = MemoryStore()
    assert str(store._db_path) == str(temp_db)
    store.close()