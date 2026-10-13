"""Fast mode (optional 7B model): explicit, per chat, persistent, never a silent fallback. MOCK model."""

import json
import logging

import pytest

from app.backend.ollama_client import OllamaClient, create_command
from app.backend.status import ConnectionState
from app.config import DEFAULT_FAST_MODEL_NAME, DEFAULT_MODEL_NAME, load_config
from app.errors import ConfigError
from app.storage.chat_repository import SqliteChatRepository
from app.ui.agent_widgets import FAST_PLAN_NOTE, PlanCard
from app.ui.main_window import DEFAULT_MODEL_MODE_SETTING, MainWindow
from app.ui.message_widgets import AssistantMessage, ErrorCard
from tests.fake_ollama import FakeOllama

QUALITY = "qwen2.5-coder-14b:latest"
FAST = "qwen2.5-coder-7b:latest"
FAST_CMD = r"ollama create qwen2.5-coder-7b -f .\ollama\Modelfile.fast"


def _env(tmp_path, **extra):
    return {"LAA_DATA_DIR": str(tmp_path / "d"), "LAA_EXPORT_DIR": str(tmp_path / "e"), **extra}


# --- config and client ------------------------------------------------------------------
def test_config_defaults_and_validation(tmp_path, caplog):
    config = load_config(_env(tmp_path))
    assert (config.model_name, config.fast_model_name) == (DEFAULT_MODEL_NAME, DEFAULT_FAST_MODEL_NAME)
    assert (QUALITY, FAST) == (DEFAULT_MODEL_NAME, DEFAULT_FAST_MODEL_NAME)
    with caplog.at_level(logging.WARNING, logger="app.config"):
        overridden = load_config(_env(tmp_path, LAA_FAST_MODEL_NAME="my-fast:latest"))
    assert overridden.fast_model_name == "my-fast:latest"
    assert any("LAA_FAST_MODEL_NAME" in r.getMessage() for r in caplog.records)
    for bad in (QUALITY, " ", "two words"):
        with pytest.raises(ConfigError):
            load_config(_env(tmp_path, LAA_FAST_MODEL_NAME=bad))


def test_client_sends_only_its_model_and_fast_create_command(tmp_path):
    config = load_config(_env(tmp_path))
    fake = FakeOllama(models=[QUALITY, FAST])
    with OllamaClient(config, transport=fake.transport(), model=FAST) as client:
        assert "".join(client.stream_chat([{"role": "user", "content": "hi"}]))
    assert fake.chat_bodies()[-1]["model"] == FAST
    assert create_command(config, FAST) == FAST_CMD
    assert create_command(config) == r"ollama create qwen2.5-coder-14b -f .\ollama\Modelfile"
    with OllamaClient(config, transport=FakeOllama(models=[QUALITY, FAST]).transport()) as client:
        version, models = client.check_models()
    assert version and models == {QUALITY: True, FAST: True}


# --- window ---------------------------------------------------------------------------------


@pytest.fixture
def fake():
    return FakeOllama(models=[QUALITY, FAST])


@pytest.fixture
def session(qtbot, themed_app, tmp_config, fake, tmp_path):
    opened = []

    def start():
        repo = SqliteChatRepository.open(tmp_path / "db" / "assistant.db")
        win = MainWindow(tmp_config, store=repo, use_webengine=False,
                         client_factory=lambda: OllamaClient(tmp_config, transport=fake.transport()))
        qtbot.addWidget(win)
        win.show()
        qtbot.waitUntil(lambda: win.health().state is not ConnectionState.CHECKING, timeout=5000)
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


def _send(qtbot, win, text):
    with qtbot.waitSignal(win.streamFinished, timeout=10000):
        assert win.submit_prompt(text)


def _assistants(win):
    return [w for w in win.chat_view.items if isinstance(w, AssistantMessage)]


@pytest.mark.gui
def test_quality_is_the_default(qtbot, session, fake):
    win = session()
    assert win.selected_model() == QUALITY and not win.composer.fast_mode()
    assert win.composer.model_chip.text() == "Quality (14B)"
    assert win.sidebar.status_card.model_text() == "qwen2.5-coder-14b"
    _send(qtbot, win, "write a function")
    assert fake.chat_bodies()[-1]["model"] == QUALITY


@pytest.mark.gui
def test_toggle_sends_fast_model_and_stats_show_it(qtbot, session, fake):
    win = session()
    win.composer.model_chip.click()
    assert win.composer.model_chip.text() == "Fast (7B)" and win.selected_model() == FAST
    assert win.sidebar.status_card.model_text() == "qwen2.5-coder-7b"
    assert win.health().state is ConnectionState.CONNECTED
    _send(qtbot, win, "write a function")
    assert fake.chat_bodies()[-1]["model"] == FAST
    assert _assistants(win)[-1].status_label.text() == "qwen2.5-coder-7b · 42 tokens · 21.0 tok/s"
    stored = win.store.get_messages(win.current_chat_id())[-1]
    assert stored.model_name == FAST
    assert win.store.get_chat(win.current_chat_id()).model_name == FAST


