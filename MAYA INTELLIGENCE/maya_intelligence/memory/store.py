"""Memory store — SQLite with FTS5, 4 categories, secret-guard, MAYA_INTEL_DB override."""

import os
import re
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class MayaIntelError(Exception):
    """Base exception for MAYA INTELLIGENCE memory."""


@dataclass
class MemoryEntry:
    id: int
    category: str
    key: str
    value: str
    sensitivity: str
    created_at: str
    updated_at: str


VALID_CATEGORIES = ("personal", "conversation", "project", "knowledge")
SENSITIVITY_LEVELS = ("low", "medium", "high")

# Patterns that look like secrets
SECRET_PATTERNS = [
    re.compile(r"(?i)(password|secret|token|key|api_key|apikey)\s*[:=]\s*\S+"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9\-_.]+"),
    re.compile(r"sk-[A-Za-z0-9]{16,}"),  # OpenAI-style keys (16+ chars after sk-)
    re.compile(r"sk_[A-Za-z0-9]{16,}"),  # OpenAI-style with underscore
    re.compile(r"[A-Za-z0-9]{16,}"),     # Generic long tokens (16+ consecutive alphanumeric)
]


def _get_db_path() -> Path:
    """Resolve DB path from MAYA_INTEL_DB env or default."""
    env_path = os.environ.get("MAYA_INTEL_DB")
    if env_path:
        return Path(env_path).expanduser().resolve()
    # Default: <PROJECT_ROOT>/MAYA AI/memory/offline/maya_intelligence.db
    project_root = Path(__file__).parent.parent.parent.parent
    return project_root / "MAYA AI" / "memory" / "offline" / "maya_intelligence.db"


def _ensure_db_dir(db_path: Path):
    """Create parent directory if needed."""
    db_path.parent.mkdir(parents=True, exist_ok=True)


def _contains_secret(text: str) -> bool:
    """Check if text contains obvious secrets."""
    for pattern in SECRET_PATTERNS:
        if pattern.search(text):
            return True
    return False


