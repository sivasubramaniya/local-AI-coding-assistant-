"""REAL end-to-end app test: the real window, the real local model, real files and processes.

Run with:  python -m pytest -m integration tests/test_integration_app.py -v -s
Takes 15–30 minutes on a CPU-heavy machine. Skips if Ollama or the exact model is missing.
Screenshots of each state are written to docs/screenshots/.

The steps share one window and one database (tmp_path), in order:
chat + highlight -> stop -> project mode (plan, apply, preview, validator, tests/repair)
-> export ZIP -> restart persistence.
"""

from __future__ import annotations

import ast
import time
from pathlib import Path

import pytest

from app.backend.ollama_client import OllamaClient
from app.backend.status import ConnectionState
from app.config import load_config
from app.errors import AppError
from app.storage.chat_repository import SqliteChatRepository
from app.ui.agent_widgets import ChangesCard, ExportCard, PlanCard
from app.ui.main_window import STATUS_STOPPED, MainWindow
from app.ui.markdown_render import render_markdown
from app.ui.message_widgets import AssistantMessage

pytestmark = [pytest.mark.integration, pytest.mark.gui]

ROOT = Path(__file__).resolve().parent.parent
SHOTS = ROOT / "docs" / "screenshots"
MODEL_WAIT_MS = 20 * 60 * 1000
PROJECT_REQUEST = "Create a simple Python to-do CLI app with tests"


def _assistants(win):
    return [w for w in win.chat_view.items if isinstance(w, AssistantMessage)]


def _cards(win, kind):
    return [w for w in win.chat_view.items if isinstance(w, kind)]


def _shot(win, name: str) -> None:
    from PySide6.QtTest import QTest

    SHOTS.mkdir(parents=True, exist_ok=True)
    # Let the layout settle first: after the preview opens, long answers re-wrap one level per
    # event-loop pass (measured: up to 3 passes), so a capture taken earlier shows a transient overlap.
    QTest.qWait(400)
    win.repaint()
    assert win.grab().save(str(SHOTS / name)), f"could not save {name}"


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("realapp")
    config = load_config({"LAA_DATA_DIR": str(tmp / "data"), "LAA_EXPORT_DIR": str(tmp / "export"),
                          "LAA_STREAM_READ_TIMEOUT_S": "900", "LAA_COMMAND_TIMEOUT_S": "300"})
    with OllamaClient(config) as client:
        try:
            client.ensure_ready()
        except AppError as exc:
            pytest.skip(f"real model not available: {exc.message}")
    return {"config": config, "tmp": tmp, "db": config.db_path}


@pytest.fixture(scope="module")
def app_state(env, qapp):
    from app.ui.theme import apply_theme

    apply_theme(qapp)
    state = {"win": None, "repo": None}

    def open_window():
        repo = SqliteChatRepository.open(env["db"])
        win = MainWindow(env["config"], store=repo, use_webengine=False)
        win.resize(1600, 900)
        win.show()
        win.approver = lambda command, cwd: True  # the test approves the allowlisted commands
        state.update(win=win, repo=repo)
        return win

    state["open"] = open_window
    yield state
    if state["win"] is not None:
        state["win"].close()
        state["repo"].close()


def _ready(qtbot, win):
    qtbot.waitUntil(lambda: win.health().state is ConnectionState.CONNECTED, timeout=60000)


def test_1_streaming_answer_with_highlighted_python(qtbot, app_state):
    win = app_state["open"]()
    _ready(qtbot, win)
    _shot(win, "01-empty.png")
    tokens: list[str] = []
    win.submit_prompt("Write a binary search in Python")
    assistant = _assistants(win)[0]
    qtbot.waitUntil(lambda: len(assistant.text()) > 40, timeout=MODEL_WAIT_MS)
    tokens.append(assistant.text())
    _shot(win, "02-streaming.png")
    with qtbot.waitSignal(win.streamFinished, timeout=MODEL_WAIT_MS):
        pass
    final = assistant.text()
    assert len(final) > len(tokens[0]), "the answer did not keep streaming after the first tokens"
    blocks = assistant.browser.code_blocks
    assert blocks, f"no code block in the answer: {final[:300]!r}"
    tree = ast.parse(blocks[0])
    assert any(isinstance(n, ast.FunctionDef) for n in ast.walk(tree))
    assert "color:" in render_markdown(final).html  # Pygments highlighting
    assert assistant.status_label.text().startswith("qwen2.5-coder-14b · ")
    _shot(win, "03-answer.png")


