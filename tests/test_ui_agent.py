"""Project generation and edit flows in the window (offscreen, MOCK Ollama, tmp_path only)."""

import json

import pytest

from app.backend.ollama_client import OllamaClient
from app.backend.status import ConnectionState
from app.storage.chat_repository import SqliteChatRepository
from app.ui.agent_widgets import ChangesCard, PlanCard
from app.ui.main_window import MainWindow
from app.ui.message_widgets import AssistantMessage, ErrorCard
from tests.fake_ollama import FakeOllama

pytestmark = pytest.mark.gui

PLAN = json.dumps({
    "project_name": "Hello Tool",
    "description": "Prints a greeting.",
    "language": "Python",
    "files": [{"path": "hello.py", "purpose": "main"}, {"path": "README.md", "purpose": "docs"}],
    "run_instructions": "python hello.py",
    "test_command": "",
})
HELLO = "```python\nprint('hello')\n```"
README = "````markdown\n# Hello\n\n```\npython hello.py\n```\n````"


@pytest.fixture
def fake():
    return FakeOllama()


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "data" / "assistant.db"


@pytest.fixture
def session(qtbot, themed_app, tmp_config, fake, db_path):
    opened = []

    def start():
        repo = SqliteChatRepository.open(db_path)
        win = MainWindow(tmp_config, store=repo, use_webengine=False,
                         client_factory=lambda: OllamaClient(tmp_config, transport=fake.transport()))
        qtbot.addWidget(win)
        win.resize(1300, 850)
        win.show()
        qtbot.waitUntil(lambda: win.health().state is ConnectionState.CONNECTED, timeout=5000)
        opened.append((win, repo))
        return win

    yield start
    for win, repo in opened:
        win.close()
        repo.close()


def _cards(win, kind):
    return [w for w in win.chat_view.items if isinstance(w, kind)]


def _plan(qtbot, win, fake, request="make a hello tool", replies=(PLAN,)):
    fake.replies = list(replies)
    with qtbot.waitSignal(win.streamFinished, timeout=10000):
        assert win.submit_prompt(request, project_mode=True)
    return _cards(win, PlanCard)[-1]


def test_plan_card_shows_files_before_anything_is_written(qtbot, session, fake, tmp_config):
    win = session()
    card = _plan(qtbot, win, fake)
    assert card.is_open()
    assert [label.text().split("  —  ")[0] for label in card.file_labels] == ["•  hello.py", "•  README.md"]
    assert not tmp_config.projects_dir.exists() or not any(tmp_config.projects_dir.iterdir())
    plan_prompt = fake.chat_bodies()[0]["messages"]
    assert plan_prompt[0]["role"] == "system" and "ONLY one JSON object" in plan_prompt[1]["content"]
    assert win.store.list_projects() == []


def test_cancel_plan_writes_nothing(qtbot, session, fake, tmp_config):
    win = session()
    card = _plan(qtbot, win, fake)
    card.cancel_button.click()
    assert card.state_text() == "Cancelled" and not card.is_open()
    assert len(fake.chat_bodies()) == 1  # no file calls
    assert not tmp_config.projects_dir.exists() or not any(tmp_config.projects_dir.iterdir())


def test_apply_generates_files_links_db_and_preview(qtbot, session, fake, tmp_config, db_path):
    win = session()
    card = _plan(qtbot, win, fake)
    chat_id = win.current_chat_id()
    fake.replies = [HELLO, README]
    with qtbot.waitSignal(win.streamFinished, timeout=10000):
        card.apply_button.click()

    root = tmp_config.projects_dir / "hello-tool"
    assert (root / "hello.py").read_text() == "print('hello')\n"
    assert "```\npython hello.py\n```" in (root / "README.md").read_text()
    assert "2 of 2 files written (complete)" in card.state_text()

    projects = win.store.list_projects()
    assert len(projects) == 1 and projects[0].conversation_id == chat_id and projects[0].status == "complete"
    assert win.sidebar.project_model.item(0).text() == "hello-tool"

    summary = [w for w in win.chat_view.items if isinstance(w, AssistantMessage)][-1]
    assert [c.path for c in summary.file_cards] == ["hello.py", "README.md"]
    assert win.is_preview_open() and set(win.preview.files()) == {"README.md", "hello.py"}
    stored = win.store.get_messages(chat_id)[-1]
    assert stored.files == ["hello.py", "README.md"] and stored.project_id == projects[0].id

    # the file prompts asked for one block per file; nothing was executed
    file_prompts = [b["messages"][1]["content"] for b in fake.chat_bodies()[1:]]
    assert "`hello.py`" in file_prompts[0] and "four backticks" in file_prompts[1]


def test_restart_restores_file_cards_and_project_preview(qtbot, session, fake, tmp_config):
    win = session()
    card = _plan(qtbot, win, fake)
    fake.replies = [HELLO, README]
    with qtbot.waitSignal(win.streamFinished, timeout=10000):
        card.apply_button.click()
    chat_id = win.current_chat_id()
    win.close()
    win.store.close()

    win2 = session()
    assert win2.current_chat_id() == chat_id
    summary = [w for w in win2.chat_view.items if isinstance(w, AssistantMessage)][-1]
    assert [c.path for c in summary.file_cards] == ["hello.py", "README.md"]
    summary.file_cards[0].fileOpened.emit("hello.py")
    assert win2.preview.current_path() == "hello.py"