@pytest.mark.gui
def test_selection_persists_per_chat_across_restart(qtbot, session, fake):
    win = session()
    _send(qtbot, win, "quality question")
    quality_chat = win.current_chat_id()
    win.new_chat()
    win.composer.model_chip.click()
    _send(qtbot, win, "fast question")
    fast_chat = win.current_chat_id()

    win2 = session.restart(win)
    assert win2.current_chat_id() == fast_chat and win2.composer.fast_mode()
    assert _assistants(win2)[-1].status_label.text().startswith("qwen2.5-coder-7b")
    win2.select_chat(quality_chat)
    assert not win2.composer.fast_mode() and win2.selected_model() == QUALITY
    assert _assistants(win2)[-1].status_label.text().startswith("qwen2.5-coder-14b")
    _send(qtbot, win2, "again")
    assert fake.chat_bodies()[-1]["model"] == QUALITY
    win2.select_chat(fast_chat)
    _send(qtbot, win2, "again fast")
    assert fake.chat_bodies()[-1]["model"] == FAST


@pytest.mark.gui
def test_missing_fast_model_is_amber_with_command_and_never_falls_back(qtbot, session, fake):
    fake.models = [QUALITY]
    win = session()
    assert win.health().state is ConnectionState.CONNECTED  # Quality is fine
    win.composer.model_chip.click()
    card = win.sidebar.status_card
    assert win.health().state is ConnectionState.MODEL_MISSING
    assert card.status_text() == "Ollama · Model missing"
    assert FAST_CMD in win.health().message
    win.submit_prompt("hello")
    errors = [w for w in win.chat_view.items if isinstance(w, ErrorCard)]
    assert errors and FAST_CMD in errors[-1].label.text()
    assert fake.chat_bodies() == []  # no request at all: not to 7B, and never to 14B instead
    win.composer.model_chip.click()  # back to Quality explicitly
    assert win.health().state is ConnectionState.CONNECTED


@pytest.mark.gui
def test_missing_quality_model_while_fast_is_selected_still_works(qtbot, session, fake):
    fake.models = [FAST]
    win = session()
    assert win.health().state is ConnectionState.MODEL_MISSING  # default chat uses Quality
    win.composer.model_chip.click()
    assert win.health().state is ConnectionState.CONNECTED
    _send(qtbot, win, "write a function")
    assert [b["model"] for b in fake.chat_bodies()] == [FAST]


@pytest.mark.gui
def test_health_checks_both_models_with_tags_only(qtbot, session, fake):
    win = session()
    for _ in range(2):
        with qtbot.waitSignal(win.healthChecked, timeout=5000) as blocker:
            win.check_health()
    assert blocker.args[0].models == {QUALITY: True, FAST: True}
    assert set(fake.paths()) <= {"/api/version", "/api/tags"}


@pytest.mark.gui
def test_settings_default_applies_to_new_chats_only(qtbot, session, fake, tmp_path):
    win = session()
    _send(qtbot, win, "a quality chat")
    first = win.current_chat_id()
    win.settings_editor = lambda export_dir, timeout: (str(tmp_path / "x"), 60, True)
    win.open_settings()
    assert win.store.get_setting(DEFAULT_MODEL_MODE_SETTING) == "fast"
    other = win.new_chat()
    assert win.composer.fast_mode() and win.selected_model() == FAST
    assert win.store.get_chat(other).model_name == FAST
    win.select_chat(first)  # existing chats keep their own choice
    assert not win.composer.fast_mode() and win.store.get_chat(first).model_name == QUALITY
    win2 = session.restart(win)
    assert win2.store.get_setting(DEFAULT_MODEL_MODE_SETTING) == "fast"
    assert win2.new_chat() and win2.composer.fast_mode()


@pytest.mark.gui
def test_fast_mode_plan_card_note(qtbot, session, fake):
    plan = json.dumps({"project_name": "t", "description": "d", "language": "Python",
                       "files": [{"path": "a.py", "purpose": "x"}], "run_instructions": "", "test_command": ""})
    win = session()
    win.composer.model_chip.click()
    fake.replies = [plan]
    with qtbot.waitSignal(win.streamFinished, timeout=10000):
        win.submit_prompt("make a tool", project_mode=True)
    card = [w for w in win.chat_view.items if isinstance(w, PlanCard)][-1]
    assert card.fast_note is not None and card.fast_note.text() == FAST_PLAN_NOTE
    assert fake.chat_bodies()[-1]["model"] == FAST
    win.composer.model_chip.click()
    fake.replies = [plan]
    with qtbot.waitSignal(win.streamFinished, timeout=10000):
        win.submit_prompt("make another tool", project_mode=True)
    assert [w for w in win.chat_view.items if isinstance(w, PlanCard)][-1].fast_note is None