def test_2_stop_keeps_partial_answer(qtbot, app_state):
    win = app_state["win"]
    win.submit_prompt("Explain in detail, with several long code examples, how Python generators work.")
    assistant = _assistants(win)[-1]
    qtbot.waitUntil(lambda: len(assistant.text()) > 60, timeout=MODEL_WAIT_MS)
    win.composer.send_button.click()  # Send is a Stop button while generating
    qtbot.waitUntil(lambda: not win.is_busy(), timeout=10000)
    assert assistant.status_label.text() == STATUS_STOPPED
    assert win.composer.send_button.toolTip().startswith("Send")
    stored = win.store.get_messages(win.current_chat_id())[-1]
    assert stored.status == "stopped" and stored.content and stored.content == assistant.text()
    _shot(win, "04-stopped.png")


def _drive_repair_loop(qtbot, win, deadline: float) -> str:
    """Approve fixes until the checks pass or the loop ends. Returns the last tool message text."""
    applied = 0
    while time.monotonic() < deadline:
        def settled():
            open_cards = [c for c in _cards(win, ChangesCard) if c.is_open()]
            return bool(open_cards) or (not win.is_busy() and win.repair_round(win.current_chat_id()) == 0)

        qtbot.waitUntil(settled, timeout=MODEL_WAIT_MS)
        open_cards = [c for c in _cards(win, ChangesCard) if c.is_open()]
        if not open_cards:
            break
        applied += 1
        open_cards[-1].apply_button.click()  # apply the model's fix; the loop re-runs the tests
        qtbot.wait(500)
    checks = [a.text() for a in _assistants(win) if "Exit code" in a.text() or "timed out" in a.text()]
    return checks[-1] if checks else ""


def test_3_project_mode_generates_validates_and_tests(qtbot, app_state, env):
    win = app_state["win"]
    win.new_chat()
    win.composer.project_chip.setChecked(True)
    win.composer.input.setPlainText(PROJECT_REQUEST)
    with qtbot.waitSignal(win.streamFinished, timeout=MODEL_WAIT_MS):
        assert win.composer.submit()
    win.composer.project_chip.setChecked(False)
    plans = _cards(win, PlanCard)
    assert plans, f"no plan card; last answer: {_assistants(win)[-1].text()[:300]!r}"
    plan = plans[-1].plan
    _shot(win, "05-plan-card.png")

    with qtbot.waitSignal(win.streamFinished, timeout=MODEL_WAIT_MS * 2):
        plans[-1].apply_button.click()
    summary = _assistants(win)[-1].text()
    project = win.store.latest_project_for_chat(win.current_chat_id())
    assert project is not None and project.status in ("complete", "partial"), summary
    root = Path(project.path)
    assert root.is_relative_to(env["config"].projects_dir.resolve())
    written = [f.path for f in plan.files if (root / f.path).is_file()]
    assert written, summary
    assert win.is_preview_open() and set(written) <= set(win.preview.files())
    assert "Project check passed." in summary, summary
    _shot(win, "06-generated-preview.png")

    assert win.run_project_tests(), "the project has no tests the app can run"
    last_check = _drive_repair_loop(qtbot, win, time.monotonic() + 3600)
    app_state["checks"] = last_check
    _shot(win, "07-tests.png")
    assert "All checks passed" in last_check, f"tests still fail after the repair loop:\n{last_check[-1500:]}"


def test_4_export_zip_is_verified(qtbot, app_state, env):
    win = app_state["win"]
    target = env["tmp"] / "zips"
    win.folder_chooser = lambda start: str(target)
    with qtbot.waitSignal(win.exportFinished, timeout=60000) as blocker:
        win.export_zip_action.trigger()
    result = blocker.args[0]
    assert getattr(result, "verified", False), result
    assert result.destination.is_file() and result.destination.parent == target
    assert _cards(win, ExportCard)
    _shot(win, "08-export.png")


def test_5_restart_restores_chat_and_project(qtbot, app_state):
    win = app_state["win"]
    chat_id = win.current_chat_id()
    titles = win.sidebar.chat_titles()
    project_names = [p.name for p in win.store.list_projects()]
    win.close()
    app_state["repo"].close()
    win2 = app_state["open"]()
    _ready(qtbot, win2)
    assert win2.current_chat_id() == chat_id
    assert win2.sidebar.chat_titles() == titles and len(titles) == 2
    assert [p.name for p in win2.store.list_projects()] == project_names
    restored = _assistants(win2)
    assert any(a.file_cards for a in restored), "file cards were not restored"
    assert win2.preview.files(), "the project files were not loaded into the preview"
    win2.open_file(win2.preview.files()[0])
    _shot(win2, "09-restored.png")
