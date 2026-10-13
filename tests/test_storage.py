"""SQLite storage: schema, CRUD, transactions, migrations, corruption. tmp_path only."""

import hashlib
import sqlite3

import pytest

from app.backend.chat_store import DEFAULT_TITLE, ChatMessage, title_from_prompt
from app.errors import StorageError
from app.storage.chat_repository import SqliteChatRepository
from app.storage.database import (
    MIGRATIONS,
    DatabaseCorruptError,
    inspect_database,
    latest_version,
    open_database,
)


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "data" / "assistant.db"


@pytest.fixture
def repo(db_path):
    r = SqliteChatRepository.open(db_path)
    yield r
    r.close()


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _add_project(conn, project_id, chat_id):
    conn.execute(
        "INSERT INTO projects (id, conversation_id, name, path, status, created_at, updated_at)"
        " VALUES (?, ?, 'demo', 'C:/p', 'created', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')",
        (project_id, chat_id),
    )


# --- schema ----------------------------------------------------------------------
def test_schema_created_at_latest_with_pragmas(db_path):
    conn = open_database(db_path)
    try:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"conversations", "messages", "projects", "app_settings", "schema_version", "message_files"} <= tables
        indexes = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
        assert {"idx_messages_conversation_seq", "idx_conversations_updated"} <= indexes
        rows = conn.execute("SELECT version, applied_at FROM schema_version").fetchall()
        assert [r[0] for r in rows] == list(range(1, latest_version() + 1)) and rows[0][1].endswith("+00:00")
        assert isinstance(conn.execute("SELECT 1").fetchone(), sqlite3.Row)
    finally:
        conn.close()
    assert latest_version() == 4


