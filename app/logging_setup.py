"""Logging configuration: console + rotating file.

Policy: never log prompt text, model output or file contents at INFO level or
above. Log sizes, counts and identifiers instead; full content only at DEBUG.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

from app.config import AppConfig

LOG_FORMAT = "%(asctime)s %(levelname)-8s %(module)s: %(message)s"
LOG_FILE_NAME = "app.log"
MAX_BYTES = 1_000_000
BACKUP_COUNT = 5
_HANDLER_MARK = "_laa_handler"
NOISY_LIBRARIES = ("httpx", "httpcore")


def setup_logging(config: AppConfig) -> logging.Logger:
    """Configure the root logger. Safe to call repeatedly (handlers are replaced)."""
    root = logging.getLogger()
    for handler in list(root.handlers):
        if getattr(handler, _HANDLER_MARK, False):
            root.removeHandler(handler)
            handler.close()

    formatter = logging.Formatter(LOG_FORMAT)

    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(formatter)
    setattr(console, _HANDLER_MARK, True)

    config.logs_dir.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        config.logs_dir / LOG_FILE_NAME,
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    setattr(file_handler, _HANDLER_MARK, True)

    root.addHandler(console)
    root.addHandler(file_handler)
    root.setLevel(config.log_level)
    # httpx logs every request at INFO (health checks run every few seconds); keep that for DEBUG only
    library_level = logging.DEBUG if config.log_level == "DEBUG" else logging.WARNING
    for name in NOISY_LIBRARIES:
        logging.getLogger(name).setLevel(library_level)
    return root
