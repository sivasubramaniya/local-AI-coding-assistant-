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