def test_reopen_does_not_reapply(db_path):
    open_database(db_path).close()
    conn = open_database(db_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM schema_version").fetchone()[0] == latest_version()
    finally:
        conn.close()


def test_check_constraints(repo):
    chat = repo.create_chat()
    with pytest.raises(sqlite3.IntegrityError):
        repo._conn.execute(
            "INSERT INTO messages (conversation_id, seq, role, content, status, created_at)"
            " VALUES (?, 1, 'system', 'x', 'complete', 'now')", (chat.id,))
    with pytest.raises(sqlite3.IntegrityError):
        repo._conn.execute(
            "INSERT INTO messages (conversation_id, seq, role, content, status, created_at)"
            " VALUES ('no-such-chat', 1, 'user', 'x', 'complete', 'now')")


# --- CRUD ------------------------------------------------------------------------
def test_create_and_list_newest_updated_first(repo):
    a = repo.create_chat(model_name="qwen2.5-coder-14b:latest")
    b = repo.create_chat()
    assert len(a.id) == 36 and a.title == DEFAULT_TITLE and a.created_at.endswith("+00:00")
    assert [c.id for c in repo.list_chats()] == [b.id, a.id]
    repo.add_message(a.id, ChatMessage("user", "hello"))
    assert [c.id for c in repo.list_chats()] == [a.id, b.id]
    assert repo.get_chat(a.id).model_name == "qwen2.5-coder-14b:latest"


def test_messages_keep_seq_order_and_fields(repo):
    chat = repo.create_chat()
    repo.add_message(chat.id, ChatMessage("user", "q1"))
    saved = repo.add_message(chat.id, ChatMessage("assistant", "a1", eval_count=10, tokens_per_sec=3.5))
    repo.add_message(chat.id, ChatMessage("user", "q2"))
    messages = repo.get_messages(chat.id)
    assert [(m.seq, m.role, m.content) for m in messages] == [(1, "user", "q1"), (2, "assistant", "a1"),
                                                              (3, "user", "q2")]
    assert saved.id == messages[1].id and messages[1].eval_count == 10 and messages[1].tokens_per_sec == 3.5
    assert all(m.status == "complete" for m in messages)


def test_get_missing_chat_raises(repo):
    with pytest.raises(StorageError):
        repo.get_chat("missing")
    with pytest.raises(StorageError):
        repo.get_messages("missing")
    with pytest.raises(StorageError):
        repo.add_message("missing", ChatMessage("user", "x"))
    assert repo.chat_exists("missing") is False


@pytest.mark.parametrize("title, expected", [("  My   chat ", "My chat"), ("x" * 80, "x" * 80), ("a", "a")])
def test_rename_valid(repo, title, expected):
    chat = repo.create_chat()
    assert repo.rename_chat(chat.id, title).title == expected
    assert repo.get_chat(chat.id).title == expected


@pytest.mark.parametrize("title", ["", "   ", "x" * 81])
def test_rename_invalid(repo, title):
    chat = repo.create_chat()
    with pytest.raises(StorageError):
        repo.rename_chat(chat.id, title)
    assert repo.get_chat(chat.id).title == DEFAULT_TITLE


def test_delete_cascades_messages_and_unlinks_projects(repo):
    chat = repo.create_chat()
    repo.add_message(chat.id, ChatMessage("user", "q"))
    repo.add_message(chat.id, ChatMessage("assistant", "a"))
    _add_project(repo._conn, "p1", chat.id)
    repo.delete_chat(chat.id)
    assert not repo.chat_exists(chat.id)
    assert repo._conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 0
    projects = repo.list_projects()
    assert len(projects) == 1 and projects[0].conversation_id is None and projects[0].name == "demo"


def test_feedback_persists(repo, db_path):
    chat = repo.create_chat()
    repo.add_message(chat.id, ChatMessage("user", "q"))
    reply = repo.add_message(chat.id, ChatMessage("assistant", "a"))
    repo.set_feedback(reply.id, "bad")
    repo.close()
    again = SqliteChatRepository.open(db_path)
    try:
        assert again.get_messages(chat.id)[1].feedback == "bad"
        again.set_feedback(reply.id, None)
        assert again.get_messages(chat.id)[1].feedback is None
        with pytest.raises(StorageError):
            again.set_feedback(reply.id, "great")
        with pytest.raises(StorageError):
            again.set_feedback(99999, "bad")
    finally:
        again.close()


def test_settings(repo):
    assert repo.get_setting("last_chat_id") is None
    assert repo.get_setting("x", "default") == "default"
    repo.set_setting("last_chat_id", "abc")
    repo.set_setting("last_chat_id", "def")
    assert repo.get_setting("last_chat_id") == "def"
    repo.set_setting("last_chat_id", None)
    assert repo.get_setting("last_chat_id") is None


def test_replace_reply_only_drops_trailing_assistant(repo):
    chat = repo.create_chat()
    repo.add_message(chat.id, ChatMessage("user", "q1"))
    repo.add_message(chat.id, ChatMessage("assistant", "a1"))
    repo.add_message(chat.id, ChatMessage("user", "q2"))
    repo.add_message(chat.id, ChatMessage("assistant", "a2"))
    repo.replace_reply(chat.id, ChatMessage("assistant", "a2-new", status="stopped"))
    assert [(m.content, m.status) for m in repo.get_messages(chat.id)] == [
        ("q1", "complete"), ("a1", "complete"), ("q2", "complete"), ("a2-new", "stopped")]


# --- auto-title ----------------------------------------------------------------------
def test_auto_title_rules(repo):
    chat = repo.create_chat()
    repo.add_message(chat.id, ChatMessage("user", "\n  fix   my parser\nsecond line is ignored"))
    assert repo.get_chat(chat.id).title == "Fix my parser"
    repo.add_message(chat.id, ChatMessage("user", "another question"))
    assert repo.get_chat(chat.id).title == "Fix my parser"  # only the first user message

    long_chat = repo.create_chat()
    repo.add_message(long_chat.id, ChatMessage("user", "w" * 100))
    title = repo.get_chat(long_chat.id).title
    assert len(title) == 40 and title.endswith("…")

    named = repo.create_chat("Kept name")
    repo.add_message(named.id, ChatMessage("user", "something"))
    assert repo.get_chat(named.id).title == "Kept name"  # a custom title is never replaced


def test_title_from_prompt_edge_cases():
    assert title_from_prompt("   \n\n  ") == DEFAULT_TITLE
    assert title_from_prompt("x" * 40) == "X" + "x" * 39
    assert title_from_prompt("x" * 41).endswith("…")


# --- transactions ----------------------------------------------------------------------
def test_failure_mid_write_rolls_back(repo, monkeypatch):
    chat = repo.create_chat()
    before = repo.get_chat(chat.id)

    def boom(*args, **kwargs):
        raise sqlite3.OperationalError("disk I/O error (injected)")

    # _touch runs after the message INSERT and the title UPDATE, inside the same transaction
    monkeypatch.setattr(repo, "_touch", boom)
    with pytest.raises(StorageError) as info:
        repo.add_message(chat.id, ChatMessage("user", "first question"))
    assert "injected" in (info.value.detail or "")
    assert repo._conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 0
    after = repo.get_chat(chat.id)
    assert after.title == before.title == DEFAULT_TITLE and after.updated_at == before.updated_at
    assert not repo._conn.in_transaction


def test_failed_replace_keeps_old_reply(repo, monkeypatch):
    chat = repo.create_chat()
    repo.add_message(chat.id, ChatMessage("user", "q"))
    repo.add_message(chat.id, ChatMessage("assistant", "old"))
    monkeypatch.setattr(repo, "_touch", lambda *a: (_ for _ in ()).throw(sqlite3.OperationalError("injected")))
    with pytest.raises(StorageError):
        repo.replace_reply(chat.id, ChatMessage("assistant", "new"))
    assert [m.content for m in repo.get_messages(chat.id)] == ["q", "old"]


def test_invalid_message_rejected_before_write(repo):
    chat = repo.create_chat()
    with pytest.raises(StorageError):
        repo.add_message(chat.id, ChatMessage("system", "prompt"))
    with pytest.raises(StorageError):
        repo.add_message(chat.id, ChatMessage("assistant", "x", status="weird"))
    assert repo.get_messages(chat.id) == []


# --- migrations ----------------------------------------------------------------------
V_NEXT = (latest_version() + 1, "ALTER TABLE conversations ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0;\n"
         "CREATE INDEX idx_conversations_pinned ON conversations (pinned);")


def test_fake_next_migration_upgrades_and_keeps_data(db_path):
    repo = SqliteChatRepository.open(db_path)
    chat = repo.create_chat()
    repo.add_message(chat.id, ChatMessage("user", "keep me"))
    repo.close()

    conn = open_database(db_path, [*MIGRATIONS, V_NEXT])
    try:
        assert [r[0] for r in conn.execute("SELECT version FROM schema_version ORDER BY version")] == \
            list(range(1, latest_version() + 2))
        row = conn.execute("SELECT title, pinned FROM conversations").fetchone()
        assert row["title"] == "Keep me" and row["pinned"] == 0
        assert conn.execute("SELECT content FROM messages").fetchone()[0] == "keep me"
    finally:
        conn.close()


def test_broken_migration_rolls_back_whole_step(db_path):
    open_database(db_path).close()
    bad = (latest_version() + 1, "ALTER TABLE conversations ADD COLUMN pinned INTEGER;\nTHIS IS NOT SQL;")
    with pytest.raises(StorageError):
        open_database(db_path, [*MIGRATIONS, bad])
    conn = open_database(db_path)
    try:
        columns = [r[1] for r in conn.execute("PRAGMA table_info(conversations)")]
        assert "pinned" not in columns
        assert conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] == latest_version()
    finally:
        conn.close()


