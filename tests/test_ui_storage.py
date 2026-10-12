"""Window + SQLite history across restarts (offscreen, mocked Ollama, tmp_path DB only)."""

import pytest
from PySide6.QtWidgets import QInputDialog, QMessageBox

from app.backend.chat_store import LAST_CHAT_SETTING
from app.backend.memory_store import InMemoryChatStore
from app.backend.ollama_client import OllamaClient
from app.backend.status import ConnectionState
from app.errors import StorageError
from app.prompts import load_system_prompt
from app.storage.chat_repository import SqliteChatRepository
from app.ui.main_window import DELETE_CONFIRM, STATUS_STOPPED, MainWindow
from app.ui.message_widgets import AssistantMessage, ErrorCard, UserBubble
from tests.fake_ollama import FakeOllama

pytestmark = pytest.mark.gui


@pytest.fixture
def fake():
    return FakeOllama()


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "data" / "assistant.db"


@pytest.fixture
def session(qtbot, themed_app, tmp_config, fake, db_path):
    """Open a window on the tmp DB; every call is one 'app start'. Closes everything at the end."""
    opened = []

    def start(store=None):
        repo = store if store is not None else SqliteChatRepository.open(db_path)
        win = MainWindow(tmp_config, store=repo, use_webengine=False,
                         client_factory=lambda: OllamaClient(tmp_config, transport=fake.transport()))
        qtbot.addWidget(win)
        win.resize(1300, 850)
        win.show()
        qtbot.waitUntil(lambda: win.health().state is ConnectionState.CONNECTED, timeout=5000)
        opened.append((win, repo))
        return win

    def restart(win):
        win.close()
        win.store.close()
        return start()

    start.restart = restart
    yield start
    for win, repo in opened:
        win.close()
        repo.close()


def _assistants(win):
    return [w for w in win.chat_view.items if isinstance(w, AssistantMessage)]


def _errors(win):
    return [w for w in win.chat_view.items if isinstance(w, ErrorCard)]


def _send(qtbot, win, text):
    with qtbot.waitSignal(win.streamFinished, timeout=10000):
        assert win.submit_prompt(text)


def test_history_and_context_survive_restart(qtbot, session, fake):
    win = session()
    _send(qtbot, win, "say hello")
    chat_id = win.current_chat_id()

    win2 = session.restart(win)
    assert win2.current_chat_id() == chat_id  # last opened chat is reopened
    assert win2.sidebar.chat_ids() == [chat_id]
    assert win2.sidebar.chat_titles() == ["Say hello"]
    items = win2.chat_view.items
    assert isinstance(items[0], UserBubble) and items[0].text() == "say hello"
    assert isinstance(items[1], AssistantMessage) and items[1].text() == "Hello from the model."
    assert items[1].status_label.text() == "qwen2.5-coder-14b · 42 tokens · 21.0 tok/s"

    fake.tokens = ["Second."]
    _send(qtbot, win2, "and again")
    body = fake.chat_bodies()[-1]
    assert body["messages"] == [
        {"role": "system", "content": load_system_prompt()},
        {"role": "user", "content": "say hello"},
        {"role": "assistant", "content": "Hello from the model."},
        {"role": "user", "content": "and again"},
    ]


def test_stopped_and_errored_replies_are_saved_with_status(qtbot, session, fake):
    from tests.fake_ollama import content_line

    fake.tokens = [f"part{i} " for i in range(300)]
    fake.chunk_delay_s = 0.02
    win = session()
    win.submit_prompt("long answer")
    assistant = _assistants(win)[0]
    qtbot.waitUntil(lambda: len(assistant.text()) > 10, timeout=5000)
    win.stop_generation()
    stopped_chat = win.current_chat_id()

    fake.chunk_delay_s = 0
    fake.raw_chunks = [content_line("Partial "), b'{"error":"CUDA out of memory"}\n']
    win.new_chat()
    win.submit_prompt("big job")
    qtbot.waitUntil(lambda: bool(_errors(win)), timeout=5000)
    error_chat = win.current_chat_id()

    stopped = win.store.get_messages(stopped_chat)[-1]
    assert stopped.status == "stopped" and stopped.content.startswith("part0 ")
    errored = win.store.get_messages(error_chat)[-1]
    assert errored.status == "error" and errored.content == "Ollama reported an error: CUDA out of memory"
    assert "Traceback" not in errored.content

    win2 = session.restart(win)
    win2.select_chat(stopped_chat)
    assert _assistants(win2)[0].status_label.text() == STATUS_STOPPED
    win2.select_chat(error_chat)
    assert _errors(win2)[0].label.text() == "Ollama reported an error: CUDA out of memory"


def test_rename_and_delete_persist_across_restart(qtbot, session, monkeypatch):
    win = session()
    _send(qtbot, win, "first chat")
    first = win.current_chat_id()
    win.new_chat()
    _send(qtbot, win, "second chat")
    second = win.current_chat_id()

    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("Renamed one", True))
    win.sidebar.renameRequested.emit(first)
    asked = []
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a, **k: asked.append(a[2]) or QMessageBox.StandardButton.Yes)
    win.sidebar.deleteRequested.emit(second)
    assert asked == [DELETE_CONFIRM]

    win2 = session.restart(win)
    assert win2.sidebar.chat_ids() == [first]
    assert win2.sidebar.chat_titles() == ["Renamed one"]
    assert win2.current_chat_id() == first


