"""SQLite connection management, DDL, and initialization for RecallBench.

Uses standard-library sqlite3 with WAL mode, parameterized statements,
and strict resource cleanup.
"""
import sqlite3
from typing import Optional


CREATE_FACTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS facts (
    id TEXT PRIMARY KEY,
    entity_id TEXT NOT NULL,
    attribute TEXT NOT NULL,
    value_json TEXT NOT NULL,
    valid_from TEXT NOT NULL,
    valid_to TEXT,
    asserted_at TEXT NOT NULL,
    retracted_at TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    superseded_by TEXT,
    is_deleted INTEGER NOT NULL DEFAULT 0,
    deleted_at TEXT,
    deletion_scope TEXT,
    confidence REAL NOT NULL DEFAULT 1.0,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_facts_entity_attr
ON facts(entity_id, attribute);

CREATE INDEX IF NOT EXISTS idx_facts_validity
ON facts(entity_id, attribute, valid_from, valid_to);

CREATE INDEX IF NOT EXISTS idx_facts_bitemporal
ON facts(entity_id, attribute, asserted_at, retracted_at);
"""


def init_db(conn: sqlite3.Connection) -> None:
    """Initialize database schemas, pragmas, and indexes."""
    # Pragmas for concurrency, integrity, and performance
    # Note: journal_mode=WAL is applied for file-backed DBs (ignored or in-memory safe)
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
    except sqlite3.OperationalError:
        pass
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.executescript(CREATE_FACTS_TABLE_SQL)
    conn.commit()


def get_connection(db_path: str = ":memory:", timeout: float = 10.0) -> sqlite3.Connection:
    """Create a configured SQLite connection with row factory."""
    conn = sqlite3.connect(
        db_path,
        timeout=timeout,
        detect_types=sqlite3.PARSE_DECLTYPES,
        check_same_thread=False,
    )
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn
