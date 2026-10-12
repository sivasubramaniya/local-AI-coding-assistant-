"""Local AI Assistant entry point.

Usage:
    python main.py                       start the desktop application
    python main.py --check               print an environment summary and exit
    python main.py --demo                start with canned demo answers (no model needed)
    python main.py --screenshot PATH     run a scripted demo, save a window capture, exit
        [--delay MS] [--no-preview]
"""

from __future__ import annotations

import argparse
import importlib.util
import logging
import platform
import sys
from collections.abc import Callable
from pathlib import Path

from app.__version__ import __version__
from app.config import AppConfig, ensure_directories, load_config
from app.errors import AppError, ConfigError
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
    ollama_lines, warnings = _ollama_report(config)
    lines = [
        f"{config.app_name} {__version__} - environment check",
        f"  Version       : {__version__}",
        f"  Python        : {platform.python_version()} ({sys.executable})",
        f"  Model         : {config.model_name}",
        f"  Ollama URL    : {config.ollama_url}",
        *ollama_lines,
        f"  Options       : temperature={config.temperature}, top_p={config.top_p}, "
        f"num_ctx={config.num_ctx}, keep_alive={config.keep_alive}",
        f"  Timeouts      : connect={config.connect_timeout_s:g}s, request={config.request_timeout_s:g}s, "
        f"stream gap={config.stream_read_timeout_s:g}s, health every {config.health_interval_s:g}s",
        f"  Data dir      : {config.data_dir}",
        *_database_report(config),
        f"  Logs dir      : {config.logs_dir}",
        f"  Projects dir  : {config.projects_dir}",
        f"  Export dir    : {config.export_dir}",
        f"  Log level     : {config.log_level}",
        f"  System prompt : loaded ({len(prompt)} characters)",
        f"  Packages      : {packages}",
        f"  QtWebEngine   : {webengine}",
        *(f"WARNING: {w}" for w in warnings),
    ]
    return "\n".join(lines)


def _database_report(config: AppConfig) -> list[str]:
    """Read-only: never creates or migrates the database."""
    from app.storage.database import inspect_database, latest_version

    info = inspect_database(config.db_path)
    lines = [f"  Database      : {config.db_path}"]
    if not info.exists:
        lines.append(f"  DB schema     : not created yet (app supports v{latest_version()})")
    elif info.error:
        lines.append(f"  DB schema     : UNREADABLE ({info.error})")
    else:
        lines.append(f"  DB schema     : v{info.schema_version} (app supports v{latest_version()})")
        lines.append(f"  Chats         : {info.chat_count}")
    return lines


def _ollama_report(config: AppConfig) -> tuple[list[str], list[str]]:
    """Contact Ollama (only /api/version and /api/tags). Returns (lines, warnings)."""
    from app.backend.ollama_client import OllamaClient, close_matches, create_hint

    lines: list[str] = []
    warnings: list[str] = []
    with OllamaClient(config) as client:
        try:
            lines.append(f"  Ollama        : running, version {client.get_version()}")
            models = client.list_models()
        except AppError as exc:
            lines.append("  Ollama        : NOT REACHABLE")
            warnings.append(exc.message)
            return lines, warnings
    present = config.model_name in models
    lines.append(f"  Model present : {'yes (exact match)' if present else 'NO'}")
    lines.append(f"  Installed     : {', '.join(models) or 'none'}")
    if not present:
        matches = close_matches(config.model_name, models)
        if matches:
            lines.append(f"  Similar       : {', '.join(matches)} (never used automatically)")
        warnings.append(
            f"Model {config.model_name} is not installed. " + create_hint(config)
        )
    return lines, warnings