def test_newer_database_is_refused_and_untouched(db_path):
    repo = SqliteChatRepository.open(db_path)
    repo.create_chat()
    repo._conn.execute("INSERT INTO schema_version (version, applied_at) VALUES (99, 'future')")
    repo.close()
    digest = _sha(db_path)
    files_before = sorted(p.name for p in db_path.parent.iterdir())

    with pytest.raises(StorageError) as info:
        open_database(db_path)
    assert "newer version" in info.value.message and "99" in info.value.message
    assert not isinstance(info.value, DatabaseCorruptError)
    assert _sha(db_path) == digest
    assert not any(".corrupt-" in p.name for p in db_path.parent.iterdir())
    assert sorted(p.name for p in db_path.parent.iterdir()) == files_before


# --- corruption ----------------------------------------------------------------------
def test_corrupt_file_is_backed_up_never_deleted(db_path):
    db_path.parent.mkdir(parents=True)
    garbage = b"this is definitely not a sqlite database " * 200
    db_path.write_bytes(garbage)

    with pytest.raises(DatabaseCorruptError) as info:
        open_database(db_path)
    backup = info.value.backup_path
    assert backup is not None and backup.name.startswith("assistant.db.corrupt-")
    assert backup.read_bytes() == garbage  # the user's bytes are kept as-is
    assert str(backup) in info.value.message
    assert not db_path.exists()

    # the UI may then start a fresh database at the same path
    fresh = SqliteChatRepository.open(db_path)
    try:
        assert fresh.list_chats() == []
    finally:
        fresh.close()
    assert backup.read_bytes() == garbage


def test_inspect_database_is_read_only(db_path):
    assert inspect_database(db_path).exists is False
    assert not db_path.exists()  # inspecting never creates the file
    repo = SqliteChatRepository.open(db_path)
    repo.create_chat()
    repo.create_chat()
    repo.close()
    digest = _sha(db_path)
    info = inspect_database(db_path)
    assert (info.schema_version, info.chat_count, info.error) == (latest_version(), 2, None)
    assert _sha(db_path) == digest


def test_repository_schema_version(repo):
    assert repo.schema_version() == latest_version() == 4


def test_real_v1_database_upgrades_to_latest_and_keeps_data(db_path):
    v1 = SqliteChatRepository(open_database(db_path, MIGRATIONS[:1]))
    chat = v1.create_chat()
    v1._conn.execute(
        "INSERT INTO messages (conversation_id, seq, role, content, status, created_at)"
        " VALUES (?, 1, 'user', 'old message', 'complete', '2026-01-01')", (chat.id,))
    v1.close()
    repo = SqliteChatRepository.open(db_path)
    try:
        assert repo.schema_version() == latest_version()
        assert [m.content for m in repo.get_messages(chat.id)] == ["old message"]
        assert repo.get_messages(chat.id)[0].files == []
    finally:
        repo.close()


