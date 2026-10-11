"""Local AI Assistant entry point.

Usage:
    python main.py           start the application
    python main.py --check   print an environment summary and exit
"""

from __future__ import annotations

import argparse
import importlib.util
import logging
import platform
import sys

from app.config import AppConfig, ensure_directories, load_config
from app.errors import ConfigError
from app.logging_setup import setup_logging
from app.prompts import load_system_prompt

EXIT_OK = 0
EXIT_CONFIG_ERROR = 2
RUNTIME_PACKAGES = ("PySide6", "httpx", "pygments", "markdown")

logger = logging.getLogger("main")


def _check_summary(config: AppConfig, prompt: str) -> str:
    packages = ", ".join(
        f"{name} {'OK' if importlib.util.find_spec(name) else 'MISSING'}" for name in RUNTIME_PACKAGES
    )
    lines = [
        f"{config.app_name} - environment check",
        f"  Python        : {platform.python_version()} ({sys.executable})",
        f"  Model         : {config.model_name}",
        f"  Ollama URL    : {config.ollama_url} (not contacted in this phase)",
        f"  Data dir      : {config.data_dir}",
        f"  Database      : {config.db_path}",
        f"  Logs dir      : {config.logs_dir}",
        f"  Projects dir  : {config.projects_dir}",
        f"  Export dir    : {config.export_dir}",
        f"  Log level     : {config.log_level}",
        f"  System prompt : loaded ({len(prompt)} characters)",
        f"  Packages      : {packages}",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="main.py", description="Local AI Assistant")
    parser.add_argument("--check", action="store_true", help="print an environment summary and exit")
    args = parser.parse_args(argv)

    try:
        config = load_config()
        ensure_directories(config)
        setup_logging(config)
        prompt = load_system_prompt()
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        if exc.detail:
            print(f"Details: {exc.detail}", file=sys.stderr)
        return EXIT_CONFIG_ERROR

    logger.info(
        "Starting %s | model=%s | data_dir=%s", config.app_name, config.model_name, config.data_dir
    )

    if args.check:
        print(_check_summary(config, prompt))
        return EXIT_OK

    # TODO(Phase 3): create the QApplication and MainWindow here and return app.exec().
    logger.info("UI not implemented yet (Phase 3). Exiting.")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