def attach_parent_console() -> bool:
    """Packaged (windowed) build: print to the terminal that started us, if any."""
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return False
    import ctypes

    if not ctypes.windll.kernel32.AttachConsole(-1):  # ATTACH_PARENT_PROCESS
        return False
    sys.stdout = open("CONOUT$", "w", encoding="utf-8", errors="replace")  # noqa: SIM115
    sys.stderr = open("CONOUT$", "w", encoding="utf-8", errors="replace")  # noqa: SIM115
    return True


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
    app.setApplicationVersion(__version__)
    app.setOrganizationName("LocalAIAssistant")
    apply_theme(app)
    return app


def open_history_store(config: AppConfig, choose: Callable[[str, bool], str]):
    """Open the SQLite chat history at config.db_path.

    When it cannot be opened, ``choose(message, offer_fresh)`` decides: "fresh" (a damaged
    file was already moved to a backup, so open a new one), "memory" (run without saving)
    or "quit" (returns None). User data is never deleted.
    """
    from app.backend.memory_store import InMemoryChatStore
    from app.storage.chat_repository import SqliteChatRepository
    from app.storage.database import DatabaseCorruptError

    try:
        return SqliteChatRepository.open(config.db_path)
    except DatabaseCorruptError as exc:
        logger.error("History database unreadable: %s", exc.full_text())
        choice = choose(f"{exc.message}\n\nStart with a fresh, empty chat history?", True)
        if choice == "fresh":
            try:
                return SqliteChatRepository.open(config.db_path)
            except AppError as again:
                logger.error("Fresh database failed: %s", again.full_text())
                choice = choose(again.message, False)
    except AppError as exc:
        logger.error("History database unavailable: %s", exc.full_text())
        choice = choose(exc.message, False)
    return InMemoryChatStore() if choice == "memory" else None


def run_gui(config: AppConfig, demo_mode: bool = False) -> int:
    from app.backend.memory_store import InMemoryChatStore
    from app.ui.dialogs import ask_storage_recovery
    from app.ui.main_window import MainWindow

    app = create_app()
    # demo mode never touches the real database
    store = InMemoryChatStore() if demo_mode else open_history_store(config, ask_storage_recovery)
    if store is None:
        return EXIT_ERROR
    window = MainWindow(config, store=store, demo_mode=demo_mode)
    window.showMaximized()
    try:
        return app.exec()
    finally:
        from app.ui.workers import shutdown_workers

        shutdown_workers()  # no QThread may outlive the application object
        store.close()


def run_screenshot(config: AppConfig, path: Path, delay_ms: int, open_preview: bool) -> int:
    """Scripted demo: one user message, a streamed answer, optional preview, then a capture."""
    from PySide6.QtCore import QTimer

    from app.ui import demo
    from app.ui.main_window import MainWindow

    app = create_app()
    # screenshots are deterministic: demo answers, no Ollama health checks
    window = MainWindow(config, token_delay_s=0.004, demo_mode=True, health_checks=False)
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
    parser.add_argument("--version", action="version", version=f"Local AI Assistant {__version__}")
    parser.add_argument("--screenshot", metavar="PATH", help="run a scripted demo and save a window capture")
    parser.add_argument("--delay", type=int, default=800, metavar="MS", help="wait before the capture (default 800)")
    parser.add_argument("--no-preview", action="store_true", help="capture with the preview panel closed")
    parser.add_argument("--demo", action="store_true", help="use canned demo answers instead of the model")
    args = parser.parse_args(argv)

    if getattr(sys, "frozen", False):
        attach_parent_console()  # so configuration errors are visible when started from a terminal
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
        summary = _check_summary(config, prompt)
        if getattr(sys, "frozen", False):
            # the windowed exe has no console of its own: attach to the caller's and keep a copy
            attach_parent_console()
            (config.logs_dir / "check.txt").write_text(summary + "\n", encoding="utf-8")
        print(summary)
        return EXIT_OK
    if args.screenshot:
        return run_screenshot(config, Path(args.screenshot), max(0, args.delay), not args.no_preview)
    return run_gui(config, demo_mode=args.demo)


if __name__ == "__main__":
    sys.exit(main())