# --- projects and message files (v2) ------------------------------------------------
def test_projects_crud_and_chat_link(repo):
    chat = repo.create_chat()
    first = repo.create_project("calc", "C:/p/calc", chat.id, "generating")
    second = repo.create_project("calc-2", "C:/p/calc-2", chat.id)
    assert repo.latest_project_for_chat(chat.id).id == second.id
    repo.update_project_status(first.id, "complete")
    assert repo.get_project(first.id).status == "complete"
    assert [p.id for p in repo.list_projects()][0] == first.id  # most recently updated first
    with pytest.raises(StorageError):
        repo.update_project_status(first.id, "exploded")
    with pytest.raises(StorageError):
        repo.create_project("x", "y", "no-such-chat")
    with pytest.raises(StorageError):
        repo.get_project("missing")
    assert repo.latest_project_for_chat("other") is None


def test_message_files_round_trip_and_cascade(repo):
    chat = repo.create_chat()
    project = repo.create_project("site", "C:/p/site", chat.id)
    repo.add_message(chat.id, ChatMessage("user", "make a site"))
    saved = repo.add_message(chat.id, ChatMessage("assistant", "done", files=["index.html", "css/site.css"],
                                                  project_id=project.id))
    restored = repo.get_messages(chat.id)[1]
    assert restored.files == ["index.html", "css/site.css"] and restored.project_id == project.id
    assert saved.files == restored.files
    repo.delete_chat(chat.id)
    assert repo._conn.execute("SELECT COUNT(*) FROM message_files").fetchone()[0] == 0
    assert repo.get_project(project.id).conversation_id is None



# --- v3: model per message and per chat (Phase 13, Fast mode) ---------------------------------
def test_v2_database_upgrades_to_v3_and_keeps_data(db_path):
    v2 = SqliteChatRepository(open_database(db_path, MIGRATIONS[:2]))
    chat = v2.create_chat(model_name="qwen2.5-coder-14b:latest")
    v2._conn.execute(
        "INSERT INTO messages (conversation_id, seq, role, content, status, created_at)"
        " VALUES (?, 1, 'assistant', 'old answer', 'complete', '2026-01-01')", (chat.id,))
    v2.close()
    repo = SqliteChatRepository.open(db_path)
    try:
        assert repo.schema_version() == latest_version()
        old = repo.get_messages(chat.id)[0]
        assert old.content == "old answer" and old.model_name is None  # unknown for old rows
        assert repo.get_chat(chat.id).model_name == "qwen2.5-coder-14b:latest"
    finally:
        repo.close()


def test_message_and_chat_model_round_trip(repo):
    chat = repo.create_chat(model_name="qwen2.5-coder-14b:latest")
    repo.add_message(chat.id, ChatMessage("user", "q"))
    repo.add_message(chat.id, ChatMessage("assistant", "a", model_name="qwen2.5-coder-7b:latest"))
    assert repo.get_messages(chat.id)[1].model_name == "qwen2.5-coder-7b:latest"
    repo.set_chat_model(chat.id, "qwen2.5-coder-7b:latest")
    assert repo.get_chat(chat.id).model_name == "qwen2.5-coder-7b:latest"
    with pytest.raises(StorageError):
        repo.set_chat_model(chat.id, " ")
    with pytest.raises(StorageError):
        repo.set_chat_model("missing", "qwen2.5-coder-7b:latest")



# --- v4: message kind (Phase 14) ------------------------------------------------------------
TOOL_TEXT = "`python -m pytest -q` in `D:\\laa-demo\\p`\n\nExit code 1 · 0.5 s\n\nErrors:\n````text\nboom\n````"


def test_v3_database_upgrades_to_v4_and_backfills_tool_messages(db_path):
    v3 = SqliteChatRepository(open_database(db_path, MIGRATIONS[:3]))
    chat = v3.create_chat()
    for seq, content in ((1, TOOL_TEXT), (2, "A normal answer with `code` in it.")):
        v3._conn.execute(
            "INSERT INTO messages (conversation_id, seq, role, content, status, created_at)"
            " VALUES (?, ?, 'assistant', ?, 'error', '2026-01-01')", (chat.id, seq, content))
    v3.close()
    repo = SqliteChatRepository.open(db_path)
    try:
        kinds = [m.kind for m in repo.get_messages(chat.id)]
        assert repo.schema_version() == 4 and kinds == ["tool", "chat"]
    finally:
        repo.close()


def test_message_kind_round_trip_and_validation(repo):
    chat = repo.create_chat()
    repo.add_message(chat.id, ChatMessage("assistant", "out", kind="tool"))
    assert repo.get_messages(chat.id)[0].kind == "tool"
    with pytest.raises(StorageError):
        repo.add_message(chat.id, ChatMessage("assistant", "x", kind="weird"))