def test_sidebar_project_opens_files(qtbot, session, fake):
    win = session()
    card = _plan(qtbot, win, fake)
    fake.replies = [HELLO, README]
    with qtbot.waitSignal(win.streamFinished, timeout=10000):
        card.apply_button.click()
    win.close_preview()
    win.new_chat()
    project_id = win.store.list_projects()[0].id
    win.sidebar.projectSelected.emit(project_id)
    assert win.is_preview_open() and "hello.py" in win.preview.files()


def test_partial_failure_is_listed_and_successes_kept(qtbot, session, fake, tmp_config):
    win = session()
    card = _plan(qtbot, win, fake)
    fake.replies = [HELLO, "no block", "still no block"]
    with qtbot.waitSignal(win.streamFinished, timeout=10000):
        card.apply_button.click()
    root = tmp_config.projects_dir / "hello-tool"
    assert (root / "hello.py").is_file() and not (root / "README.md").exists()
    summary = [w for w in win.chat_view.items if isinstance(w, AssistantMessage)][-1]
    assert "1 of 2 files written" in summary.text() and "README.md" in summary.text()
    assert win.store.list_projects()[0].status == "partial"


def test_malformed_plan_twice_shows_error_card(qtbot, session, fake, tmp_config):
    win = session()
    fake.replies = ["not json", '{"project_name": ']
    win.submit_prompt("make a tool", project_mode=True)
    qtbot.waitUntil(lambda: bool(_cards(win, ErrorCard)), timeout=10000)
    text = _cards(win, ErrorCard)[-1].label.text()
    assert "project plan could not be used" in text
    assert len(fake.chat_bodies()) == 2  # first try + one corrective retry
    assert _cards(win, PlanCard) == [] and win.store.list_projects() == []
    assert win.store.get_messages(win.current_chat_id())[-1].status == "error"


def test_stop_during_generation_keeps_written_files(qtbot, session, fake, tmp_config):
    win = session()
    card = _plan(qtbot, win, fake)
    fake.replies = [HELLO]  # README then falls back to slow tokens
    fake.tokens = [f"w{i} " for i in range(400)]
    fake.chunk_delay_s = 0.02
    card.apply_button.click()
    root = tmp_config.projects_dir / "hello-tool"
    qtbot.waitUntil(lambda: (root / "hello.py").exists(), timeout=10000)
    qtbot.wait(100)
    win.stop_generation()
    assert not win.is_busy()
    assert (root / "hello.py").is_file()
    assert win.store.list_projects()[0].status == "cancelled"
    summary = [w for w in win.chat_view.items if isinstance(w, AssistantMessage)][-1]
    assert "stopped" in summary.text().lower()


def _project_chat(qtbot, win, fake):
    card = _plan(qtbot, win, fake)
    fake.replies = [HELLO, README]
    with qtbot.waitSignal(win.streamFinished, timeout=10000):
        card.apply_button.click()


def test_followup_in_project_chat_sends_files_and_offers_changes(qtbot, session, fake, tmp_config):
    win = session()
    _project_chat(qtbot, win, fake)
    root = tmp_config.projects_dir / "hello-tool"
    fake.replies = ["Use a name:\n```python path=hello.py\nprint('hello, world')\n```"]
    with qtbot.waitSignal(win.streamFinished, timeout=10000):
        win.submit_prompt("fix hello.py so it greets the world")
    request = fake.chat_bodies()[-1]["messages"][-1]["content"]
    assert "File hello.py:" in request and "print('hello')" in request and "path=<relative path>" in request
    stored_user = [m for m in win.store.get_messages(win.current_chat_id()) if m.role == "user"][-1]
    assert stored_user.content == "fix hello.py so it greets the world"  # context is not stored

    card = _cards(win, ChangesCard)[-1]
    assert "+print('hello, world')" in card.diff_view.toPlainText()
    assert (root / "hello.py").read_text() == "print('hello')\n"  # not written before Apply
    card.apply_button.click()
    assert (root / "hello.py").read_text() == "print('hello, world')\n"
    assert len(list(root.glob("hello.py.bak-*"))) == 1
    assert "Applied to 1 file" in card.state_text()


def test_changes_cancel_leaves_files_alone(qtbot, session, fake, tmp_config):
    win = session()
    _project_chat(qtbot, win, fake)
    root = tmp_config.projects_dir / "hello-tool"
    fake.replies = ["```python path=hello.py\nimport os\nos.remove('x')\n```"]
    with qtbot.waitSignal(win.streamFinished, timeout=10000):
        win.submit_prompt("refactor hello.py")
    card = _cards(win, ChangesCard)[-1]
    card.cancel_button.click()
    assert (root / "hello.py").read_text() == "print('hello')\n"
    assert list(root.glob("*.bak-*")) == []


def test_model_text_is_never_executed(qtbot, session, fake, tmp_config, monkeypatch):
    import subprocess

    calls = []
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: calls.append(a) or (_ for _ in ()).throw(
        AssertionError("subprocess started")))
    win = session()
    _project_chat(qtbot, win, fake)
    fake.replies = ["Run this:\n```powershell\nRemove-Item -Recurse C:\\\n```"]
    with qtbot.waitSignal(win.streamFinished, timeout=10000):
        win.submit_prompt("debug hello.py please")
    assert calls == []
    assert _cards(win, ChangesCard) == []  # a command block without path= is not a file change
