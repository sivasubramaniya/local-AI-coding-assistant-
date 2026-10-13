"""Central application configuration.

All paths, the model name and service settings come from here. Values can be
overridden with environment variables prefixed ``LAA_`` (see ``ENV_OVERRIDES``).
"""

from __future__ import annotations

import logging
import os
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from app.errors import ConfigError

logger = logging.getLogger(__name__)

APP_DIR_NAME = "LocalAIAssistant"
FALLBACK_DIR_NAME = ".local_ai_assistant"
DEFAULT_MODEL_NAME = "qwen2.5-coder-14b:latest"
# Optional Fast mode (owner decision 2026-10-12). Used only when the user selects it; never as a fallback.
DEFAULT_FAST_MODEL_NAME = "qwen2.5-coder-7b:latest"
VALID_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


@dataclass(frozen=True)
class AppConfig:
    app_name: str
    model_name: str
    ollama_url: str
    request_timeout_s: float
    connect_timeout_s: float
    temperature: float
    top_p: float
    num_ctx: int
    data_dir: Path
    db_path: Path
    logs_dir: Path
    projects_dir: Path
    export_dir: Path
    log_level: str
    keep_alive: str = "10m"
    stream_read_timeout_s: float = 300.0
    health_interval_s: float = 10.0
    command_timeout_s: float = 60.0
    fast_model_name: str = DEFAULT_FAST_MODEL_NAME

    @property
    def model_base_name(self) -> str:
        """Model name without the ':latest' tag (the name used by `ollama create`)."""
        return self.model_name.removesuffix(":latest")


LOOPBACK_HOSTS = ("localhost", "127.0.0.1", "::1")
_KEEP_ALIVE_RE = re.compile(r"^(-1|0|\d+(\.\d+)?(ms|s|m|h)?)$")


def model_options(config: AppConfig) -> dict[str, float | int]:
    """Generation options sent to Ollama on every request."""
    return {"temperature": config.temperature, "top_p": config.top_p, "num_ctx": config.num_ctx}


def default_data_dir(env: Mapping[str, str] | None = None) -> Path:
    """%LOCALAPPDATA%\\LocalAIAssistant, or ~/.local_ai_assistant if unset."""
    env = os.environ if env is None else env
    local = env.get("LOCALAPPDATA")
    if local:
        return Path(local) / APP_DIR_NAME
    return Path.home() / FALLBACK_DIR_NAME


def default_desktop_dir() -> Path:
    """The user's real Desktop folder (handles OneDrive redirection on Windows)."""
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            class GUID(ctypes.Structure):
                _fields_ = [
                    ("Data1", wintypes.DWORD),
                    ("Data2", wintypes.WORD),
                    ("Data3", wintypes.WORD),
                    ("Data4", wintypes.BYTE * 8),
                ]

            # FOLDERID_Desktop {B4BFCC3A-DB2C-424C-B029-7FE99A87C641}
            folder_id = GUID(
                0xB4BFCC3A, 0xDB2C, 0x424C,
                (wintypes.BYTE * 8)(0xB0, 0x29, 0x7F, 0xE9, 0x9A, 0x87, 0xC6, 0x41),
            )
            path_ptr = ctypes.c_wchar_p()
            result = ctypes.windll.shell32.SHGetKnownFolderPath(
                ctypes.byref(folder_id), 0, None, ctypes.byref(path_ptr)
            )
            if result == 0 and path_ptr.value:
                desktop = Path(path_ptr.value)
                ctypes.windll.ole32.CoTaskMemFree(path_ptr)
                return desktop
        except (OSError, AttributeError):  # pragma: no cover - platform specific
            logger.debug("SHGetKnownFolderPath failed; using ~/Desktop", exc_info=True)
    return Path.home() / "Desktop"


def _parse_float(field: str, raw: str) -> float:
    try:
        return float(raw)
    except ValueError:
        raise ConfigError(f"Invalid config value for '{field}': expected a number, got {raw!r}.") from None


def _parse_int(field: str, raw: str) -> int:
    try:
        return int(raw)
    except ValueError:
        raise ConfigError(f"Invalid config value for '{field}': expected a whole number, got {raw!r}.") from None


