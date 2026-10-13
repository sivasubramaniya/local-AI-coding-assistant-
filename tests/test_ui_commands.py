"""Command approval flow in the window: allowlist first, then the user's approval, then a worker."""

import pytest

from app.backend.chat_store import ChatMessage
from app.backend.ollama_client import OllamaClient
from app.backend.status import ConnectionState
from app.storage.chat_repository import SqliteChatRepository
from app.ui.main_window import MainWindow
from app.ui.message_widgets import AssistantMessage, ErrorCard
from tests.fake_ollama import FakeOllama

pytestmark = pytest.mark.gui


@pytest.fixture
def fake():
    return FakeOllama()


@pytest.fixture
def win(qtbot, themed_app, tmp_config, fake, tmp_path):
    repo = SqliteChatRepository.open(tmp_path / "db" / "assistant.db")
    window = MainWindow(tmp_config, store=repo, use_webengine=False,
                        client_factory=lambda: OllamaClient(tmp_config, transport=fake.transport()))
    qtbot.addWidget(window)
    window.resize(1300, 850)
    window.show()
    qtbot.waitUntil(lambda: window.health().state is ConnectionState.CONNECTED, timeout=5000)
    yield window
    window.close()
    repo.close()


@pytest.fixture
def project(win, tmp_path):
    root = tmp_path / "projects" / "calc"
    root.mkdir(parents=True)
    (root / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    (root / "test_calc.py").write_text("from calc import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n",
                                       encoding="utf-8")
    win.store.add_message(win.current_chat_id(), ChatMessage("user", "make calc"))
    win.store.create_project("calc", str(root), win.current_chat_id(), "complete")
    return root


def _errors(window):
    return [w for w in window.chat_view.items if isinstance(w, ErrorCard)]


def test_user_rejection_runs_nothing_and_app_stays_usable(qtbot, win, project, monkeypatch, fake):
    import subprocess

    started = []
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: started.append(a))
    asked = []
    win.approver = lambda command, cwd: asked.append((command, cwd)) or False
    assert win.run_project_tests() is False
    assert asked == [("python -m pytest -q", str(project.resolve()))]
    assert started == []
    assert "You rejected the command, so it was not run" in _errors(win)[-1].label.text()
    assert not win.is_busy()
    with qtbot.waitSignal(win.streamFinished, timeout=10000):
        assert win.submit_prompt("still works?")


def test_command_not_on_allowlist_is_refused_even_if_approved(win, project):
    asked = []
    win.approver = lambda command, cwd: asked.append(command) or True
    for argv in (["cmd", "/c", "dir"], ["powershell", "-c", "ls"], ["python", "-c", "print(1)"],
                 ["python", "-m", "pytest", "&&", "calc"], ["git", "push"]):
        assert win.run_project_command(argv) is False
    assert asked == []  # never even offered for approval
    texts = [card.label.text() for card in _errors(win)]
    assert len(texts) == 5 and all("not on the approved list" in t for t in texts)
    assert not win.is_busy()


def test_approved_tests_run_and_output_is_shown_and_saved(qtbot, win, project):
    win.approver = lambda command, cwd: True
    with qtbot.waitSignal(win.streamFinished, timeout=60000):
        assert win.run_project_tests()
    message = [w for w in win.chat_view.items if isinstance(w, AssistantMessage)][-1]
    assert "Exit code 0" in message.text() and "1 passed" in message.text()
    assert message.status_label.text() == "Checks passed"
    assert win.command_results[-1].ok
    stored = win.store.get_messages(win.current_chat_id())[-1]
    assert stored.role == "assistant" and "Exit code 0" in stored.content


def test_failing_tests_are_reported_as_failed(qtbot, win, project):
    (project / "test_calc.py").write_text("def test_bad():\n    assert 1 == 2\n", encoding="utf-8")
    win.approver = lambda command, cwd: True
    with qtbot.waitSignal(win.streamFinished, timeout=60000):
        win.run_project_tests()
    message = [w for w in win.chat_view.items if isinstance(w, AssistantMessage)][0]
    assert message.status_label.text() == "Checks failed" and "Exit code 1" in message.text()
    assert "Repair round 1 of 3" in message.text()
    stored = [m for m in win.store.get_messages(win.current_chat_id()) if "Exit code 1" in m.content]
    assert stored and stored[0].status == "error"


def test_no_project_means_no_command(win):
    win.approver = lambda command, cwd: pytest.fail("must not ask")
    assert win.run_project_tests() is False
    assert win.toast.isVisible()



def test_restored_tool_runs_show_checks_status_not_the_model(qtbot, win, project, tmp_config, tmp_path):
    """Regression: after a restart, test-run messages showed the model name, and failed runs were
    restored as red error cards with raw Markdown."""
    win.approver = lambda command, cwd: True
    with qtbot.waitSignal(win.streamFinished, timeout=60000):
        win.run_project_tests()  # passes
    (project / "test_calc.py").write_text("def test_bad():\n    assert 1 == 2\n", encoding="utf-8")
    win._repair.clear()
    with qtbot.waitSignal(win.streamFinished, timeout=60000):
        win.run_project_command(["python", "-m", "pytest", "-q"])  # fails, no repair loop
    chat_id = win.current_chat_id()
    kinds = [(m.kind, m.status) for m in win.store.get_messages(chat_id) if m.role == "assistant"]
    assert kinds == [("tool", "complete"), ("tool", "error")]

    win.chat_view.clear()
    win._current_chat_id = None
    win.select_chat(chat_id)  # restore from the database
    restored = [w for w in win.chat_view.items if isinstance(w, AssistantMessage)]
    assert [w.status_label.text() for w in restored] == ["Checks passed", "Checks failed"]
    assert not [w for w in win.chat_view.items if isinstance(w, ErrorCard)]
