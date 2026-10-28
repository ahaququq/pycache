"""SQLite database layer.

We deliberately use SQLite: it is serverless (no separate DB process to
maintain inside a container), file based (so it travels with the data dir),
fast enough for our index/metadata workload, and available in the Python
standard library. All access goes through a single connection per thread
with WAL mode for concurrent readers.
"""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from typing import Iterator

from .config import DB_PATH

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------
SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    kind        TEXT NOT NULL,          -- 'db' | python module name
    config      TEXT NOT NULL DEFAULT '{}',   -- JSON config blob
    enabled     INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS mappings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id   INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    local_path  TEXT NOT NULL,          -- e.g. "gradle/8.5/gradle-8.5-bin.zip"
    remote_url  TEXT NOT NULL,          -- e.g. "https://services.gradle.org/..."
    enabled     INTEGER NOT NULL DEFAULT 1,
    UNIQUE (source_id, local_path)
);

CREATE TABLE IF NOT EXISTS files (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id   INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    local_path  TEXT NOT NULL,
    remote_url  TEXT NOT NULL,
    size        INTEGER,                 -- bytes, NULL if unknown
    cached      INTEGER NOT NULL DEFAULT 0,  -- 1 if file physically present in cache
    cache_path  TEXT,                    -- relative path inside CACHE_DIR
    etag        TEXT,
    last_modified TEXT,
    exists_upstream INTEGER NOT NULL DEFAULT 0,  -- 1 if HEAD probe succeeded
    unavailable INTEGER NOT NULL DEFAULT 0,     -- 1 if file listed but unavailable (404, 403, etc.)
    unavailable_reason TEXT,                  -- error reason (e.g., '404 Not Found', '403 Forbidden')
    last_checked TEXT,
    UNIQUE (source_id, local_path)
);

CREATE TABLE IF NOT EXISTS admin_users (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    pw_hash TEXT NOT NULL,
    pw_salt TEXT NOT NULL,
    created TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_files_source ON files(source_id);
CREATE INDEX IF NOT EXISTS idx_files_path ON files(local_path);
CREATE INDEX IF NOT EXISTS idx_mappings_source ON mappings(source_id);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS log_entries (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT NOT NULL DEFAULT (datetime('now')),
    level       TEXT NOT NULL,          -- DEBUG, INFO, WARNING, ERROR, CRITICAL
    module      TEXT NOT NULL,          -- source module name
    message     TEXT NOT NULL,
    details     TEXT                    -- optional JSON with extra context
);

CREATE INDEX IF NOT EXISTS idx_log_timestamp ON log_entries(timestamp);
CREATE INDEX IF NOT EXISTS idx_log_level ON log_entries(level);
CREATE INDEX IF NOT EXISTS idx_log_module ON log_entries(module);
"""


class Database:
    """Thread-local SQLite connection wrapper."""

    def __init__(self, path: str | None = None) -> None:
        self.path = str(path or DB_PATH)
        self._local = threading.local()

    # -- connection management ------------------------------------------------
    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.path, check_same_thread=False)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        return conn

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        conn = self._conn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        return self._conn().execute(sql, params)

    def executemany(self, sql: str, params: list) -> sqlite3.Cursor:
        return self._conn().executemany(sql, params)

    def fetchone(self, sql: str, params: tuple = ()) -> sqlite3.Row | None:
        return self._conn().execute(sql, params).fetchone()

    def fetchall(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        return self._conn().execute(sql, params).fetchall()

    def init(self) -> None:
        """Create schema and default admin row if missing."""
        self._conn().executescript(SCHEMA)
        self._conn().commit()


# Singleton used across the app.
db = Database()


def get_db() -> Database:
    return db