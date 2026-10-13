import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _run(tmp_path, *args, **extra_env):
    env = {k: v for k, v in os.environ.items() if not k.startswith("LAA_")}
    env.update({"LAA_DATA_DIR": str(tmp_path / "data"), "LAA_EXPORT_DIR": str(tmp_path / "export")})
    env.update(extra_env)
    return subprocess.run(
        [sys.executable, str(ROOT / "main.py"), *args],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=60,
    )


UNUSED_LOCAL_URL = "http://127.0.0.1:9"  # nothing listens here: connection refused


def test_check_exits_zero_and_warns_when_ollama_is_down(tmp_path):
    result = _run(tmp_path, "--check", LAA_OLLAMA_URL=UNUSED_LOCAL_URL)
    assert result.returncode == 0, result.stderr
    assert "Local AI Assistant" in result.stdout
    assert "qwen2.5-coder-14b:latest" in result.stdout
    assert "NOT REACHABLE" in result.stdout
    assert "WARNING: Ollama is not running" in result.stdout
    assert "num_ctx=8192" in result.stdout and "keep_alive=10m" in result.stdout
    assert (tmp_path / "data" / "logs" / "app.log").is_file()


def test_check_reports_model_present(tmp_path):
    from tests.fake_ollama import StallingServer

    with StallingServer() as server:
        result = _run(tmp_path, "--check", LAA_OLLAMA_URL=server.url)
    assert result.returncode == 0, result.stderr
    assert "running, version 0.40.2" in result.stdout
    assert "Model present : yes (exact match)" in result.stdout
    assert "WARNING" not in result.stdout


def test_check_rejects_remote_url(tmp_path):
    result = _run(tmp_path, "--check", LAA_OLLAMA_URL="https://api.example.com")
    assert result.returncode == 2
    assert "not local" in result.stderr


@pytest.mark.gui
def test_screenshot_mode_saves_image_and_exits_zero(tmp_path):
    shot = tmp_path / "shot.png"
    result = _run(tmp_path, "--screenshot", str(shot), "--delay", "100", "--no-preview",
                  QT_QPA_PLATFORM="offscreen", LAA_OLLAMA_URL=UNUSED_LOCAL_URL)
    assert result.returncode == 0, result.stderr
    assert shot.is_file() and shot.stat().st_size > 10_000


def test_bad_config_exits_two_without_traceback(tmp_path):
    result = _run(tmp_path, "--check", LAA_LOG_LEVEL="WRONG")
    assert result.returncode == 2
    assert "Configuration error" in result.stderr
    assert "log_level" in result.stderr
    assert "Traceback" not in result.stderr


def test_check_reports_database_without_creating_it(tmp_path):
    result = _run(tmp_path, "--check", LAA_OLLAMA_URL=UNUSED_LOCAL_URL)
    assert result.returncode == 0, result.stderr
    assert "assistant.db" in result.stdout
    assert "DB schema     : not created yet (app supports v4)" in result.stdout
    assert not (tmp_path / "data" / "assistant.db").exists()


def test_check_reports_schema_and_chat_count(tmp_path):
    from app.storage.chat_repository import SqliteChatRepository

    repo = SqliteChatRepository.open(tmp_path / "data" / "assistant.db")
    repo.create_chat()
    repo.close()
    result = _run(tmp_path, "--check", LAA_OLLAMA_URL=UNUSED_LOCAL_URL)
    assert "DB schema     : v4 (app supports v4)" in result.stdout
    assert "Chats         : 1" in result.stdout


@pytest.mark.gui
def test_screenshot_demo_mode_never_creates_the_database(tmp_path):
    shot = tmp_path / "shot.png"
    result = _run(tmp_path, "--screenshot", str(shot), "--delay", "50", "--no-preview",
                  QT_QPA_PLATFORM="offscreen", LAA_OLLAMA_URL=UNUSED_LOCAL_URL)
    assert result.returncode == 0, result.stderr
    assert not (tmp_path / "data" / "assistant.db").exists()


def test_open_history_store_choices(tmp_config):
    import main as entry
    from app.backend.memory_store import InMemoryChatStore
    from app.storage.chat_repository import SqliteChatRepository

    db = tmp_config.db_path
    db.parent.mkdir(parents=True)
    db.write_bytes(b"garbage" * 500)
    asked = []

    def choose_fresh(message, offer_fresh):
        asked.append((message, offer_fresh))
        return "fresh"

    store = entry.open_history_store(tmp_config, choose_fresh)
    assert isinstance(store, SqliteChatRepository)
    store.close()
    assert asked[0][1] is True and ".corrupt-" in asked[0][0]
    backups = list(db.parent.glob("assistant.db.corrupt-*"))
    assert len(backups) == 1 and backups[0].read_bytes() == b"garbage" * 500

    # a newer schema: no fresh option, file untouched; the user picks "continue without saving"
    store = SqliteChatRepository.open(db)
    store._conn.execute("INSERT INTO schema_version (version, applied_at) VALUES (7, 'x')")
    store.close()
    before = db.read_bytes()
    seen = []
    memory = entry.open_history_store(tmp_config, lambda m, fresh: seen.append(fresh) or "memory")
    assert isinstance(memory, InMemoryChatStore) and seen == [False]
    assert db.read_bytes() == before
    assert entry.open_history_store(tmp_config, lambda m, fresh: "quit") is None


def test_attach_console_is_a_no_op_from_source():
    import main as entry

    assert entry.attach_parent_console() is False


def test_check_reports_both_models_and_optional_fast(tmp_path):
    from tests.fake_ollama import StallingServer

    with StallingServer() as server:  # lists only the default model
        result = _run(tmp_path, "--check", LAA_OLLAMA_URL=server.url)
    assert "Model         : qwen2.5-coder-14b:latest (default, Quality)" in result.stdout
    assert "Fast model    : qwen2.5-coder-7b:latest (optional" in result.stdout
    assert "Fast present  : no" in result.stdout
    assert r"ollama create qwen2.5-coder-7b -f .\ollama\Modelfile.fast" in result.stdout
    assert "WARNING" not in result.stdout  # the fast model is optional
