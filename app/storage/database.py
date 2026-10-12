"""SQLite database: connection setup, schema migrations, corruption handling.

Threading rule: every storage call runs on the Qt UI thread (the queries are tiny).
Worker threads never touch the database; they hand results to the UI thread through
signals and the UI thread saves them. Connections keep sqlite3's default
``check_same_thread=True``, so a call from another thread fails loudly.

Safety rules:
- A database written by a newer app version raises StorageError and is not modified.
- An unreadable or corrupt file is renamed to ``<name>.corrupt-<timestamp>`` (never
  deleted) and DatabaseCorruptError carries the backup path, so the UI can offer a
  fresh database.
- Each migration runs inside its own transaction and is recorded in ``schema_version``.
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.backend.chat_store import utc_now
from app.errors import StorageError

logger = logging.getLogger(__name__)

BUSY_TIMEOUT_MS = 5000

SCHEMA_V1 = """
CREATE TABLE conversations (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    model_name  TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE TABLE messages (
    id              INTEGER PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    seq             INTEGER NOT NULL,
    role            TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content         TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'complete' CHECK (status IN ('complete', 'stopped', 'error')),
    eval_count      INTEGER,
    tokens_per_sec  REAL,
    feedback        TEXT,
    created_at      TEXT NOT NULL,
    UNIQUE (conversation_id, seq)
);
CREATE TABLE projects (
    id              TEXT PRIMARY KEY,
    conversation_id TEXT REFERENCES conversations(id) ON DELETE SET NULL,
    name            TEXT NOT NULL,
    path            TEXT NOT NULL,
    status          TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE TABLE app_settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);
CREATE INDEX idx_messages_conversation_seq ON messages (conversation_id, seq);
CREATE INDEX idx_conversations_updated ON conversations (updated_at DESC);
CREATE INDEX idx_projects_conversation ON projects (conversation_id);
"""

# Ordered (version, SQL). Append new versions; never edit a released one.
MIGRATIONS: list[tuple[int, str]] = [
    (1, SCHEMA_V1),
]

_SCHEMA_VERSION_SQL = (
    "CREATE TABLE IF NOT EXISTS schema_version ("
    "version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
)


class DatabaseCorruptError(StorageError):
    """The database file could not be read. It was renamed to ``backup_path``."""

    default_message = "The chat history database is damaged."

    def __init__(self, message: str | None = None, detail: str | None = None,
                 backup_path: Path | None = None) -> None:
        super().__init__(message, detail)
        self.backup_path = backup_path


@dataclass(frozen=True)
class DatabaseInfo:
    path: Path
    exists: bool
    schema_version: int | None = None
    chat_count: int | None = None
    error: str | None = None


def latest_version(migrations: Sequence[tuple[int, str]] = MIGRATIONS) -> int:
    return max((v for v, _ in migrations), default=0)


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), isolation_level=None)  # explicit BEGIN/COMMIT only
    conn.row_factory = sqlite3.Row
    conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _stored_version(conn: sqlite3.Connection) -> int:
    """Read-only: the highest applied migration, 0 for a new database."""
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_version'"
    ).fetchone()
    if row is None:
        return 0
    value = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
    return int(value or 0)


def _check_integrity(conn: sqlite3.Connection) -> None:
    result = conn.execute("PRAGMA quick_check").fetchone()[0]
    if result != "ok":
        raise sqlite3.DatabaseError(f"quick_check: {result}")


def backup_corrupt_file(path: Path) -> Path:
    """Rename ``path`` (and its -wal/-shm files) to ``<name>.corrupt-<UTC timestamp>``."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup = path.with_name(f"{path.name}.corrupt-{stamp}")
    counter = 2
    while backup.exists():
        backup = path.with_name(f"{path.name}.corrupt-{stamp}-{counter}")
        counter += 1
    path.rename(backup)
    for suffix in ("-wal", "-shm"):
        sidecar = path.with_name(path.name + suffix)
        if sidecar.exists():
            sidecar.rename(backup.with_name(backup.name + suffix))
    return backup


def apply_migrations(conn: sqlite3.Connection, migrations: Sequence[tuple[int, str]] = MIGRATIONS) -> int:
    """Apply missing migrations, one transaction each. Returns the resulting version."""
    current = _stored_version(conn)
    for version, sql in sorted(migrations):
        if version <= current:
            continue
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(_SCHEMA_VERSION_SQL)
            for statement in _split_sql(sql):
                conn.execute(statement)
            conn.execute("INSERT INTO schema_version (version, applied_at) VALUES (?, ?)", (version, utc_now()))
            conn.execute("COMMIT")
        except sqlite3.Error as exc:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise StorageError(
                f"Could not upgrade the chat history database to version {version}.",
                detail=f"{type(exc).__name__}: {exc}",
            ) from None
        logger.info("Database migrated to schema version %d", version)
        current = version
    return current


def _split_sql(sql: str) -> list[str]:
    """Split a migration script into complete statements (no triggers with inner ';')."""
    statements: list[str] = []
    buffer = ""
    for line in sql.splitlines(keepends=True):
        buffer += line
        if sqlite3.complete_statement(buffer):
            if buffer.strip():
                statements.append(buffer.strip())
            buffer = ""
    if buffer.strip():
        statements.append(buffer.strip())
    return statements


def open_database(path: Path, migrations: Sequence[tuple[int, str]] = MIGRATIONS) -> sqlite3.Connection:
    """Open (creating if needed) and migrate the database at ``path``.

    Raises StorageError for a newer schema (file untouched) or DatabaseCorruptError
    (file renamed to a backup) when it cannot be read.
    """
    path = Path(path)
    supported = latest_version(migrations)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise StorageError(f"Cannot create the folder for the database '{path.parent}'.", detail=str(exc)) from exc

    conn: sqlite3.Connection | None = None
    try:
        conn = _connect(path)
        _check_integrity(conn)
        stored = _stored_version(conn)
    except sqlite3.Error as exc:
        if conn is not None:
            conn.close()
        if not path.exists():
            raise StorageError(f"Cannot open the database '{path}'.", detail=f"{type(exc).__name__}: {exc}") from None
        try:
            backup = backup_corrupt_file(path)
        except OSError as move_exc:
            raise StorageError(
                f"The chat history database '{path}' is damaged and could not be moved aside. "
                "Close other programs using it and try again.",
                detail=f"{type(exc).__name__}: {exc}; rename failed: {move_exc}",
            ) from None
        logger.error("Database %s is unreadable (%s); moved to %s", path, exc, backup)
        raise DatabaseCorruptError(
            f"The chat history database could not be read. It was kept as a backup at '{backup}'.",
            detail=f"{type(exc).__name__}: {exc}",
            backup_path=backup,
        ) from None

    if stored > supported:
        conn.close()
        raise StorageError(
            f"The chat history database was created by a newer version of the app "
            f"(schema {stored}, this version supports {supported}). It was not changed.",
            detail=str(path),
        )

    try:
        conn.execute("PRAGMA journal_mode = WAL")
        apply_migrations(conn, migrations)
    except sqlite3.Error as exc:
        conn.close()
        raise StorageError(f"Cannot prepare the database '{path}'.", detail=f"{type(exc).__name__}: {exc}") from None
    except StorageError:
        conn.close()
        raise
    return conn


def inspect_database(path: Path) -> DatabaseInfo:
    """Read-only summary for ``main.py --check``. Never creates or changes the file."""
    path = Path(path)
    if not path.exists():
        return DatabaseInfo(path, exists=False)
    try:
        conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        return DatabaseInfo(path, exists=True, error=f"{type(exc).__name__}: {exc}")
    try:
        version = _stored_version(conn)
        has_chats = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'conversations'"
        ).fetchone()
        count = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0] if has_chats else 0
        return DatabaseInfo(path, exists=True, schema_version=version, chat_count=int(count))
    except sqlite3.Error as exc:
        return DatabaseInfo(path, exists=True, error=f"{type(exc).__name__}: {exc}")
    finally:
        conn.close()
