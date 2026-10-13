"""SqliteChatRepository: the ChatStore backed by the local SQLite database.

Call it from the UI thread only (see app.storage.database). Every write runs in one
transaction; on any failure it rolls back and raises StorageError.
"""

from __future__ import annotations

import logging
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

from app.backend.chat_store import (
    DEFAULT_TITLE,
    ChatMessage,
    Conversation,
    ProjectRecord,
    check_feedback,
    check_project_status,
    check_message,
    clean_title,
    title_from_prompt,
    utc_now,
)
from app.errors import StorageError
from app.storage.database import MIGRATIONS, open_database

logger = logging.getLogger(__name__)


def _conversation(row: sqlite3.Row) -> Conversation:
    return Conversation(row["id"], row["title"], row["model_name"], row["created_at"], row["updated_at"])


def _project(row: sqlite3.Row) -> ProjectRecord:
    return ProjectRecord(row["id"], row["conversation_id"], row["name"], row["path"], row["status"],
                         row["created_at"], row["updated_at"])


def _message(row: sqlite3.Row) -> ChatMessage:
    return ChatMessage(
        role=row["role"], content=row["content"], status=row["status"], eval_count=row["eval_count"],
        tokens_per_sec=row["tokens_per_sec"], feedback=row["feedback"], id=row["id"], seq=row["seq"],
        created_at=row["created_at"], model_name=row["model_name"], kind=row["kind"],
    )


class SqliteChatRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._last_stamp = ""

    @classmethod
    def open(cls, path: Path, migrations=MIGRATIONS) -> SqliteChatRepository:
        return cls(open_database(path, migrations))

    # --- plumbing --------------------------------------------------------------
    def _now(self) -> str:
        """UTC ISO timestamp, strictly increasing within this repository (keeps ordering stable)."""
        stamp = utc_now()
        if stamp <= self._last_stamp:
            stamp = (datetime.fromisoformat(self._last_stamp) + timedelta(microseconds=1)).isoformat(
                timespec="microseconds")
        self._last_stamp = stamp
        return stamp

    @contextmanager
    def _tx(self, action: str) -> Iterator[sqlite3.Connection]:
        try:
            self._conn.execute("BEGIN IMMEDIATE")
        except sqlite3.Error as exc:
            raise StorageError(f"Could not {action}.", detail=f"{type(exc).__name__}: {exc}") from None
        try:
            yield self._conn
            self._conn.execute("COMMIT")
        except StorageError:
            self._rollback()
            raise
        except Exception as exc:
            self._rollback()
            logger.warning("Storage write failed (%s): %s", action, exc)
            raise StorageError(f"Could not {action}.", detail=f"{type(exc).__name__}: {exc}") from None

    def _rollback(self) -> None:
        try:
            if self._conn.in_transaction:
                self._conn.execute("ROLLBACK")
        except sqlite3.Error:
            logger.exception("Rollback failed")

    def _read(self, action: str, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        try:
            return self._conn.execute(sql, params).fetchall()
        except sqlite3.Error as exc:
            raise StorageError(f"Could not {action}.", detail=f"{type(exc).__name__}: {exc}") from None

    def _require_chat(self, conn: sqlite3.Connection, chat_id: str) -> sqlite3.Row:
        row = conn.execute("SELECT * FROM conversations WHERE id = ?", (chat_id,)).fetchone()
        if row is None:
            raise StorageError("That chat no longer exists.", detail=f"chat id {chat_id!r}")
        return row

    # --- chats -----------------------------------------------------------------
    def create_chat(self, title: str = DEFAULT_TITLE, model_name: str | None = None) -> Conversation:
        title = clean_title(title)
        now = self._now()
        chat_id = str(uuid.uuid4())
        with self._tx("create the chat") as conn:
            conn.execute(
                "INSERT INTO conversations (id, title, model_name, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (chat_id, title, model_name, now, now),
            )
        return Conversation(chat_id, title, model_name, now, now)

    def list_chats(self) -> list[Conversation]:
        rows = self._read("load the chat list",
                          "SELECT * FROM conversations ORDER BY updated_at DESC, rowid DESC")
        return [_conversation(r) for r in rows]

    def get_chat(self, chat_id: str) -> Conversation:
        rows = self._read("load the chat", "SELECT * FROM conversations WHERE id = ?", (chat_id,))
        if not rows:
            raise StorageError("That chat no longer exists.", detail=f"chat id {chat_id!r}")
        return _conversation(rows[0])

    def chat_exists(self, chat_id: str) -> bool:
        return bool(self._read("load the chat", "SELECT 1 FROM conversations WHERE id = ?", (chat_id,)))

    def get_messages(self, chat_id: str) -> list[ChatMessage]:
        self.get_chat(chat_id)
        rows = self._read("load the messages",
                          "SELECT * FROM messages WHERE conversation_id = ? ORDER BY seq", (chat_id,))
        messages = [_message(r) for r in rows]
        file_rows = self._read(
            "load the message files",
            "SELECT f.message_id, f.path, f.project_id FROM message_files f JOIN messages m ON m.id = f.message_id"
            " WHERE m.conversation_id = ? ORDER BY f.message_id, f.position", (chat_id,))
        by_id = {m.id: m for m in messages}
        for row in file_rows:
            message = by_id[row["message_id"]]
            message.files.append(row["path"])
            message.project_id = row["project_id"]
        return messages

    def _insert_message(self, conn: sqlite3.Connection, chat_id: str, message: ChatMessage) -> ChatMessage:
        now = self._now()
        seq = conn.execute(
            "SELECT COALESCE(MAX(seq), 0) + 1 FROM messages WHERE conversation_id = ?", (chat_id,)
        ).fetchone()[0]
        cursor = conn.execute(
            "INSERT INTO messages (conversation_id, seq, role, content, status, eval_count, tokens_per_sec,"
            " feedback, created_at, model_name, kind) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (chat_id, seq, message.role, message.content, message.status, message.eval_count,
             message.tokens_per_sec, message.feedback, now, message.model_name, message.kind),
        )
        for position, path in enumerate(message.files):
            conn.execute("INSERT INTO message_files (message_id, position, path, project_id) VALUES (?, ?, ?, ?)",
                         (cursor.lastrowid, position, path, message.project_id))
        self._touch(conn, chat_id, now)
        return ChatMessage(
            role=message.role, content=message.content, files=list(message.files), status=message.status,
            eval_count=message.eval_count, tokens_per_sec=message.tokens_per_sec, feedback=message.feedback,
            id=cursor.lastrowid, seq=seq, created_at=now, project_id=message.project_id,
            model_name=message.model_name, kind=message.kind,
        )

    def _touch(self, conn: sqlite3.Connection, chat_id: str, now: str) -> None:
        conn.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (now, chat_id))

    def add_message(self, chat_id: str, message: ChatMessage) -> ChatMessage:
        check_message(message)
        with self._tx("save the message") as conn:
            chat = self._require_chat(conn, chat_id)
            if message.role == "user" and chat["title"] == DEFAULT_TITLE:
                has_user = conn.execute(
                    "SELECT 1 FROM messages WHERE conversation_id = ? AND role = 'user' LIMIT 1", (chat_id,)
                ).fetchone()
                if has_user is None:
                    conn.execute("UPDATE conversations SET title = ? WHERE id = ?",
                                 (title_from_prompt(message.content), chat_id))
            return self._insert_message(conn, chat_id, message)

    def replace_reply(self, chat_id: str, message: ChatMessage) -> ChatMessage:
        check_message(message)
        with self._tx("save the reply") as conn:
            self._require_chat(conn, chat_id)
            conn.execute(
                "DELETE FROM messages WHERE conversation_id = ? AND role = 'assistant' AND seq > "
                "COALESCE((SELECT MAX(seq) FROM messages WHERE conversation_id = ? AND role = 'user'), 0)",
                (chat_id, chat_id),
            )
            return self._insert_message(conn, chat_id, message)

    def rename_chat(self, chat_id: str, title: str) -> Conversation:
        title = clean_title(title)
        with self._tx("rename the chat") as conn:
            self._require_chat(conn, chat_id)
            conn.execute("UPDATE conversations SET title = ? WHERE id = ?", (title, chat_id))
        return self.get_chat(chat_id)

    def set_chat_model(self, chat_id: str, model_name: str) -> None:
        if not model_name or not model_name.strip():
            raise StorageError("Could not save the model choice.", detail="empty model name")
        with self._tx("save the model choice") as conn:
            self._require_chat(conn, chat_id)
            conn.execute("UPDATE conversations SET model_name = ? WHERE id = ?", (model_name, chat_id))

    def delete_chat(self, chat_id: str) -> None:
        with self._tx("delete the chat") as conn:
            self._require_chat(conn, chat_id)
            conn.execute("DELETE FROM conversations WHERE id = ?", (chat_id,))

    def set_feedback(self, message_id: int, value: str | None) -> None:
        check_feedback(value)
        with self._tx("save the feedback") as conn:
            cursor = conn.execute("UPDATE messages SET feedback = ? WHERE id = ?", (value, message_id))
            if cursor.rowcount == 0:
                raise StorageError("That message no longer exists.", detail=f"message id {message_id}")

    # --- projects and settings ------------------------------------------------------
    def list_projects(self) -> list[ProjectRecord]:
        rows = self._read("load the projects", "SELECT * FROM projects ORDER BY updated_at DESC, rowid DESC")
        return [_project(r) for r in rows]

    def create_project(self, name: str, path: str, conversation_id: str | None,
                       status: str = "planned") -> ProjectRecord:
        check_project_status(status)
        now = self._now()
        project_id = str(uuid.uuid4())
        with self._tx("save the project") as conn:
            if conversation_id is not None:
                self._require_chat(conn, conversation_id)
            conn.execute(
                "INSERT INTO projects (id, conversation_id, name, path, status, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)", (project_id, conversation_id, name, path, status, now, now))
        return ProjectRecord(project_id, conversation_id, name, path, status, now, now)

    def update_project_status(self, project_id: str, status: str) -> None:
        check_project_status(status)
        with self._tx("update the project") as conn:
            cursor = conn.execute("UPDATE projects SET status = ?, updated_at = ? WHERE id = ?",
                                  (status, self._now(), project_id))
            if cursor.rowcount == 0:
                raise StorageError("That project no longer exists.", detail=f"project id {project_id!r}")

    def get_project(self, project_id: str) -> ProjectRecord:
        rows = self._read("load the project", "SELECT * FROM projects WHERE id = ?", (project_id,))
        if not rows:
            raise StorageError("That project no longer exists.", detail=f"project id {project_id!r}")
        return _project(rows[0])

    def latest_project_for_chat(self, chat_id: str) -> ProjectRecord | None:
        rows = self._read("load the project",
                          "SELECT * FROM projects WHERE conversation_id = ? ORDER BY created_at DESC, rowid DESC"
                          " LIMIT 1", (chat_id,))
        return _project(rows[0]) if rows else None

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        rows = self._read("load a setting", "SELECT value FROM app_settings WHERE key = ?", (key,))
        return rows[0]["value"] if rows and rows[0]["value"] is not None else default

    def set_setting(self, key: str, value: str | None) -> None:
        with self._tx("save a setting") as conn:
            if value is None:
                conn.execute("DELETE FROM app_settings WHERE key = ?", (key,))
            else:
                conn.execute(
                    "INSERT INTO app_settings (key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, str(value)),
                )

    def schema_version(self) -> int:
        return int(self._read("read the schema version", "SELECT MAX(version) AS v FROM schema_version")[0]["v"])

    def close(self) -> None:
        try:
            self._conn.close()
        except sqlite3.Error:
            logger.debug("close failed", exc_info=True)