def test_invalid_rename_shows_message_and_keeps_title(qtbot, session, monkeypatch):
    win = session()
    _send(qtbot, win, "keep this title")
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("x" * 81, True))
    win.sidebar.renameRequested.emit(win.current_chat_id())
    assert win.toast.isVisible() and "80" in win.toast.text()
    assert win.sidebar.chat_titles() == ["Keep this title"]


def test_regenerate_replaces_last_reply_in_db(qtbot, session, fake):
    win = session()
    _send(qtbot, win, "question")
    fake.tokens = ["Better", " answer"]
    with qtbot.waitSignal(win.streamFinished, timeout=10000):
        _assistants(win)[0].actions.regenerate_button.click()
    win2 = session.restart(win)
    stored = win2.store.get_messages(win2.current_chat_id())
    assert [(m.role, m.content) for m in stored] == [("user", "question"), ("assistant", "Better answer")]


def test_thumbs_down_persists(qtbot, session):
    win = session()
    _send(qtbot, win, "rate me")
    _assistants(win)[0].actions.thumbs_button.click()
    assert win.store.get_messages(win.current_chat_id())[-1].feedback == "bad"
    win2 = session.restart(win)
    restored = _assistants(win2)[0]
    assert restored.actions.thumbs_button.isChecked()
    restored.actions.thumbs_button.click()
    assert win2.store.get_messages(win2.current_chat_id())[-1].feedback is None


def test_empty_new_chats_do_not_pile_up(qtbot, session):
    win = session()
    _send(qtbot, win, "real chat")
    real = win.current_chat_id()
    empty = win.new_chat()
    assert win.new_chat() == empty  # reused, not another row
    win.select_chat(real)
    assert win.sidebar.chat_ids() == [real]  # the untouched chat was dropped
    win2 = session.restart(win)
    assert win2.sidebar.chat_ids() == [real]


def test_startup_with_empty_db_starts_new_chat(session, db_path):
    win = session()
    assert win.current_chat_id() is not None
    assert win.store.get_setting(LAST_CHAT_SETTING) == win.current_chat_id()
    assert win.sidebar.project_model.rowCount() == 0  # projects table is empty until Phase 6


def test_projects_section_reads_projects_table(session, db_path):
    repo = SqliteChatRepository.open(db_path)
    repo._conn.execute(
        "INSERT INTO projects (id, conversation_id, name, path, status, created_at, updated_at)"
        " VALUES ('p1', NULL, 'calculator', 'C:/x', 'created', '2026-01-01', '2026-01-01')")
    win = session(store=repo)
    model = win.sidebar.project_model
    assert [model.item(r).text() for r in range(model.rowCount())] == ['calculator']


class FailingStore(InMemoryChatStore):
    """Every write fails like a full or locked disk."""

    def add_message(self, chat_id, message):
        raise StorageError("Could not save the message.", detail="database or disk is full")

    def replace_reply(self, chat_id, message):
        raise StorageError("Could not save the reply.", detail="database or disk is full")

    def set_setting(self, key, value):
        raise StorageError("Could not save a setting.")


class BrokenStore(InMemoryChatStore):
    """Even reads fail."""

    def _fail(self, *args, **kwargs):
        raise StorageError("The chat history is not available.")

    list_chats = get_chat = get_messages = chat_exists = create_chat = _fail
    get_setting = set_setting = list_projects = _fail


def test_storage_errors_show_an_error_and_do_not_crash(qtbot, session):
    win = session(store=FailingStore())
    assert win.submit_prompt("hello") is False
    cards = _errors(win)
    assert cards and cards[-1].label.text() == "Could not save the message."
    assert not win.is_busy() and win.isVisible()


def test_fully_broken_store_still_opens_the_window(qtbot, session):
    win = session(store=BrokenStore())
    assert win.isVisible()
    assert win.submit_prompt("hello") is False
    win.new_chat()
    win.select_chat("anything")
    assert win.toast.isVisible()


def test_stop_button_signal_saves_partial_and_next_stream_is_unaffected(qtbot, session, fake):
    fake.tokens = [f"p{i} " for i in range(300)]
    fake.chunk_delay_s = 0.02
    win = session()
    win.submit_prompt("go")
    assistant = _assistants(win)[0]
    qtbot.waitUntil(lambda: len(assistant.text()) > 6, timeout=5000)
    win.composer.stopRequested.emit()  # the real Stop button path (sender is the composer)
    assert not win.is_busy()
    assert assistant.status_label.text() == STATUS_STOPPED
    assert win.store.get_messages(win.current_chat_id())[-1].status == "stopped"

    fake.chunk_delay_s = 0
    fake.tokens = ["Fresh", " answer."]
    _send(qtbot, win, "next")  # a late 'cancelled' from the old worker must not end this stream
    assert _assistants(win)[-1].text() == "Fresh answer."
    assert win.store.get_messages(win.current_chat_id())[-1].content == "Fresh answer."
