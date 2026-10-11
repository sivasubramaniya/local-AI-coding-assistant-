"""Local AI Assistant entry point.

Usage:
    python main.py                       start the desktop application
    python main.py --check               print an environment summary and exit
    python main.py --screenshot PATH     run a scripted demo, save a window capture, exit
        [--delay MS] [--no-preview]
"""

from __future__ import annotations

import argparse
import importlib.util
import logging
import platform
import sys
from pathlib import Path

from app.config import AppConfig, ensure_directories, load_config
from app.errors import ConfigError
from app.logging_setup import setup_logging
from app.prompts import load_system_prompt

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_CONFIG_ERROR = 2
RUNTIME_PACKAGES = ("PySide6", "httpx", "pygments", "markdown")
SCREENSHOT_SIZE = (1600, 900)

logger = logging.getLogger("main")


def _check_summary(config: AppConfig, prompt: str) -> str:
    packages = ", ".join(
        f"{name} {'OK' if importlib.util.find_spec(name) else 'MISSING'}" for name in RUNTIME_PACKAGES
    )
    webengine = "OK" if importlib.util.find_spec("PySide6.QtWebEngineWidgets") else "not installed (fallback preview)"
    lines = [
        f"{config.app_name} - environment check",
        f"  Python        : {platform.python_version()} ({sys.executable})",
        f"  Model         : {config.model_name}",
        f"  Ollama URL    : {config.ollama_url} (not contacted yet)",
        f"  Data dir      : {config.data_dir}",
        f"  Database      : {config.db_path}",
        f"  Logs dir      : {config.logs_dir}",
        f"  Projects dir  : {config.projects_dir}",
        f"  Export dir    : {config.export_dir}",
        f"  Log level     : {config.log_level}",
        f"  System prompt : loaded ({len(prompt)} characters)",
        f"  Packages      : {packages}",
        f"  QtWebEngine   : {webengine}",
    ]
    return "\n".join(lines)


def create_app(argv: list[str] | None = None):
    """Create the QApplication with the theme applied."""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    from app.ui.preview_panel import webengine_available
    from app.ui.theme import apply_theme

    if webengine_available():
        # QtWebEngine must be imported and GL contexts shared before QApplication exists
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app = QApplication.instance() or QApplication(argv or sys.argv[:1])
    app.setApplicationName("Local AI Assistant")
    app.setOrganizationName("LocalAIAssistant")
    apply_theme(app)
    return app


def run_gui(config: AppConfig) -> int:
    from app.ui.main_window import MainWindow

    app = create_app()
    window = MainWindow(config)
    window.showMaximized()
    return app.exec()


def run_screenshot(config: AppConfig, path: Path, delay_ms: int, open_preview: bool) -> int:
    """Scripted demo: one user message, a streamed answer, optional preview, then a capture."""
    from PySide6.QtCore import QTimer

    from app.ui import demo
    from app.ui.main_window import MainWindow

    app = create_app()
    window = MainWindow(config, token_delay_s=0.004)
    window.resize(*SCREENSHOT_SIZE)
    window.show()
    window.new_chat()
    result = {"code": EXIT_ERROR}

    def capture() -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        ok = window.grab().save(str(path))
        if ok:
            logger.info("Screenshot saved to %s", path)
            print(f"Screenshot saved: {path}")
            result["code"] = EXIT_OK
        else:
            print(f"Could not save screenshot to {path}", file=sys.stderr)
        app.quit()

    def after_stream() -> None:
        if open_preview:
            window.open_file(demo.DEMO_ANSWER_FILES[0])
        QTimer.singleShot(delay_ms, capture)

    window.streamFinished.connect(after_stream)
    QTimer.singleShot(400, lambda: window.submit_prompt(demo.WELCOME_PROMPT))
    QTimer.singleShot(60_000, app.quit)  # safety net
    app.exec()
    return result["code"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="main.py", description="Local AI Assistant")
    parser.add_argument("--check", action="store_true", help="print an environment summary and exit")
    parser.add_argument("--screenshot", metavar="PATH", help="run a scripted demo and save a window capture")
    parser.add_argument("--delay", type=int, default=800, metavar="MS", help="wait before the capture (default 800)")
    parser.add_argument("--no-preview", action="store_true", help="capture with the preview panel closed")
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
    if args.screenshot:
        return run_screenshot(config, Path(args.screenshot), max(0, args.delay), not args.no_preview)
    return run_gui(config)


if __name__ == "__main__":
    sys.exit(main())
