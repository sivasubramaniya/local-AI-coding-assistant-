import logging
from logging.handlers import RotatingFileHandler

import pytest

from app.config import load_config
from app.logging_setup import BACKUP_COUNT, MAX_BYTES, setup_logging


@pytest.fixture
def config(tmp_path):
    return load_config({"LAA_DATA_DIR": str(tmp_path / "data"), "LAA_EXPORT_DIR": str(tmp_path / "export")})


@pytest.fixture(autouse=True)
def restore_root_logger():
    root = logging.getLogger()
    saved_handlers, saved_level = list(root.handlers), root.level
    yield
    for handler in list(root.handlers):
        if handler not in saved_handlers:
            root.removeHandler(handler)
            handler.close()
    root.setLevel(saved_level)


def _our_handlers():
    return [h for h in logging.getLogger().handlers if getattr(h, "_laa_handler", False)]


def test_writes_to_log_file(config):
    setup_logging(config)
    logging.getLogger("app.test").info("hello from test")
    for handler in _our_handlers():
        handler.flush()
    log_file = config.logs_dir / "app.log"
    assert log_file.is_file()
    text = log_file.read_text(encoding="utf-8")
    assert "hello from test" in text
    assert "INFO" in text


def test_no_duplicate_handlers(config):
    setup_logging(config)
    setup_logging(config)
    handlers = _our_handlers()
    assert len(handlers) == 2
    assert sum(isinstance(h, RotatingFileHandler) for h in handlers) == 1


def test_rotation_settings(config):
    setup_logging(config)
    file_handler = next(h for h in _our_handlers() if isinstance(h, RotatingFileHandler))
    assert file_handler.maxBytes == MAX_BYTES == 1_000_000
    assert file_handler.backupCount == BACKUP_COUNT == 5


def test_http_library_logs_quiet_unless_debug(tmp_path):
    base = {"LAA_DATA_DIR": str(tmp_path), "LAA_EXPORT_DIR": str(tmp_path)}
    setup_logging(load_config(base))
    assert logging.getLogger("httpx").level == logging.WARNING
    setup_logging(load_config({**base, "LAA_LOG_LEVEL": "DEBUG"}))
    assert logging.getLogger("httpx").level == logging.DEBUG
    logging.getLogger("httpx").setLevel(logging.NOTSET)
    logging.getLogger("httpcore").setLevel(logging.NOTSET)


def test_level_applied(tmp_path):
    cfg = load_config({"LAA_DATA_DIR": str(tmp_path), "LAA_EXPORT_DIR": str(tmp_path), "LAA_LOG_LEVEL": "WARNING"})
    setup_logging(cfg)
    assert logging.getLogger().level == logging.WARNING