class MemoryStore:
    """SQLite memory store with FTS5 search."""

    def __init__(self, db_path: Path = None):
        self._db_path = db_path or _get_db_path()
        _ensure_db_dir(self._db_path)
        self._init_db()

    def _init_db(self):
        """Initialize database schema."""
        with self._conn() as conn:
            schema_path = Path(__file__).parent / "schema.sql"
            if schema_path.exists():
                conn.executescript(schema_path.read_text(encoding="utf-8"))
            else:
                # Fallback inline schema
                conn.executescript("""
                    CREATE TABLE IF NOT EXISTS memories (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        category TEXT NOT NULL,
                        key TEXT NOT NULL,
                        value TEXT NOT NULL,
                        sensitivity TEXT DEFAULT 'low',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(category, key)
                    );
                    CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
                        category, key, value, content='memories', content_rowid='id'
                    );
                    CREATE TRIGGER IF NOT EXISTS memories_fts_insert AFTER INSERT ON memories BEGIN
                        INSERT INTO memories_fts(rowid, category, key, value)
                        VALUES (new.id, new.category, new.key, new.value);
                    END;
                    CREATE TRIGGER IF NOT EXISTS memories_fts_update AFTER UPDATE ON memories BEGIN
                        UPDATE memories_fts SET category=new.category, key=new.key, value=new.value
                        WHERE rowid=new.id;
                    END;
                    CREATE TRIGGER IF NOT EXISTS memories_fts_delete AFTER DELETE ON memories BEGIN
                        DELETE FROM memories_fts WHERE rowid=old.id;
                    END;
                    CREATE INDEX IF NOT EXISTS idx_memories_category ON memories(category);
                    CREATE INDEX IF NOT EXISTS idx_memories_key ON memories(key);
                """)

    @contextmanager
    def _conn(self):
        """Context manager for database connection."""
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _row_to_entry(self, row: sqlite3.Row) -> MemoryEntry:
        return MemoryEntry(
            id=row["id"],
            category=row["category"],
            key=row["key"],
            value=row["value"],
            sensitivity=row["sensitivity"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def add(
        self,
        category: str,
        key: str,
        value: str,
        sensitivity: str = "low",
        allow_secret: bool = False,
    ) -> MemoryEntry:
        """Add or update a memory entry."""
        if category not in VALID_CATEGORIES:
            raise MayaIntelError(f"Invalid category: {category}. Must be one of {VALID_CATEGORIES}")
        if sensitivity not in SENSITIVITY_LEVELS:
            raise MayaIntelError(f"Invalid sensitivity: {sensitivity}. Must be one of {SENSITIVITY_LEVELS}")
        if not allow_secret and _contains_secret(value):
            raise MayaIntelError("Value appears to contain a secret (password, token, key, etc.). Use allow_secret=True to override.")

        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO memories (category, key, value, sensitivity)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(category, key) DO UPDATE SET
                    value=excluded.value,
                    sensitivity=excluded.sensitivity,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (category, key, value, sensitivity),
            )
            # Always query for the row after insert/update
            row = conn.execute("SELECT * FROM memories WHERE category=? AND key=?", (category, key)).fetchone()
            if row:
                return self._row_to_entry(row)
            raise MayaIntelError(f"Failed to retrieve memory after insert: {category}/{key}")

    def get(self, category: str, key: str) -> MemoryEntry | None:
        """Get a memory entry by category and key."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM memories WHERE category=? AND key=?", (category, key)
            ).fetchone()
            return self._row_to_entry(row) if row else None

    def search(self, query: str, category: str = None, limit: int = 20) -> list[MemoryEntry]:
        """Search memories using FTS5 (falls back to LIKE on any error)."""
        # Try FTS5 first, fall back to LIKE on any error
        like_query = f"%{query}%"
        with self._conn() as conn:
            # Try FTS5
            try:
                fts_query = query.replace('"', '""')
                if category:
                    sql = """
                        SELECT m.* FROM memories m
                        JOIN memories_fts f ON m.id = f.rowid
                        WHERE memories_fts MATCH ? AND m.category = ?
                        ORDER BY rank LIMIT ?
                    """
                    rows = conn.execute(sql, (fts_query, category, limit)).fetchall()
                else:
                    sql = """
                        SELECT m.* FROM memories m
                        JOIN memories_fts f ON m.id = f.rowid
                        WHERE memories_fts MATCH ?
                        ORDER BY rank LIMIT ?
                    """
                    rows = conn.execute(sql, (fts_query, limit)).fetchall()
            except Exception:
                rows = []

            # Fallback to LIKE if FTS returns nothing or errors
            if not rows:
                if category:
                    rows = conn.execute(
                        "SELECT * FROM memories WHERE category=? AND (key LIKE ? OR value LIKE ?) LIMIT ?",
                        (category, like_query, like_query, limit),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT * FROM memories WHERE key LIKE ? OR value LIKE ? LIMIT ?",
                        (like_query, like_query, limit),
                    ).fetchall()

            return [self._row_to_entry(r) for r in rows]

    def update(
        self,
        category: str,
        key: str,
        value: str = None,
        sensitivity: str = None,
        allow_secret: bool = False,
    ) -> MemoryEntry:
        """Update a memory entry."""
        entry = self.get(category, key)
        if not entry:
            raise MayaIntelError(f"Memory not found: {category}/{key}")

        new_value = value if value is not None else entry.value
        new_sensitivity = sensitivity if sensitivity is not None else entry.sensitivity

        if not allow_secret and _contains_secret(new_value):
            raise MayaIntelError("Value appears to contain a secret. Use allow_secret=True to override.")

        with self._conn() as conn:
            conn.execute(
                "UPDATE memories SET value=?, sensitivity=?, updated_at=CURRENT_TIMESTAMP WHERE category=? AND key=?",
                (new_value, new_sensitivity, category, key),
            )
        return self.get(category, key)

    def delete(self, category: str, key: str) -> bool:
        """Delete a memory entry."""
        with self._conn() as conn:
            cursor = conn.execute(
                "DELETE FROM memories WHERE category=? AND key=?", (category, key)
            )
            return cursor.rowcount > 0

    def list(self, category: str = None, limit: int = 100) -> list[MemoryEntry]:
        """List memories, optionally filtered by category."""
        with self._conn() as conn:
            if category:
                rows = conn.execute(
                    "SELECT * FROM memories WHERE category=? ORDER BY updated_at DESC LIMIT ?",
                    (category, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM memories ORDER BY updated_at DESC LIMIT ?", (limit,)
                ).fetchall()
            return [self._row_to_entry(r) for r in rows]

    def stats(self) -> dict[str, Any]:
        """Get memory statistics."""
        with self._conn() as conn:
            total = conn.execute("SELECT COUNT(*) as c FROM memories").fetchone()["c"]
            by_category = {}
            for cat in VALID_CATEGORIES:
                count = conn.execute(
                    "SELECT COUNT(*) as c FROM memories WHERE category=?", (cat,)
                ).fetchone()["c"]
                by_category[cat] = count
            return {"total": total, "by_category": by_category, "db_path": str(self._db_path)}

    def close(self):
        """No-op for compatibility."""
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()