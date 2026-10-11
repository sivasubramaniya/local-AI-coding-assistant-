"""Window <-> Ollama wiring, using a scripted fake Ollama (no real network)."""

import time

import pytest
from PySide6.QtCore import QTimer

from app.backend.ollama_client import OllamaClient
from app.backend.status import ConnectionState
from app.prompts import load_system_prompt
from app.ui import theme
from app.ui.main_window import STATUS_STOPPED, MainWindow
from app.ui.message_widgets import AssistantMessage, ErrorCard, UserBubble
from tests.fake_ollama import FakeOllama

pytestmark = pytest.mark.gui

CREATE_CMD = r"ollama create qwen2.5-coder-14b -f .\ollama\Modelfile"


@pytest.fixture
def fake():
    return FakeOllama()


@pytest.fixture
def make_window(qtbot, themed_app, tmp_config, fake):
    def factory(**kwargs):
        win = MainWindow(
            tmp_config,
            use_webengine=False,
            client_factory=lambda: OllamaClient(tmp_config, transport=fake.transport()),
            **kwargs,
        )
        qtbot.addWidget(win)
        win.resize(1300, 850)
        win.show()
        return win

    return factory


def _wait_health(qtbot, win, state):
    qtbot.waitUntil(lambda: win.health().state is state, timeout=5000)


def _assistants(win):
    return [w for w in win.chat_view.items if isinstance(w, AssistantMessage)]


def _errors(win):
    return [w for w in win.chat_view.items if isinstance(w, ErrorCard)]


def test_normal_launch_is_not_demo(make_window):
    win = make_window()
    assert not win.demo_mode
    assert win.chat_view.items == []
    assert win.preview.files() == []


def test_send_streams_tokens_and_shows_stats(qtbot, make_window, fake):
    win = make_window()
    _wait_health(qtbot, win, ConnectionState.CONNECTED)
    assert win.sidebar.status_card.status_text() == "Ollama · Connected"
    with qtbot.waitSignal(win.streamFinished, timeout=10000):
        assert win.submit_prompt("say hello")
    assistant = _assistants(win)[0]
    assert assistant.text() == "Hello from the model."
    assert assistant.status_label.text() == "qwen2.5-coder-14b · 42 tokens · 21.0 tok/s"
    body = fake.chat_bodies()[-1]
    assert body["messages"][0] == {"role": "system", "content": load_system_prompt()}
    assert body["messages"][-1] == {"role": "user", "content": "say hello"}
    assert body["stream"] is True and body["options"]["num_ctx"] == 8192
    stored = win.store.get(win.current_chat_id()).messages
    assert [m.role for m in stored] == ["user", "assistant"]


def test_status_line_loading_then_generating(qtbot, make_window, fake):
    fake.tokens = [f"w{i} " for i in range(40)]
    fake.chunk_delay_s = 0.03
    win = make_window()
    _wait_health(qtbot, win, ConnectionState.CONNECTED)
    win.submit_prompt("go")
    assistant = _assistants(win)[0]
    assert assistant.status_label.text() == "Loading model…"
    qtbot.waitUntil(lambda: assistant.status_label.text() == "Generating…", timeout=5000)
    with qtbot.waitSignal(win.streamFinished, timeout=10000):
        pass


def test_disconnected_shows_error_card_and_retry_recovers(qtbot, make_window, fake):
    fake.down = True
    win = make_window()
    _wait_health(qtbot, win, ConnectionState.DISCONNECTED)
    assert win.sidebar.status_card.status_text() == "Ollama · Disconnected"
    win.submit_prompt("hello?")
    cards = _errors(win)
    assert len(cards) == 1
    assert "Ollama is not running at http://localhost:11434" in cards[0].label.text()
    assert isinstance(win.chat_view.items[0], UserBubble)
    assert "/api/chat" not in fake.paths()

    fake.down = False  # Ollama comes back
    with qtbot.waitSignal(win.streamFinished, timeout=10000):
        cards[0].retry_button.click()
    assert win.health().state is ConnectionState.CONNECTED
    assert _errors(win) == []
    assert _assistants(win)[0].text() == "Hello from the model."
    stored = win.store.get(win.current_chat_id()).messages
    assert [m.role for m in stored] == ["user", "assistant"]  # the question was not duplicated


def test_model_missing_amber_status_and_create_command(qtbot, make_window, fake):
    fake.models = ["qwen2.5-coder:14b"]
    win = make_window()
    _wait_health(qtbot, win, ConnectionState.MODEL_MISSING)
    card = win.sidebar.status_card
    assert card.status_text() == "Ollama · Model missing"
    assert theme.WARNING in card.dot.styleSheet()
    win.submit_prompt("hi")
    text = _errors(win)[0].label.text()
    assert CREATE_CMD in text and "from the project folder" in text
    assert "qwen2.5-coder:14b" in text  # mentioned as similar...
    assert "/api/chat" not in fake.paths()  # ...but never used: no fallback


def test_stop_keeps_partial_marks_stopped_and_restores_send(qtbot, make_window, fake):
    fake.tokens = [f"part{i} " for i in range(300)]
    fake.chunk_delay_s = 0.02
    win = make_window()
    _wait_health(qtbot, win, ConnectionState.CONNECTED)
    win.submit_prompt("long answer")
    assistant = _assistants(win)[0]
    qtbot.waitUntil(lambda: len(assistant.text()) > 20, timeout=5000)
    started = time.monotonic()
    win.stop_generation()
    assert time.monotonic() - started < 1.0
    assert not win.is_busy()
    assert win.composer.send_button.toolTip().startswith("Send")
    assert assistant.status_label.text() == STATUS_STOPPED
    assert assistant.text().startswith("part0 ") and len(assistant.text()) < len("".join(fake.tokens))
    last = win.store.get(win.current_chat_id()).messages[-1]
    assert last.role == "assistant" and last.status == STATUS_STOPPED
    assert "(stopped)" not in last.content  # the marker is never sent back to the model


def test_ui_timer_keeps_firing_during_stream(qtbot, make_window, fake):
    fake.tokens = [f"t{i} " for i in range(30)]
    fake.chunk_delay_s = 0.02
    win = make_window()
    _wait_health(qtbot, win, ConnectionState.CONNECTED)
    ticks = []
    timer = QTimer()
    timer.timeout.connect(lambda: ticks.append(1))
    timer.start(10)
    with qtbot.waitSignal(win.streamFinished, timeout=10000):
        win.submit_prompt("stream")
    timer.stop()
    assert len(ticks) >= 20, f"UI timer fired only {len(ticks)} times in ~0.6 s of streaming"


def test_regenerate_replaces_last_answer(qtbot, make_window, fake):
    win = make_window()
    _wait_health(qtbot, win, ConnectionState.CONNECTED)
    with qtbot.waitSignal(win.streamFinished, timeout=10000):
        win.submit_prompt("question")
    fake.tokens = ["Second", " answer"]
    with qtbot.waitSignal(win.streamFinished, timeout=10000):
        _assistants(win)[0].actions.regenerate_button.click()
    assert [a.text() for a in _assistants(win)] == ["Second answer"]
    bodies = fake.chat_bodies()
    assert len(bodies) == 2
    assert bodies[1]["messages"][0]["role"] == "system"
    assert [m["content"] for m in bodies[1]["messages"][1:]] == ["question"]
    stored = win.store.get(win.current_chat_id()).messages
    assert [(m.role, m.content) for m in stored] == [("user", "question"), ("assistant", "Second answer")]


def test_error_chunk_mid_stream_shows_error_card(qtbot, make_window, fake):
    from tests.fake_ollama import content_line

    fake.raw_chunks = [content_line("Partial "), b'{"error":"CUDA out of memory"}\n']
    win = make_window()
    _wait_health(qtbot, win, ConnectionState.CONNECTED)
    win.submit_prompt("big job")
    qtbot.waitUntil(lambda: bool(_errors(win)), timeout=5000)
    assert _errors(win)[0].label.text() == "Ollama reported an error: CUDA out of memory"
    assert _assistants(win)[0].status_label.text() == "Failed"
    assert not win.is_busy()


def test_send_while_checking_waits_for_health(qtbot, make_window, fake):
    win = make_window()
    # first health check has not finished yet when the user sends
    assert win.health().state is ConnectionState.CHECKING
    with qtbot.waitSignal(win.streamFinished, timeout=10000):
        win.submit_prompt("early question")
    assert _assistants(win)[0].text() == "Hello from the model."


def test_cancel_stream_while_health_check_runs(qtbot, make_window, fake):
    fake.tokens = [f"x{i} " for i in range(300)]
    fake.chunk_delay_s = 0.02
    win = make_window()
    _wait_health(qtbot, win, ConnectionState.CONNECTED)
    win.submit_prompt("slow")
    assistant = _assistants(win)[0]
    qtbot.waitUntil(lambda: bool(assistant.text()), timeout=5000)
    with qtbot.waitSignal(win.healthChecked, timeout=5000) as blocker:
        win.check_health()
        win.stop_generation()
    assert blocker.args[0].state is ConnectionState.CONNECTED
    assert win.health().state is ConnectionState.CONNECTED


def test_health_checks_never_call_chat_or_generate(qtbot, make_window, fake):
    win = make_window()
    for _ in range(3):
        with qtbot.waitSignal(win.healthChecked, timeout=5000):
            win.check_health()
    paths = fake.paths()
    assert paths and set(paths) <= {"/api/version", "/api/tags"}
