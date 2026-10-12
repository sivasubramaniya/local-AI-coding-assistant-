"""MOCK model: generate -> run tests -> fail -> model fix as diff -> apply -> re-run (max 3 rounds).

The tests run for real (python -m pytest in a tmp project); only the model is mocked.
"""

import pytest

from app.agent.tool_runner import (
    CommandResult,
    default_test_commands,
    java_test_classes,
    results_markdown,
    trimmed_failure_output,
)
from app.backend.chat_store import ChatMessage
from app.backend.ollama_client import OllamaClient
from app.backend.status import ConnectionState
from app.prompts import load_system_prompt
from app.storage.chat_repository import SqliteChatRepository
from app.ui.agent_widgets import ChangesCard
from app.ui.main_window import MAX_REPAIR_ROUNDS, MainWindow
from app.ui.message_widgets import AssistantMessage
from tests.fake_ollama import FakeOllama

BUGGY = "def add(a, b):\n    return a - b\n"
FIXED = "def add(a, b):\n    return a + b\n"
TEST = "from calc import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n"
FIX_REPLY = "The operator is wrong.\n```python path=calc.py\n" + FIXED + "```"
WRONG_FIX_REPLY = "Try this.\n```python path=calc.py\ndef add(a, b):\n    return a * b\n```"


# --- pure helpers ---------------------------------------------------------------------
def test_java_detection(tmp_path):
    src = tmp_path / "src" / "calc"
    src.mkdir(parents=True)
    (src / "Calculator.java").write_text("package calc;\npublic class Calculator {}\n")
    (src / "CalculatorTest.java").write_text(
        "package calc;\npublic class CalculatorTest {\n  public static void main(String[] a) {}\n}\n")
    (src / "TestNoMain.java").write_text("package calc;\nclass TestNoMain {}\n")
    (tmp_path / "out").mkdir()
    (tmp_path / "out" / "Stale.java").write_text("class Stale {}")
    assert java_test_classes(tmp_path) == ["calc.CalculatorTest"]
    commands = default_test_commands(tmp_path)
    assert commands[0][:5] == ["javac", "-encoding", "UTF-8", "-d", "out"]
    assert "out/Stale.java" not in commands[0]
    assert commands[1] == ["java", "-cp", "out", "calc.CalculatorTest"]


def test_trimmed_failure_output_keeps_the_end(tmp_path):
    long = "noise\n" * 5000 + "AssertionError: 1 != 2"
    results = [CommandResult(("python", "-m", "pytest"), tmp_path, 1, long, "", False, 1.0)]
    text = trimmed_failure_output(results, 500)
    assert "AssertionError: 1 != 2" in text and "earlier output omitted" in text and len(text) < 700
    assert "exit code 1" in text


def test_results_markdown_mentions_skipped_steps(tmp_path):
    failed = CommandResult(("javac", "A.java"), tmp_path, 1, "", "error: ';' expected", False, 0.5)
    text = results_markdown([failed], planned=2)
    assert "error: ';' expected" in text and "1 later command(s) were not run" in text


# --- the loop in the window -----------------------------------------------------------------


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
    window.approver = lambda command, cwd: True
    yield window
    window.close()
    repo.close()


@pytest.fixture
def project(win, tmp_path):
    root = tmp_path / "projects" / "calc"
    root.mkdir(parents=True)
    (root / "calc.py").write_text(BUGGY, encoding="utf-8")
    (root / "test_calc.py").write_text(TEST, encoding="utf-8")
    (root / "README.md").write_text("# Calc\n", encoding="utf-8")
    win.store.add_message(win.current_chat_id(), ChatMessage("user", "make calc"))
    win.store.create_project("calc", str(root), win.current_chat_id(), "complete")
    return root


def _assistants(win):
    return [w for w in win.chat_view.items if isinstance(w, AssistantMessage)]


def _cards(win):
    return [w for w in win.chat_view.items if isinstance(w, ChangesCard)]


