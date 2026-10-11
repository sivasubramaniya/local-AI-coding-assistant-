import dataclasses
import logging
from pathlib import Path

import pytest

from app.config import (
    DEFAULT_MODEL_NAME,
    AppConfig,
    default_data_dir,
    ensure_directories,
    load_config,
)
from app.errors import ConfigError


@pytest.fixture
def base_env(tmp_path):
    """Isolated environment: never touches the real user folders."""
    return {"LAA_DATA_DIR": str(tmp_path / "data"), "LAA_EXPORT_DIR": str(tmp_path / "export")}


def test_defaults(base_env, tmp_path):
    config = load_config(base_env)
    assert config.app_name == "Local AI Assistant"
    assert config.model_name == "qwen2.5-coder-14b:latest"
    assert config.ollama_url == "http://localhost:11434"
    assert config.request_timeout_s == 120
    assert config.connect_timeout_s == 5
    assert config.temperature == 0.2
    assert config.top_p == 0.8
    assert config.num_ctx == 8192
    assert config.log_level == "INFO"
    data = tmp_path / "data"
    assert config.data_dir == data
    assert config.db_path == data / "assistant.db"
    assert config.logs_dir == data / "logs"
    assert config.projects_dir == data / "projects"
    assert config.export_dir == tmp_path / "export"


def test_config_is_frozen(base_env):
    config = load_config(base_env)
    with pytest.raises(dataclasses.FrozenInstanceError):
        config.model_name = "other"  # type: ignore[misc]


def test_default_data_dir_uses_localappdata(tmp_path):
    assert default_data_dir({"LOCALAPPDATA": str(tmp_path)}) == tmp_path / "LocalAIAssistant"


def test_default_data_dir_fallback_without_localappdata():
    assert default_data_dir({}) == Path.home() / ".local_ai_assistant"


def test_default_export_dir_is_not_hardcoded(tmp_path):
    config = load_config({"LAA_DATA_DIR": str(tmp_path)})
    assert config.export_dir.is_absolute()
    assert config.export_dir != config.data_dir


def test_env_overrides(base_env):
    env = {
        **base_env,
        "LAA_OLLAMA_URL": "http://127.0.0.1:9999/",
        "LAA_LOG_LEVEL": "debug",
        "LAA_REQUEST_TIMEOUT_S": "300",
        "LAA_CONNECT_TIMEOUT_S": "2.5",
        "LAA_TEMPERATURE": "0.7",
        "LAA_TOP_P": "0.95",
        "LAA_NUM_CTX": "4096",
    }
    config = load_config(env)
    assert config.ollama_url == "http://127.0.0.1:9999"
    assert config.log_level == "DEBUG"
    assert config.request_timeout_s == 300
    assert config.connect_timeout_s == 2.5
    assert config.temperature == 0.7
    assert config.top_p == 0.95
    assert config.num_ctx == 4096


def test_model_override_logs_warning(base_env, caplog):
    with caplog.at_level(logging.WARNING, logger="app.config"):
        config = load_config({**base_env, "LAA_MODEL_NAME": "some-other:7b"})
    assert config.model_name == "some-other:7b"
    assert any("LAA_MODEL_NAME" in r.getMessage() for r in caplog.records)


def test_no_warning_without_model_override(base_env, caplog):
    with caplog.at_level(logging.WARNING, logger="app.config"):
        config = load_config(base_env)
    assert config.model_name == DEFAULT_MODEL_NAME
    assert not caplog.records


@pytest.mark.parametrize(
    ("var", "value", "field"),
    [
        ("LAA_OLLAMA_URL", "localhost:11434", "ollama_url"),
        ("LAA_OLLAMA_URL", "ftp://localhost", "ollama_url"),
        ("LAA_REQUEST_TIMEOUT_S", "0", "request_timeout_s"),
        ("LAA_REQUEST_TIMEOUT_S", "abc", "request_timeout_s"),
        ("LAA_CONNECT_TIMEOUT_S", "-1", "connect_timeout_s"),
        ("LAA_TEMPERATURE", "2.5", "temperature"),
        ("LAA_TEMPERATURE", "-0.1", "temperature"),
        ("LAA_TOP_P", "1.5", "top_p"),
        ("LAA_NUM_CTX", "0", "num_ctx"),
        ("LAA_NUM_CTX", "8k", "num_ctx"),
        ("LAA_LOG_LEVEL", "WRONG", "log_level"),
        ("LAA_MODEL_NAME", "   ", "model_name"),
    ],
)
def test_invalid_values_raise_config_error_naming_field(base_env, var, value, field):
    with pytest.raises(ConfigError) as info:
        load_config({**base_env, var: value})
    assert f"'{field}'" in str(info.value)


def test_ensure_directories_creates_dirs_but_not_export(base_env):
    config = load_config(base_env)
    ensure_directories(config)
    assert config.data_dir.is_dir()
    assert config.logs_dir.is_dir()
    assert config.projects_dir.is_dir()
    assert not config.export_dir.exists()


def test_ensure_directories_is_idempotent(base_env):
    config = load_config(base_env)
    ensure_directories(config)
    ensure_directories(config)
    assert config.logs_dir.is_dir()


def test_ensure_directories_reports_failure(tmp_path):
    blocker = tmp_path / "file.txt"
    blocker.write_text("x")
    config = load_config({"LAA_DATA_DIR": str(blocker / "sub"), "LAA_EXPORT_DIR": str(tmp_path)})
    with pytest.raises(ConfigError) as info:
        ensure_directories(config)
    assert info.value.detail


def test_appconfig_is_dataclass():
    assert dataclasses.is_dataclass(AppConfig)
