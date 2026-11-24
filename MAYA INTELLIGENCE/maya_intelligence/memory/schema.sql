-- MAYA INTELLIGENCE Memory Schema
-- SQLite with FTS5 for full-text search

-- Main memories table
CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,           -- 'personal', 'conversation', 'project', 'knowledge'
    key TEXT NOT NULL,                -- user-defined key
    value TEXT NOT NULL,              -- memory content
    sensitivity TEXT DEFAULT 'low',   -- 'low', 'medium', 'high'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(category, key)
);

-- FTS5 virtual table for full-text search
CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
    category, key, value,
    content='memories',
    content_rowid='id'
);

-- Trigger to keep FTS in sync on INSERT
CREATE TRIGGER IF NOT EXISTS memories_fts_insert AFTER INSERT ON memories BEGIN
    INSERT INTO memories_fts(rowid, category, key, value)
    VALUES (new.id, new.category, new.key, new.value);
END;

-- Trigger to keep FTS in sync on UPDATE
CREATE TRIGGER IF NOT EXISTS memories_fts_update AFTER UPDATE ON memories BEGIN
    UPDATE memories_fts SET category=new.category, key=new.key, value=new.value
    WHERE rowid=new.id;
END;

-- Trigger to keep FTS in sync on DELETE
CREATE TRIGGER IF NOT EXISTS memories_fts_delete AFTER DELETE ON memories BEGIN
    DELETE FROM memories_fts WHERE rowid=old.id;
END;

-- Index for category filtering
CREATE INDEX IF NOT EXISTS idx_memories_category ON memories(category);

-- Index for key lookup
CREATE INDEX IF NOT EXISTS idx_memories_key ON memories(key);