def validate_config(config: AppConfig) -> AppConfig:
    """Raise ConfigError naming the first invalid field."""
    url = urlparse(config.ollama_url)
    if url.scheme not in ("http", "https") or not url.netloc:
        raise ConfigError(
            f"Invalid config value for 'ollama_url': {config.ollama_url!r} is not an http(s) URL."
        )
    try:
        host = (url.hostname or "").lower()
        url.port  # noqa: B018 - raises ValueError for a malformed port
    except ValueError:
        raise ConfigError(f"Invalid config value for 'ollama_url': {config.ollama_url!r} has a bad port.") from None
    if host not in LOOPBACK_HOSTS:
        raise ConfigError(
            f"Invalid config value for 'ollama_url': host {host!r} is not local. "
            f"Only {', '.join(LOOPBACK_HOSTS)} are allowed, so no remote or cloud service is ever called."
        )
    for field_name in ("model_name", "fast_model_name"):
        value = getattr(config, field_name)
        if not value.strip() or value != value.strip() or " " in value:
            raise ConfigError(f"Invalid config value for '{field_name}': {value!r} is not a model name.")
    if config.fast_model_name == config.model_name:
        raise ConfigError("Invalid config value for 'fast_model_name': it must differ from 'model_name'.")
    if config.request_timeout_s <= 0:
        raise ConfigError("Invalid config value for 'request_timeout_s': it must be greater than 0.")
    if config.connect_timeout_s <= 0:
        raise ConfigError("Invalid config value for 'connect_timeout_s': it must be greater than 0.")
    if not 0 <= config.temperature <= 2:
        raise ConfigError("Invalid config value for 'temperature': it must be between 0 and 2.")
    if not 0 <= config.top_p <= 1:
        raise ConfigError("Invalid config value for 'top_p': it must be between 0 and 1.")
    if config.num_ctx <= 0:
        raise ConfigError("Invalid config value for 'num_ctx': it must be greater than 0.")
    if not _KEEP_ALIVE_RE.match(config.keep_alive):
        raise ConfigError(
            f"Invalid config value for 'keep_alive': {config.keep_alive!r}. Use a duration like 10m, 300s, 1h, 0 or -1."
        )
    if config.stream_read_timeout_s <= 0:
        raise ConfigError("Invalid config value for 'stream_read_timeout_s': it must be greater than 0.")
    if config.health_interval_s < 1:
        raise ConfigError("Invalid config value for 'health_interval_s': it must be at least 1 second.")
    if not 1 <= config.command_timeout_s <= 3600:
        raise ConfigError("Invalid config value for 'command_timeout_s': it must be between 1 and 3600 seconds.")
    if config.log_level not in VALID_LOG_LEVELS:
        raise ConfigError(
            f"Invalid config value for 'log_level': {config.log_level!r}. "
            f"Use one of {', '.join(VALID_LOG_LEVELS)}."
        )
    return config


def load_config(env: Mapping[str, str] | None = None) -> AppConfig:
    """Build and validate the configuration from defaults plus LAA_* overrides."""
    env = os.environ if env is None else env

    model_name = DEFAULT_MODEL_NAME
    override = env.get("LAA_MODEL_NAME")
    if override is not None and override != DEFAULT_MODEL_NAME:
        logger.warning(
            "Model name overridden by LAA_MODEL_NAME: %r (default is %r).",
            override, DEFAULT_MODEL_NAME,
        )
        model_name = override

    fast_model_name = DEFAULT_FAST_MODEL_NAME
    fast_override = env.get("LAA_FAST_MODEL_NAME")
    if fast_override is not None and fast_override != DEFAULT_FAST_MODEL_NAME:
        logger.warning(
            "Fast model name overridden by LAA_FAST_MODEL_NAME: %r (default is %r).",
            fast_override, DEFAULT_FAST_MODEL_NAME,
        )
        fast_model_name = fast_override

    data_dir = Path(env["LAA_DATA_DIR"]) if env.get("LAA_DATA_DIR") else default_data_dir(env)
    export_dir = Path(env["LAA_EXPORT_DIR"]) if env.get("LAA_EXPORT_DIR") else default_desktop_dir()

    config = AppConfig(
        app_name="Local AI Assistant",
        model_name=model_name,
        fast_model_name=fast_model_name,
        ollama_url=env.get("LAA_OLLAMA_URL", "http://localhost:11434").rstrip("/"),
        request_timeout_s=_parse_float("request_timeout_s", env.get("LAA_REQUEST_TIMEOUT_S", "120")),
        connect_timeout_s=_parse_float("connect_timeout_s", env.get("LAA_CONNECT_TIMEOUT_S", "5")),
        temperature=_parse_float("temperature", env.get("LAA_TEMPERATURE", "0.2")),
        top_p=_parse_float("top_p", env.get("LAA_TOP_P", "0.8")),
        num_ctx=_parse_int("num_ctx", env.get("LAA_NUM_CTX", "8192")),
        data_dir=data_dir,
        db_path=data_dir / "assistant.db",
        logs_dir=data_dir / "logs",
        projects_dir=data_dir / "projects",
        export_dir=export_dir,
        log_level=env.get("LAA_LOG_LEVEL", "INFO").strip().upper(),
        keep_alive=env.get("LAA_KEEP_ALIVE", "10m").strip(),
        stream_read_timeout_s=_parse_float("stream_read_timeout_s", env.get("LAA_STREAM_READ_TIMEOUT_S", "300")),
        health_interval_s=_parse_float("health_interval_s", env.get("LAA_HEALTH_INTERVAL_S", "10")),
        command_timeout_s=_parse_float("command_timeout_s", env.get("LAA_COMMAND_TIMEOUT_S", "60")),
    )
    return validate_config(config)


def ensure_directories(config: AppConfig) -> None:
    """Create data, logs and projects directories. export_dir is never created here."""
    for path in (config.data_dir, config.logs_dir, config.projects_dir):
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ConfigError(f"Cannot create directory '{path}'.", detail=str(exc)) from exc
