import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _run(tmp_path, *args, **extra_env):
    env = {k: v for k, v in os.environ.items() if not k.startswith("LAA_")}
    env.update({"LAA_DATA_DIR": str(tmp_path / "data"), "LAA_EXPORT_DIR": str(tmp_path / "export")})
    env.update(extra_env)
    return subprocess.run(
        [sys.executable, str(ROOT / "main.py"), *args],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=60,
    )


def test_check_exits_zero(tmp_path):
    result = _run(tmp_path, "--check")
    assert result.returncode == 0, result.stderr
    assert "Local AI Assistant" in result.stdout
    assert "qwen2.5-coder-14b:latest" in result.stdout
    assert (tmp_path / "data" / "logs" / "app.log").is_file()


def test_plain_start_exits_zero(tmp_path):
    result = _run(tmp_path)
    assert result.returncode == 0, result.stderr


def test_bad_config_exits_two_without_traceback(tmp_path):
    result = _run(tmp_path, "--check", LAA_LOG_LEVEL="WRONG")
    assert result.returncode == 2
    assert "Configuration error" in result.stderr
    assert "log_level" in result.stderr
    assert "Traceback" not in result.stderr