@pytest.mark.gui
def test_failing_tests_are_repaired_in_one_round(qtbot, win, project, fake):
    fake.replies = [FIX_REPLY]
    with qtbot.waitSignal(win.streamFinished, timeout=60000):
        win.run_project_tests()  # pytest fails for real
    qtbot.waitUntil(lambda: bool(_cards(win)), timeout=20000)  # repair round 1 answered
    assert win.repair_round(win.current_chat_id()) == 1
    first = _assistants(win)[0].text()
    assert "Exit code 1" in first and "Repair round 1 of 3" in first

    repair_request = fake.chat_bodies()[-1]["messages"]
    assert repair_request[0] == {"role": "system", "content": load_system_prompt()}
    latest = repair_request[-1]["content"]
    assert latest.startswith("Repair round 1/3") and "assert" in latest and "File calc.py:" in latest

    card = _cards(win)[-1]
    assert "+    return a + b" in card.diff_view.toPlainText()
    assert (project / "calc.py").read_text() == BUGGY  # nothing written before Apply
    with qtbot.waitSignal(win.streamFinished, timeout=60000):
        card.apply_button.click()  # applies, then re-runs the tests (approved again)
    assert (project / "calc.py").read_text() == FIXED
    final = _assistants(win)[-1].text()
    assert "1 passed" in final and "All checks passed after 1 repair round" in final
    assert win.repair_round(win.current_chat_id()) == 0  # loop finished


@pytest.mark.gui
def test_loop_stops_after_three_rounds(qtbot, win, project, fake):
    fake.replies = [WRONG_FIX_REPLY.replace("a * b", f"a * b + {i}") for i in range(MAX_REPAIR_ROUNDS)]
    with qtbot.waitSignal(win.streamFinished, timeout=60000):
        win.run_project_tests()
    for round_no in range(1, MAX_REPAIR_ROUNDS + 1):
        qtbot.waitUntil(lambda n=round_no: len(_cards(win)) >= n, timeout=20000)
        with qtbot.waitSignal(win.streamFinished, timeout=60000):
            _cards(win)[-1].apply_button.click()
    final = _assistants(win)[-1].text()
    assert f"Stopped after {MAX_REPAIR_ROUNDS} repair rounds" in final
    qtbot.wait(300)
    assert len(_cards(win)) == MAX_REPAIR_ROUNDS and not win.is_busy()
    assert len(fake.chat_bodies()) == MAX_REPAIR_ROUNDS  # no 4th model call
    assert len(list(project.glob("calc.py.bak-*"))) == MAX_REPAIR_ROUNDS


@pytest.mark.gui
def test_cancel_fix_ends_the_loop(qtbot, win, project, fake):
    fake.replies = [FIX_REPLY]
    with qtbot.waitSignal(win.streamFinished, timeout=60000):
        win.run_project_tests()
    qtbot.waitUntil(lambda: bool(_cards(win)), timeout=20000)
    _cards(win)[-1].cancel_button.click()
    assert win.repair_round(win.current_chat_id()) == 0
    assert (project / "calc.py").read_text() == BUGGY


@pytest.mark.gui
def test_rejecting_the_rerun_ends_the_loop(qtbot, win, project, fake):
    fake.replies = [FIX_REPLY]
    with qtbot.waitSignal(win.streamFinished, timeout=60000):
        win.run_project_tests()
    qtbot.waitUntil(lambda: bool(_cards(win)), timeout=20000)
    win.approver = lambda command, cwd: False
    _cards(win)[-1].apply_button.click()
    qtbot.wait(200)
    assert win.repair_round(win.current_chat_id()) == 0 and not win.is_busy()
    assert (project / "calc.py").read_text() == FIXED  # the confirmed fix was applied; tests just not re-run


@pytest.mark.gui
def test_no_usable_fix_ends_the_loop(qtbot, win, project, fake):
    fake.replies = ["I am not sure what is wrong."]
    with qtbot.waitSignal(win.streamFinished, timeout=60000):
        win.run_project_tests()
    qtbot.waitUntil(lambda: len(fake.chat_bodies()) == 1 and not win.is_busy(), timeout=20000)
    qtbot.wait(200)
    assert win.repair_round(win.current_chat_id()) == 0
    assert "did not propose a usable fix" in win.toast.text()
