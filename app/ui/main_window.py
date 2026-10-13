"""Main window: Sidebar | QSplitter(chat panel, preview panel).

The window wires widgets to the chat service, the Ollama workers and the health
checks. Business rules (message building, trimming, history) live in
app.backend.chat_service; network work runs in worker threads.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QSplitter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.agent.coding_agent import (
    CONTEXT_TASKS,
    apply_changes,
    build_context,
    list_project_files,
    parse_changes,
    prepare_changes,
    read_attachments,
    read_project_files,
)
from app.agent.project_generator import GenerationResult, ProjectPlan, ProjectWriter
from app.agent.tool_runner import (
    CommandResult,
    ToolRunner,
    default_test_commands,
    display_command,
    results_markdown,
    trimmed_failure_output,
)
from app.backend.chat_service import ChatService
from app.backend.chat_store import (
    FEEDBACK_BAD,
    LAST_CHAT_SETTING,
    ChatMessage,
    ChatStore,
    Conversation,
    ProjectRecord,
)
from app.backend.memory_store import InMemoryChatStore
from app.backend.ollama_client import OllamaClient, StreamStats, create_hint
from app.backend.status import ConnectionState, HealthResult, stub_connection_state
from app.config import AppConfig
from app.backend.task_classifier import TaskType, classify
from app.errors import (
    AppError,
    CommandRejectedError,
    ModelNotFoundError,
    OllamaUnavailableError,
    ResponseFormatError,
)
from app.ui import demo, theme
from app.ui.agent_widgets import ChangesCard, ExportCard, PlanCard
from app.ui.dialogs import CommandApprovalDialog, SettingsDialog
from app.ui.chat_view import ChatView
from app.ui.composer import Composer
from app.ui.icons import icon_size, load_icon
from app.ui.message_widgets import AssistantMessage, ErrorCard
from app.ui.preview_panel import PreviewPanel
from app.ui.sidebar import Sidebar
from app.ui.workers import (
    FakeStreamWorker,
    GenerateWorker,
    HealthCheckWorker,
    OllamaStreamWorker,
    PlanWorker,
    StreamWorker,
    ExportWorker,
    ToolWorker,
    WorkerHandle,
    start_worker,
)
from app.validation.project_validator import validate_project

logger = logging.getLogger(__name__)

NO_PROJECT_TO_EXPORT = "This chat has no project to export yet."
EXPORT_DIR_SETTING = "export_dir"
COMMAND_TIMEOUT_SETTING = "command_timeout_s"
DEFAULT_MODEL_MODE_SETTING = "default_model_mode"  # "quality" (14B, default) or "fast" (7B)
TOAST_MS = 2600
PREVIEW_SHARE = 0.45
STATUS_LOADING = "Loading model…"
STATUS_GENERATING = "Generating…"
STATUS_STOPPED = "(stopped)"
STATUS_FAILED = "Failed"
STOP_WAIT_MS = 1500
CLOSE_WAIT_MS = 6000
DELETE_CONFIRM = "Delete this chat? This cannot be undone."
STATUS_PLANNING = "Planning project…"
STATUS_PLAN_READY = "Project plan · review it, then click Generate files"
JOB_CHAT, JOB_PLAN, JOB_GENERATE, JOB_TOOL = "chat", "plan", "generate", "tool"
STATUS_RUNNING = "Running command…"
STATUS_CHECKS_PASSED = "Checks passed"
STATUS_CHECKS_FAILED = "Checks failed"
MAX_REPAIR_ROUNDS = 3


@dataclass
class RepairLoop:
    """Run tests -> model proposes a fix -> user applies it -> re-run (at most MAX_REPAIR_ROUNDS fixes)."""

    commands: list[list[str]]
    round: int = 0
PREVIEW_MAX_CHARS = 2_000_000


def _top_bar_button(icon: str, tooltip: str, text: str = "") -> QToolButton:
    button = QToolButton()
    button.setObjectName("topBarButton")
    button.setIcon(load_icon(icon, theme.TEXT_PRIMARY, 20))
    button.setIconSize(icon_size(20))
    button.setToolTip(tooltip)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    if text:
        button.setText(text)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
    return button


def reply_status(model_name: str, eval_count: int | None, tokens_per_sec: float | None) -> str:
    """Status line of a finished answer: model, token count and speed when known."""
    name = model_name.removesuffix(":latest")
    if not eval_count or eval_count <= 0:
        return name
    return f"{name} · {eval_count} tokens · {tokens_per_sec or 0.0:.1f} tok/s"


def finished_status(model_name: str, stats: StreamStats | None) -> str:
    if stats is None:
        return reply_status(model_name, None, None)
    return reply_status(model_name, stats.eval_count, stats.tokens_per_second)


class MainWindow(QMainWindow):
    streamFinished = Signal()
    exportFinished = Signal(object)  # ExportResult or AppError
    healthChecked = Signal(object)  # HealthResult

    def __init__(
        self,
        config: AppConfig,
        store: ChatStore | None = None,
        token_delay_s: float = 0.04,
        use_webengine: bool | None = None,
        demo_mode: bool = False,
        client_factory: Callable[[], OllamaClient] | None = None,
        health_checks: bool = True,
        system_prompt: str | None = None,
    ) -> None:
        super().__init__()
        self.config = config
        self.store: ChatStore = store if store is not None else InMemoryChatStore()
        self.service = ChatService(self.store, config, system_prompt)
        self.demo_mode = demo_mode
        self.token_delay_s = token_delay_s
        self._client_factory = client_factory or (lambda: OllamaClient(config))
        self._health_checks = health_checks
        self._health = HealthResult(ConnectionState.CHECKING, "Checking Ollama…")

        self._handle: WorkerHandle | None = None
        self._health_handle: WorkerHandle | None = None
        self._active_message: AssistantMessage | None = None
        self._active_chat_id: str | None = None
        self._got_first_token = False
        self._pending_chat_id: str | None = None
        self._pending_kind = JOB_CHAT
        self._job_kind = JOB_CHAT
        self._active_project: ProjectRecord | None = None
        self._active_plan_card: PlanCard | None = None
        self._active_plan: ProjectPlan | None = None
        self._active_writer_root: Path | None = None
        self.plan_cards: list[PlanCard] = []
        self.command_results: list[CommandResult] = []
        self._repair: dict[str, RepairLoop] = {}
        # Set by Regenerate/Retry: the next saved reply in that chat replaces the earlier one(s).
        self._replace_reply_chat: str | None = None
        # Model selection is explicit and per chat. Nothing here ever picks a model by itself.
        self._fast_default = False
        self._selected_model = config.model_name
        self._active_model = config.model_name
        self._model_presence: dict[str, bool] | None = None
        self._ollama_version: str | None = None
        self._health_checked_model = config.model_name
        self._active_commands: list[list[str]] = []
        # Asks the user to approve a command (command text, working dir) -> bool. Tests replace it.
        self.approver: Callable[[str, str], bool] = self._ask_approval
        # Folder pickers and openers; tests replace them.
        self.folder_chooser: Callable[[str], str | None] = self._choose_folder
        self.folder_opener: Callable[[str], None] = self._open_folder
        self.settings_editor: Callable[[str, float], tuple[str, int] | None] = self._edit_settings
        self._export_handle: WorkerHandle | None = None
        self._export_as_zip = False
        self.export_cards: list[ExportCard] = []
        self.changes_cards: list[ChangesCard] = []
        self._current_chat_id: str | None = None
        self._expanded = False

        self.setWindowTitle(config.app_name)
        self.setMinimumSize(theme.WINDOW_MIN_WIDTH, theme.WINDOW_MIN_HEIGHT)

        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.sidebar = Sidebar(config.app_name, config.model_name)
        root.addWidget(self.sidebar)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(1)
        self.chat_panel = self._build_chat_panel()
        self.preview = PreviewPanel(use_webengine=use_webengine)
        self.preview.hide()
        self.splitter.addWidget(self.chat_panel)
        self.splitter.addWidget(self.preview)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 1)
        root.addWidget(self.splitter, 1)
        self.setCentralWidget(central)

        self.toast = QLabel(self.chat_panel)
        self.toast.setObjectName("toast")
        self.toast.hide()
        self._toast_timer = QTimer(self)
        self._toast_timer.setSingleShot(True)
        self._toast_timer.timeout.connect(self.toast.hide)

        self._connect_signals()

        self._health_timer = QTimer(self)
        self._health_timer.setInterval(int(config.health_interval_s * 1000))
        self._health_timer.timeout.connect(self.check_health)
        if health_checks:
            self.set_health(self._health)
            self._health_timer.start()
            QTimer.singleShot(0, self.check_health)
        else:
            self.set_health(HealthResult(stub_connection_state(), "Health checks are off."))

        if demo_mode:
            self.preview.set_project(demo.DEMO_PROJECT_NAME, demo.DEMO_FILES)
            self.sidebar.set_projects([demo.DEMO_PROJECT_NAME])
            self.select_chat(demo.seed_demo_store(self.store))
        else:
            self._load_saved_settings()
            self._refresh_projects()
            self.restore_last_chat()

    # --- construction ----------------------------------------------------------
    def _build_chat_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("chatPanel")
        panel.setMinimumWidth(theme.CHAT_MIN_WIDTH)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        top_bar = QFrame()
        top_bar.setObjectName("topBar")
        top_bar.setFixedHeight(theme.TOP_BAR_HEIGHT + 8)
        bar = QHBoxLayout(top_bar)
        bar.setContentsMargins(16, 8, 16, 8)
        bar.setSpacing(6)
        bar.addStretch(1)
        self.export_button = _top_bar_button("export", "Export project", "Export")
        self.files_button = _top_bar_button("sidebar", "Show or hide the preview panel")
        self.files_button.setCheckable(True)
        self.more_button = _top_bar_button("more", "More")
        self.more_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        more = QMenu(self.more_button)
        self.rename_action = more.addAction("Rename chat", self._rename_current)
        self.run_tests_action = more.addAction("Run project tests", self.run_project_tests)
        self.export_zip_action = more.addAction("Export ZIP", lambda: self.export_project(as_zip=True))
        more.addSeparator()
        self.delete_action = more.addAction("Delete chat", self._delete_current)
        self.more_button.setMenu(more)
        for button in (self.export_button, self.files_button, self.more_button):
            bar.addWidget(button)
        layout.addWidget(top_bar)

        self.chat_view = ChatView()
        layout.addWidget(self.chat_view, 1)

        composer_row = QHBoxLayout()
        composer_row.setContentsMargins(24, 4, 24, 18)
        composer_row.addStretch(1)
        self.composer = Composer()
        self.composer.setMaximumWidth(theme.CONTENT_MAX_WIDTH)
        composer_row.addWidget(self.composer, 1000)
        composer_row.addStretch(1)
        layout.addLayout(composer_row)
        return panel

    def _connect_signals(self) -> None:
        sb = self.sidebar
        sb.newChatRequested.connect(self.new_chat)
        sb.chatSelected.connect(self.select_chat)
        sb.renameRequested.connect(self._ask_rename)
        sb.deleteRequested.connect(self._ask_delete)
        sb.projectSelected.connect(self.open_project)
        sb.generatedProjectsRequested.connect(self.open_preview)
        sb.settingsRequested.connect(self.open_settings)

        self.composer.sendRequested.connect(self.submit_prompt)
        self.composer.stopRequested.connect(self.stop_generation)
        self.composer.fastModeToggled.connect(self.set_fast_mode)

        self.export_button.clicked.connect(lambda: self.export_project(as_zip=False))
        self.files_button.clicked.connect(self.toggle_preview)

        self.preview.closeRequested.connect(self.close_preview)
        self.preview.expandToggled.connect(self.set_preview_expanded)
        self.preview.exportRequested.connect(lambda _path: self.export_project(as_zip=False))

    # --- chats -----------------------------------------------------------------
    # Every store call runs here on the UI thread. A StorageError never escapes:
    # it is shown as a toast or an error card and the app keeps running.
    def current_chat_id(self) -> str | None:
        return self._current_chat_id

    def _storage_failed(self, exc: AppError, card: bool = False) -> None:
        logger.warning("Storage error: %s", exc.full_text())
        if card:
            error = self.chat_view.add_error(exc.message)
            error.retry_button.hide()
        else:
            self.show_toast(exc.message)

    def _refresh_sidebar(self) -> None:
        try:
            chats = [(c.id, c.title) for c in self.store.list_chats()]
        except AppError as exc:
            self._storage_failed(exc)
            return
        self.sidebar.set_chats(chats, self._current_chat_id)

    def _refresh_projects(self) -> None:
        try:
            projects = [(p.id, p.name) for p in self.store.list_projects()]
        except AppError as exc:
            self._storage_failed(exc)
            projects = []
        self.sidebar.set_projects(projects)

    def _set_current(self, chat_id: str | None) -> None:
        self._current_chat_id = chat_id
        try:
            self.store.set_setting(LAST_CHAT_SETTING, chat_id)
        except AppError as exc:
            logger.warning("Could not remember the open chat: %s", exc.full_text())

    def _is_empty(self, chat_id: str | None) -> bool:
        if not chat_id:
            return False
        try:
            return self.store.chat_exists(chat_id) and not self.store.get_messages(chat_id)
        except AppError:
            return False

    def _discard_if_empty(self, chat_id: str | None) -> None:
        """Drop an untouched 'New chat' when the user leaves it (it holds no data)."""
        if chat_id and self._is_empty(chat_id):
            try:
                self.store.delete_chat(chat_id)
            except AppError as exc:
                logger.warning("Could not remove an empty chat: %s", exc.full_text())

    def restore_last_chat(self) -> None:
        """Reopen the chat that was open last time, or start a new one."""
        try:
            last = self.store.get_setting(LAST_CHAT_SETTING)
            exists = bool(last) and self.store.chat_exists(last)
        except AppError as exc:
            self._storage_failed(exc)
            last, exists = None, False
        if exists:
            self.select_chat(last)
        else:
            self.new_chat()

    def new_chat(self) -> str | None:
        self.stop_generation()
        current = self._current_chat_id
        if self._is_empty(current):
            chat_id = current  # already on an untouched chat: reuse it
        else:
            try:
                chat_id = self.store.create_chat(model_name=self.default_model()).id
            except AppError as exc:
                self._storage_failed(exc)
                return None
        self._set_current(chat_id)
        self.chat_view.clear()
        try:
            self._apply_model(self._model_for_chat(self.store.get_chat(chat_id)))
        except AppError:
            self._apply_model(self.default_model())
        if not self.demo_mode:
            self.preview.clear_project()
        self._refresh_sidebar()
        self.composer.input.setFocus()
        return chat_id

    def select_chat(self, chat_id: str) -> None:
        if chat_id == self._current_chat_id and self.chat_view.items:
            return
        self.stop_generation()
        try:
            chat = self.store.get_chat(chat_id)
            messages = self.store.get_messages(chat_id)
        except AppError as exc:
            self._storage_failed(exc)
            self._refresh_sidebar()
            return
        previous = self._current_chat_id
        self._set_current(chat_id)
        if previous != chat_id:
            self._discard_if_empty(previous)
        self.chat_view.clear()
        self._apply_model(self._model_for_chat(chat))
        for message in messages:
            self._render_stored(chat, message)
        self._load_chat_project(chat_id)
        self._refresh_sidebar()
        QTimer.singleShot(0, self.chat_view.scroll_to_bottom)

    def _render_stored(self, chat: Conversation, message: ChatMessage) -> None:
        if message.role == "user":
            self.chat_view.add_user_message(message.content)
            return
        if message.kind == "tool":
            status = {"complete": STATUS_CHECKS_PASSED, "error": STATUS_CHECKS_FAILED}.get(message.status,
                                                                                         STATUS_STOPPED)
        elif message.status == "error":
            card = self.chat_view.add_error(message.content)
            card.retryRequested.connect(self.retry)
            return
        elif message.status == "stopped":
            status = STATUS_STOPPED
        elif self.demo_mode:
            status = demo.DEMO_STATUS
        else:
            status = reply_status(message.model_name or chat.model_name or self.config.model_name,
                                  message.eval_count, message.tokens_per_sec)
        widget = self._add_assistant_widget(status)
        widget.set_text(message.content)
        for path in message.files:
            widget.add_file_card(path)
        widget.finish()
        widget.message_id = message.id
        widget.actions.set_thumbs_down(message.feedback == FEEDBACK_BAD)

    def rename_chat(self, chat_id: str, title: str) -> bool:
        try:
            self.store.rename_chat(chat_id, title)
        except AppError as exc:
            self._storage_failed(exc)
            return False
        self._refresh_sidebar()
        return True

    def delete_chat(self, chat_id: str) -> None:
        if chat_id == self._current_chat_id:
            self.stop_generation()
        try:
            self.store.delete_chat(chat_id)
        except AppError as exc:
            self._storage_failed(exc)
            return
        if chat_id == self._current_chat_id:
            self._current_chat_id = None
            try:
                remaining = self.store.list_chats()
            except AppError as exc:
                self._storage_failed(exc)
                remaining = []
            if remaining:
                self.select_chat(remaining[0].id)
            else:
                self.new_chat()
            return
        self._refresh_sidebar()

    def _ask_rename(self, chat_id: str) -> None:
        try:
            current = self.store.get_chat(chat_id).title
        except AppError as exc:
            self._storage_failed(exc)
            return
        title, ok = QInputDialog.getText(self, "Rename chat", "New name (1–80 characters):", text=current)
        if ok:
            self.rename_chat(chat_id, title)

    def _ask_delete(self, chat_id: str) -> None:
        try:
            if not self.store.chat_exists(chat_id):
                return
        except AppError as exc:
            self._storage_failed(exc)
            return
        answer = QMessageBox.question(
            self, "Delete chat", DELETE_CONFIRM,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.delete_chat(chat_id)

    def _rename_current(self) -> None:
        if self._current_chat_id:
            self._ask_rename(self._current_chat_id)

    def _delete_current(self) -> None:
        if self._current_chat_id:
            self._ask_delete(self._current_chat_id)

    def _on_feedback(self, widget: AssistantMessage, checked: bool) -> None:
        if widget.message_id is None:
            return
        try:
            self.store.set_feedback(widget.message_id, FEEDBACK_BAD if checked else None)
        except AppError as exc:
            self._storage_failed(exc)
            widget.actions.set_thumbs_down(not checked)

    def _save_reply(self, chat_id: str, text: str, status: str, files: list[str] | None = None,
                    stats: StreamStats | None = None, project_id: str | None = None,
                    model_name: str | None = None, kind: str = "chat") -> ChatMessage | None:
        has_stats = stats is not None and stats.eval_count > 0
        replace = self._replace_reply_chat == chat_id
        self._replace_reply_chat = None
        try:
            return self.service.record_reply(
                chat_id, text, status, files,
                eval_count=stats.eval_count if has_stats else None,
                tokens_per_sec=round(stats.tokens_per_second, 2) if has_stats else None,
                project_id=project_id,
                replace=replace,
                model_name=model_name,
                kind=kind,
            )
        except AppError as exc:
            self._storage_failed(exc, card=chat_id == self._current_chat_id)
            return None

    # --- health ----------------------------------------------------------------
    def health(self) -> HealthResult:
        return self._health

    def set_health(self, result: HealthResult) -> None:
        self._health = result
        self.sidebar.status_card.set_state(result.state, result.message)

    def set_connection_state(self, state: ConnectionState, message: str | None = None) -> None:
        self.set_health(HealthResult(state, message or f"Ollama · {state.value}"))

    def check_health(self) -> None:
        """Run ensure_ready() in a worker. Never blocks the UI thread."""
        if self._health_handle is not None:
            return
        self._health_checked_model = self._selected_model
        worker = HealthCheckWorker(self._new_client())
        worker.finished.connect(self._on_health)
        worker.error.connect(self._on_health_error)
        self._health_handle = start_worker(worker, self)

    def _on_health(self, result: object) -> None:
        self._health_handle = None
        if isinstance(result, HealthResult):
            if result.models is not None:
                self._model_presence = dict(result.models)
                self._ollama_version = result.version
                if self._selected_model != self._health_checked_model:
                    result = self._health_for_selected() or result  # the user toggled during the check
            self.set_health(result)
            self.healthChecked.emit(result)
        self._resume_pending()

    # --- model selection (Quality 14B / Fast 7B) ------------------------------------------
    def selected_model(self) -> str:
        return self._selected_model

    def _new_client(self) -> OllamaClient:
        client = self._client_factory()
        client.model = self._selected_model  # exactly the chat's choice; no fallback
        return client

    def _health_for_selected(self) -> HealthResult | None:
        """The status for the selected model from the last check (None if not checked yet)."""
        if self._model_presence is None:
            return None
        name = self._selected_model
        if self._model_presence.get(name):
            return HealthResult(ConnectionState.CONNECTED, f"Ollama {self._ollama_version} · {name} is ready",
                                self._ollama_version, dict(self._model_presence))
        message = f"Model {name} is not installed in Ollama. {create_hint(self.config, name)}"
        return HealthResult(ConnectionState.MODEL_MISSING, message, self._ollama_version, dict(self._model_presence))

    def _apply_model(self, model_name: str) -> None:
        self._selected_model = model_name
        self.composer.set_fast_mode(model_name == self.config.fast_model_name)
        self.sidebar.status_card.set_model_name(model_name)
        updated = self._health_for_selected()
        if updated is not None and self._health.state in (ConnectionState.CONNECTED, ConnectionState.MODEL_MISSING):
            self.set_health(updated)

    def _model_for_chat(self, chat: Conversation | None) -> str:
        if chat is not None and chat.model_name in (self.config.model_name, self.config.fast_model_name):
            return chat.model_name
        return self.config.model_name

    def default_model(self) -> str:
        return self.config.fast_model_name if self._fast_default else self.config.model_name

    def set_fast_mode(self, fast: bool) -> None:
        """The user's explicit choice for the current chat (saved on the conversation)."""
        model_name = self.config.fast_model_name if fast else self.config.model_name
        chat_id = self._current_chat_id
        if chat_id is not None:
            try:
                self.store.set_chat_model(chat_id, model_name)
            except AppError as exc:
                self._storage_failed(exc)
        self._apply_model(model_name)
        if self._model_presence is None and self._health_checks and not self.demo_mode:
            self.check_health()

    def _on_health_error(self, error: object) -> None:
        self._health_handle = None
        message = error.message if isinstance(error, AppError) else str(error)
        self.set_health(HealthResult(ConnectionState.DISCONNECTED, message))
        self.healthChecked.emit(self._health)
        self._resume_pending()

    def _resume_pending(self) -> None:
        chat_id, self._pending_chat_id = self._pending_chat_id, None
        kind, self._pending_kind = self._pending_kind, JOB_CHAT
        if chat_id is None:
            return
        self.composer.set_busy(False)
        if chat_id != self._current_chat_id:
            return
        if self._health.state is not ConnectionState.CONNECTED:
            self._show_not_ready()
            return
        try:
            text = self.service.last_user_text(chat_id) or ""
            if kind == JOB_PLAN:
                self._start_plan(chat_id, text)
                return
            context = self._context_for(chat_id, text, classify(text), [])
            messages = self.service.regenerate(chat_id, context)
        except AppError as exc:
            self._storage_failed(exc, card=True)
            return
        self._start_ollama(chat_id, messages)

    # --- generation ------------------------------------------------------------
    def is_busy(self) -> bool:
        return self._handle is not None or self._pending_chat_id is not None

    def _add_assistant_widget(self, status: str | None) -> AssistantMessage:
        widget = self.chat_view.add_assistant_message(status)
        widget.fileOpened.connect(self.open_file)
        widget.exportRequested.connect(lambda: self.export_project(as_zip=False))
        widget.regenerateRequested.connect(self.regenerate)
        widget.thumbsDownToggled.connect(lambda checked, w=widget: self._on_feedback(w, checked))
        return widget

    def _context_for(self, chat_id: str, text: str, task: TaskType, attachments: list[str]) -> str | None:
        """Project files and attachments for the request (read here, sizes capped)."""
        budget = self.service.context_budget_chars()
        try:
            project = self.store.latest_project_for_chat(chat_id)
        except AppError as exc:
            logger.warning("Could not load the chat's project: %s", exc.full_text())
            project = None
        attached = read_attachments(attachments, budget) if attachments else []
        use_project = project is not None and task in CONTEXT_TASKS and Path(project.path).is_dir()
        if not use_project and not attached:
            return None
        files = read_project_files(Path(project.path), budget * 2) if use_project else {}
        return build_context(text, project.name if use_project else None, files, attached, budget)

    def submit_prompt(self, text: str, project_mode: bool = False) -> bool:
        text = text.strip()
        if not text or self.is_busy():
            return False
        attachments = self.composer.attachments()
        self._replace_reply_chat = None  # a new question never replaces earlier answers
        task = classify(text, project_mode, attachments)
        logger.info("Request classified as %s", task.value)
        try:
            if self._current_chat_id is None or not self.store.chat_exists(self._current_chat_id):
                self._current_chat_id = None
                if self.new_chat() is None:
                    return False
            chat_id = self._current_chat_id
            if task is TaskType.PROJECT and not self.demo_mode:
                self.service.add_user_message(chat_id, text)
                payload: object = text
                kind = JOB_PLAN
            else:
                payload = self.service.send(chat_id, text, self._context_for(chat_id, text, task, attachments))
                kind = JOB_CHAT
        except AppError as exc:
            self._storage_failed(exc, card=True)
            return False
        self._refresh_sidebar()
        self.chat_view.add_user_message(text)
        self._dispatch(chat_id, payload, kind)
        return True

    def regenerate(self) -> None:
        """Re-run the last user message (also used by Retry)."""
        chat_id = self._current_chat_id
        if self.is_busy() or chat_id is None:
            return
        try:
            text = self.service.last_user_text(chat_id) or ""
            task = classify(text)
            if task is TaskType.PROJECT and not self.demo_mode:
                payload: object = text
                kind = JOB_PLAN
            else:
                payload = self.service.regenerate(chat_id, self._context_for(chat_id, text, task, []))
                kind = JOB_CHAT
        except AppError as exc:
            self.show_toast(exc.message)
            return
        self.chat_view.remove_items_after_last_user()
        self._replace_reply_chat = chat_id
        self._dispatch(chat_id, payload, kind)

    def retry(self) -> None:
        """Re-run the health check, then send the last user message if Ollama is ready."""
        chat_id = self._current_chat_id
        if self.is_busy() or chat_id is None:
            return
        if self.demo_mode:
            self.regenerate()
            return
        try:
            text = self.service.last_user_text(chat_id) or ""
        except AppError as exc:
            self._storage_failed(exc)
            return
        self.chat_view.remove_items_after_last_user()
        self._replace_reply_chat = chat_id
        self._pending_kind = JOB_PLAN if classify(text) is TaskType.PROJECT else JOB_CHAT
        self._wait_for_health(chat_id, force_check=True)

    def _dispatch(self, chat_id: str, payload: object, kind: str = JOB_CHAT) -> None:
        if self.demo_mode:
            self._start_fake(chat_id)
        elif self._health.state is ConnectionState.CONNECTED:
            if kind == JOB_PLAN:
                self._start_plan(chat_id, str(payload))
            else:
                self._start_ollama(chat_id, payload)  # type: ignore[arg-type]
        elif self._health.state is ConnectionState.CHECKING:
            self._pending_kind = kind
            self._wait_for_health(chat_id, force_check=False)
        else:
            self._show_not_ready()

    def _wait_for_health(self, chat_id: str, force_check: bool) -> None:
        self._pending_chat_id = chat_id
        self.composer.set_busy(True)
        if force_check or self._health_handle is None:
            self.set_health(HealthResult(ConnectionState.CHECKING, "Checking Ollama…"))
        self.check_health()

    def _show_not_ready(self) -> ErrorCard:
        card = self.chat_view.add_error(self._health.message)
        card.retryRequested.connect(self.retry)
        return card

    def _begin_stream(self, chat_id: str, worker, status: str, kind: str = JOB_CHAT) -> None:
        self._active_message = self._add_assistant_widget(status)
        self._active_chat_id = chat_id
        self._active_model = self._selected_model
        self._job_kind = kind
        self._got_first_token = False
        worker.token.connect(self._on_token)
        worker.finished.connect(self._on_finished)
        worker.cancelled.connect(self._on_cancelled)
        worker.error.connect(self._on_error)
        if hasattr(worker, "progress"):
            worker.progress.connect(self._on_progress)
        self._handle = start_worker(worker, self)
        self.composer.set_busy(True)

    def _start_fake(self, chat_id: str) -> None:
        worker = FakeStreamWorker(demo.DEMO_ANSWER, demo.DEMO_ANSWER_FILES, delay_s=self.token_delay_s)
        self._begin_stream(chat_id, worker, demo.DEMO_STATUS)
        logger.info("Demo stream started")

    def _start_ollama(self, chat_id: str, messages: list[dict]) -> None:
        worker = OllamaStreamWorker(self._new_client(), messages)
        self._begin_stream(chat_id, worker, STATUS_LOADING)
        logger.info("Model stream started (%d messages)", len(messages))

    def _start_plan(self, chat_id: str, request: str) -> None:
        worker = PlanWorker(self._new_client(), request, self.service.system_prompt)
        self._begin_stream(chat_id, worker, STATUS_PLANNING, JOB_PLAN)
        logger.info("Project planning started")

    def start_generation(self, chat_id: str, plan: ProjectPlan, card: PlanCard | None = None) -> bool:
        """Apply a plan: create the project folder and generate its files in a worker."""
        if self.is_busy() or self._health.state is not ConnectionState.CONNECTED:
            reason = "Another answer is still running." if self.is_busy() else self._health.message
            if card is not None:
                card.set_state(f"Not started: {reason}")
            self.show_toast(reason)
            return False
        try:
            writer = ProjectWriter(self.config.projects_dir, plan.project_name)
        except OSError as exc:
            error = AppError(f"Could not create the project folder in '{self.config.projects_dir}'.", detail=str(exc))
            self._storage_failed(error, card=True)
            if card is not None:
                card.set_state("Not started: the project folder could not be created.")
            return False
        try:
            self._active_project = self.store.create_project(plan.project_name, str(writer.root), chat_id,
                                                             "generating")
        except AppError as exc:
            self._storage_failed(exc)
            self._active_project = None
        self._active_plan_card = card
        self._active_writer_root = writer.root
        if card is not None:
            card.set_state(f"Generating into {writer.root}")
        worker = GenerateWorker(self._new_client(), plan, writer, self.service.system_prompt)
        self._active_plan = plan
        self._begin_stream(chat_id, worker, f"Generating {len(plan.files)} files…", JOB_GENERATE)
        logger.info("Project generation started: %d files", len(plan.files))
        return True

    def stop_generation(self) -> None:
        if self._pending_chat_id is not None and self._handle is None:
            self._pending_chat_id = None
            self._pending_kind = JOB_CHAT
            self.composer.set_busy(False)
            return
        if self._handle is None:
            return
        handle = self._handle
        handle.cancel()
        if not handle.wait(STOP_WAIT_MS):
            logger.warning("Stream thread did not stop within %d ms", STOP_WAIT_MS)
        # the queued 'cancelled' signal may not be delivered yet; finish the UI state now
        self._on_cancelled()

    def _from_active_worker(self) -> bool:
        """False for late queued signals from a worker that was already stopped.

        After Stop, the old worker's 'cancelled' can arrive after the next stream started;
        it must not end that new stream. Direct calls (including from other slots, such
        as the Stop button) are always accepted.
        """
        if self._handle is None:
            return False
        sender = self.sender()
        return not isinstance(sender, StreamWorker) or sender is self._handle.worker

    def _on_token(self, token: str) -> None:
        if self._active_message is None or not self._from_active_worker():
            return
        if not self._got_first_token:
            self._got_first_token = True
            if not self.demo_mode:
                self._active_message.set_status(STATUS_GENERATING)
        self._active_message.append_token(token)

    def _on_progress(self, text: str) -> None:
        if self._active_message is not None and self._from_active_worker():
            self._active_message.set_status(text)

    def _on_finished(self, result: object) -> None:
        if not self._from_active_worker():
            return
        if self._job_kind == JOB_PLAN:
            self._plan_finished(result)
        elif self._job_kind == JOB_GENERATE:
            self._generation_finished(result)
        elif self._job_kind == JOB_TOOL:
            self._tool_finished(result)
        else:
            self._chat_finished(result)
        self.streamFinished.emit()

    def _chat_finished(self, result: object) -> None:
        data = result if isinstance(result, dict) else {}
        text = str(data.get("text", ""))
        files = list(data.get("files", []))
        status = demo.DEMO_STATUS if self.demo_mode else finished_status(self._active_model, data.get("stats"))
        message = self._active_message
        chat_id = self._active_chat_id
        if message is not None:
            message.set_text(text)
            for path in files:
                message.add_file_card(path)
            message.finish(status=status)
        if chat_id:
            stats = data.get("stats") if isinstance(data.get("stats"), StreamStats) else None
            saved = self._save_reply(chat_id, text, "complete", files, stats,
                                     model_name=None if self.demo_mode else self._active_model)
            if saved is not None and message is not None:
                message.message_id = saved.id
        self._end_stream()
        if chat_id and not self.demo_mode:
            offered = self._offer_changes(chat_id, text)
            if not offered and chat_id in self._repair and self._repair[chat_id].round > 0:
                self._repair.pop(chat_id, None)
                self.show_toast("The model did not propose a usable fix, so the repair loop stopped.")

    def _plan_finished(self, result: object) -> None:
        chat_id = self._active_chat_id
        message = self._active_message
        self._end_stream()
        if not isinstance(result, ProjectPlan) or chat_id is None:
            return
        text = result.to_markdown()
        if message is not None:
            message.set_text(text)
            message.finish(status=STATUS_PLAN_READY)
        saved = self._save_reply(chat_id, text, "complete", model_name=self._active_model)
        if saved is not None and message is not None:
            message.message_id = saved.id
        card = PlanCard(result, fast_mode=self._active_model == self.config.fast_model_name)
        card.applyRequested.connect(lambda c=card, cid=chat_id: self.start_generation(cid, c.plan, c))
        self.chat_view.add_card(card)
        self.plan_cards.append(card)

    def _generation_finished(self, result: object) -> None:
        if isinstance(result, GenerationResult):
            self._show_generation_result(result)
        else:
            self._end_stream()

    def _show_generation_result(self, result: GenerationResult) -> None:
        chat_id = self._active_chat_id
        message = self._active_message
        project = self._active_project
        card = self._active_plan_card
        self._end_stream()
        report = validate_project(result.root, result.written)
        text = f"{result.summary_markdown()}\n\n{report.summary()}"
        if message is not None:
            message.set_text(text)
            for path in result.written:
                message.add_file_card(path)
            message.finish(status=f"Project {result.status}")
        if card is not None:
            card.set_state(f"{len(result.written)} of {len(result.plan.files)} files written ({result.status})")
        if project is not None:
            try:
                self.store.update_project_status(project.id, result.status)
            except AppError as exc:
                self._storage_failed(exc)
        if chat_id:
            saved = self._save_reply(chat_id, text, "stopped" if result.cancelled else "complete",
                                     result.written, project_id=project.id if project else None,
                                     model_name=self._active_model)
            if saved is not None and message is not None:
                message.message_id = saved.id
        self._show_project_files(result.plan.project_name, result.root)
        self._refresh_projects()
        if result.written and chat_id == self._current_chat_id:
            self.open_file(result.written[0])

    # --- approved commands -------------------------------------------------------------
    def _ask_approval(self, command: str, working_dir: str) -> bool:
        dialog = CommandApprovalDialog(command, working_dir, "The command runs on your computer inside the "
                                       "project folder. Review it before approving.", self)
        return dialog.exec() == CommandApprovalDialog.DialogCode.Accepted

    def _command_refused(self, text: str) -> None:
        card = self.chat_view.add_error(text)
        card.retry_button.hide()

    def run_project_command(self, argv: list[str]) -> bool:
        """Run one command (allowlist check, then approval). Not part of a repair loop."""
        return self.run_project_commands([argv])

    def run_project_commands(self, commands: list[list[str]]) -> bool:
        """Allowlist check, then the user's approval, then run in a worker. Never runs model text."""
        chat_id = self._current_chat_id
        if self.is_busy() or chat_id is None:
            return False
        try:
            project = self.store.latest_project_for_chat(chat_id)
        except AppError as exc:
            self._storage_failed(exc)
            return False
        if project is None:
            self.show_toast("This chat has no project to run commands in.")
            self._repair.pop(chat_id, None)
            return False
        try:
            runner = ToolRunner(Path(project.path), self.config.command_timeout_s)
            checked = [runner.check(argv) for argv in commands]  # refused here even if the user would approve
            for argv in checked:
                runner.resolve_executable(argv[0])
        except AppError as exc:
            logger.warning("Command refused: %s", exc.full_text())
            self._command_refused(exc.message)
            self._repair.pop(chat_id, None)
            return False
        command_text = "\n".join(display_command(argv) for argv in checked)
        if not self.approver(command_text, str(runner.root)):
            self._command_refused(
                CommandRejectedError(f"You rejected the command, so it was not run: {command_text}").message)
            self._repair.pop(chat_id, None)
            return False
        worker = ToolWorker(runner, checked)
        self._active_commands = checked
        self._begin_stream(chat_id, worker, f"{STATUS_RUNNING} {display_command(checked[0])}", JOB_TOOL)
        return True

    def run_project_tests(self) -> bool:
        """Run the project's tests; if they fail, start the repair loop (at most 3 model-proposed fixes)."""
        chat_id = self._current_chat_id
        if self.is_busy():
            return False
        try:
            project = self.store.latest_project_for_chat(chat_id) if chat_id else None
        except AppError as exc:
            self._storage_failed(exc)
            return False
        if project is None:
            self.show_toast("This chat has no project to test.")
            return False
        commands = default_test_commands(Path(project.path))
        if commands is None:
            self.show_toast("No tests or sources were found in this project.")
            return False
        self._repair[chat_id] = RepairLoop(commands)
        return self.run_project_commands(commands)

    def repair_round(self, chat_id: str) -> int:
        loop = self._repair.get(chat_id)
        return loop.round if loop else 0

    def _tool_finished(self, result: object) -> None:
        chat_id = self._active_chat_id
        message = self._active_message
        planned = len(self._active_commands)
        self._end_stream()
        results = [r for r in result if isinstance(r, CommandResult)] if isinstance(result, list) else []
        if not results:
            return
        self.command_results.extend(results)
        ok = all(r.ok for r in results) and len(results) == planned
        text = results_markdown(results, planned)
        loop = self._repair.get(chat_id) if chat_id else None
        next_round = 0
        if loop is not None:
            if ok:
                done = f" after {loop.round} repair round{'s' if loop.round != 1 else ''}" if loop.round else ""
                text += f"\n\n**All checks passed{done}.**"
                self._repair.pop(chat_id, None)
            elif loop.round >= MAX_REPAIR_ROUNDS:
                text += (f"\n\n**Stopped after {MAX_REPAIR_ROUNDS} repair rounds; the checks still fail.** "
                         "Nothing more was changed.")
                self._repair.pop(chat_id, None)
            else:
                loop.round += 1
                next_round = loop.round
                text += f"\n\n**Repair round {next_round} of {MAX_REPAIR_ROUNDS}:** asking the model for a fix…"
        if message is not None:
            message.set_text(text)
            message.finish(status=STATUS_CHECKS_PASSED if ok else STATUS_CHECKS_FAILED)
        if chat_id:
            saved = self._save_reply(chat_id, text, "complete" if ok else "error", kind="tool")
            if saved is not None and message is not None:
                message.message_id = saved.id
        if next_round and chat_id:
            QTimer.singleShot(0, lambda: self._start_repair(chat_id, results, next_round))

    def _start_repair(self, chat_id: str, results: list[CommandResult], round_no: int) -> None:
        """Send the trimmed failure output and the relevant files to the model; the fix comes back as a diff."""
        if self.is_busy() or chat_id != self._current_chat_id or chat_id not in self._repair:
            self._repair.pop(chat_id, None)
            return
        try:
            project = self.store.latest_project_for_chat(chat_id)
            if project is None:
                raise AppError("This chat has no project to repair.")
            budget = self.service.context_budget_chars()
            failure = trimmed_failure_output(results, budget // 3)
            files = read_project_files(Path(project.path), budget * 2)
            context = f"{failure}\n\n" + build_context(failure, project.name, files, [], budget - len(failure))
            text = f"Repair round {round_no}/{MAX_REPAIR_ROUNDS}: the checks failed. Please fix the code."
            messages = self.service.send(chat_id, text, context)
        except AppError as exc:
            self._repair.pop(chat_id, None)
            self._storage_failed(exc, card=True)
            return
        self.chat_view.add_user_message(text)
        self._refresh_sidebar()
        self._dispatch(chat_id, messages, JOB_CHAT)

    def _offer_changes(self, chat_id: str, answer: str) -> bool:
        """If the answer proposes edits to the chat's project, show them as a Changes card."""
        try:
            project = self.store.latest_project_for_chat(chat_id)
        except AppError:
            return False
        if project is None or not Path(project.path).is_dir():
            return False
        changes = parse_changes(answer, list_project_files(Path(project.path)))
        if not changes:
            return False
        pending, problems = prepare_changes(Path(project.path), changes)
        if not pending:
            self.show_toast("The suggested changes could not be used: " + "; ".join(problems.values())[:200])
            return False
        card = ChangesCard(project.name, pending, problems)
        card.applyRequested.connect(lambda c=card, p=project, cid=chat_id: self.apply_suggested_changes(c, p, cid))
        card.cancelRequested.connect(lambda cid=chat_id: self._repair.pop(cid, None))
        self.chat_view.add_card(card)
        self.changes_cards.append(card)
        return True

    def apply_suggested_changes(self, card: ChangesCard, project: ProjectRecord, chat_id: str | None = None) -> bool:
        root = Path(project.path)
        try:
            written = apply_changes(root, card.pending)
        except (AppError, OSError) as exc:
            message = exc.message if isinstance(exc, AppError) else str(exc)
            logger.warning("Applying changes failed: %s", message)
            card.set_state(f"Not applied: {message}")
            if chat_id:
                self._repair.pop(chat_id, None)
            return False
        card.set_state(f"Applied to {len(written)} file{'s' if len(written) != 1 else ''}; originals backed up.")
        try:
            self.store.update_project_status(project.id, "complete")
        except AppError as exc:
            logger.warning("Could not update the project: %s", exc.full_text())
        self._show_project_files(project.name, root)
        loop = self._repair.get(chat_id) if chat_id else None
        if loop is not None and chat_id == self._current_chat_id:
            QTimer.singleShot(0, lambda: self.run_project_commands(loop.commands))  # re-run (asks approval again)
        return True

    def _on_cancelled(self) -> None:
        if not self._from_active_worker():
            return
        if self._job_kind == JOB_GENERATE:
            worker = self._handle.worker if self._handle is not None else None
            result = getattr(worker, "result", None)
            if not isinstance(result, GenerationResult) and self._active_plan is not None:
                root = self._active_writer_root
                written = list_project_files(root) if root is not None else []
                result = GenerationResult(self._active_plan, root or Path(), written=written)
            if isinstance(result, GenerationResult):
                result.cancelled = True
                self._show_generation_result(result)
                return
        message = self._active_message
        if message is not None:
            if self._job_kind == JOB_PLAN:
                message.set_text(message.text() or "Planning was stopped.")
            elif self._job_kind == JOB_TOOL:
                message.set_text("The command was stopped. Its process tree was ended.")
            message.finish(status=STATUS_STOPPED)
            if self._active_chat_id:
                saved = self._save_reply(self._active_chat_id, message.text(), "stopped",
                                         kind="tool" if self._job_kind == JOB_TOOL else "chat")
                if saved is not None:
                    message.message_id = saved.id
        self._end_stream()

    def _on_error(self, error: object) -> None:
        if not self._from_active_worker():
            return
        err = error if isinstance(error, AppError) else AppError(str(error))
        message = self._active_message
        if message is not None:
            if message.text():
                message.finish(status=STATUS_FAILED)
            else:
                self.chat_view.remove_items_after_last_user()
        if isinstance(err, ModelNotFoundError):
            self.set_health(HealthResult(ConnectionState.MODEL_MISSING, err.message))
        elif isinstance(err, OllamaUnavailableError) and "not running" in err.message:
            self.set_health(HealthResult(ConnectionState.DISCONNECTED, err.message))
        text = err.message
        if self._job_kind == JOB_PLAN and isinstance(err, ResponseFormatError):
            detail = f" ({err.detail})" if err.detail else ""
            text = f"The model's project plan could not be used: {err.message}{detail} Try again or rephrase."
        if self._job_kind == JOB_GENERATE:
            if self._active_plan_card is not None:
                self._active_plan_card.set_state("Generation failed.")
            if self._active_project is not None:
                try:
                    self.store.update_project_status(self._active_project.id, "failed")
                except AppError:
                    logger.warning("Could not mark the project as failed")
        chat_id = self._active_chat_id
        card = self.chat_view.add_error(text)
        card.retryRequested.connect(self.retry)
        self._end_stream()
        if chat_id:
            self._save_reply(chat_id, text, "error")  # friendly text only, never a traceback

    def _end_stream(self) -> None:
        self._handle = None
        self._active_message = None
        self._active_chat_id = None
        self._active_project = None
        self._active_plan_card = None
        self._active_plan = None
        self._active_writer_root = None
        self._job_kind = JOB_CHAT
        self.composer.set_busy(False)

    def _show_project_files(self, name: str, root: Path) -> None:
        files = read_project_files(root, PREVIEW_MAX_CHARS) if root.is_dir() else {}
        self.preview.set_project(name, files)

    def _load_chat_project(self, chat_id: str) -> None:
        """Show the chat's latest project in the preview panel (so file cards open)."""
        if self.demo_mode:
            return
        try:
            project = self.store.latest_project_for_chat(chat_id)
        except AppError as exc:
            logger.warning("Could not load the chat's project: %s", exc.full_text())
            project = None
        if project is None:
            self.preview.clear_project()
        else:
            self._show_project_files(project.name, Path(project.path))

    def open_project(self, project_id: str) -> None:
        """Sidebar Projects list: show the project's files and its chat."""
        if self.demo_mode:
            self.open_preview()
            return
        try:
            project = self.store.get_project(project_id)
            linked = project.conversation_id if project.conversation_id and \
                self.store.chat_exists(project.conversation_id) else None
        except AppError as exc:
            self._storage_failed(exc)
            return
        if linked and linked != self._current_chat_id:
            self.select_chat(linked)
        root = Path(project.path)
        if not root.is_dir():
            self.show_toast(f"The project folder no longer exists: {root}")
            return
        self._show_project_files(project.name, root)
        self.open_preview()

    # --- preview ---------------------------------------------------------------
    def is_preview_open(self) -> bool:
        return not self.preview.isHidden()

    def open_preview(self) -> None:
        if self.preview.isHidden():
            self.preview.show()
            total = max(self.splitter.width(), theme.CHAT_MIN_WIDTH + theme.PREVIEW_MIN_WIDTH)
            preview_width = int(total * PREVIEW_SHARE)
            self.splitter.setSizes([total - preview_width, preview_width])
        self.files_button.setChecked(True)
        if self.preview.current_path() is None and self.preview.files():
            self.preview.open_file(self.preview.files()[0])

    def open_file(self, path: str) -> None:
        self.open_preview()
        self.preview.open_file(path)

    def close_preview(self) -> None:
        if self._expanded:
            self.set_preview_expanded(False)
        self.preview.hide()
        self.files_button.setChecked(False)

    def toggle_preview(self) -> None:
        if self.preview.isHidden():
            self.open_preview()
        else:
            self.close_preview()

    def set_preview_expanded(self, expanded: bool) -> None:
        self._expanded = expanded
        self.sidebar.setVisible(not expanded)
        self.chat_panel.setVisible(not expanded)
        if self.preview.expand_button.isChecked() != expanded:
            self.preview.expand_button.setChecked(expanded)

    # --- feedback --------------------------------------------------------------
    def show_toast(self, text: str) -> None:
        self.toast.setText(text)
        self.toast.adjustSize()
        x = (self.chat_panel.width() - self.toast.width()) // 2
        self.toast.move(max(8, x), theme.TOP_BAR_HEIGHT + 12)
        self.toast.raise_()
        self.toast.show()
        self._toast_timer.start(TOAST_MS)

    # --- export and settings ------------------------------------------------------------
    def _choose_folder(self, start: str) -> str | None:
        chosen = QFileDialog.getExistingDirectory(self, "Export to folder", start)
        return chosen or None

    def _open_folder(self, folder: str) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def export_dir(self) -> str:
        try:
            saved = self.store.get_setting(EXPORT_DIR_SETTING)
        except AppError:
            saved = None
        return saved or str(self.config.export_dir)

    def export_project(self, as_zip: bool = False) -> bool:
        """Export the current chat's project to a chosen folder (or a verified ZIP) in a worker."""
        if self._export_handle is not None:
            self.show_toast("An export is already running.")
            return False
        chat_id = self._current_chat_id
        try:
            project = self.store.latest_project_for_chat(chat_id) if chat_id else None
        except AppError as exc:
            self._storage_failed(exc)
            return False
        if project is None or not Path(project.path).is_dir():
            self.show_toast(NO_PROJECT_TO_EXPORT)
            return False
        chosen = self.folder_chooser(self.export_dir())
        if not chosen:
            return False
        try:
            self.store.set_setting(EXPORT_DIR_SETTING, chosen)
        except AppError as exc:
            logger.warning("Could not remember the export folder: %s", exc.full_text())
        worker = ExportWorker(Path(project.path), Path(chosen), project.name, as_zip)
        self._export_as_zip = as_zip
        # bound methods (not lambdas) so Qt delivers these on the UI thread
        worker.finished.connect(self._on_exported)
        worker.error.connect(self._on_export_error)
        self._export_handle = start_worker(worker, self)
        self.show_toast("Creating and checking the ZIP…" if as_zip else "Exporting the project…")
        return True

    def _on_exported(self, result: object) -> None:
        self._export_handle = None
        self.toast.hide()  # the "Exporting…" notice is finished; the card says the rest
        card = ExportCard(result, self._export_as_zip)
        card.openRequested.connect(self._open_export_folder)
        self.chat_view.add_card(card)
        self.export_cards.append(card)
        self.exportFinished.emit(result)

    def _open_export_folder(self, folder: str) -> None:
        self.folder_opener(folder)

    def _on_export_error(self, error: object) -> None:
        self._export_handle = None
        err = error if isinstance(error, AppError) else AppError(str(error))
        logger.warning("Export failed: %s", err.full_text())
        card = self.chat_view.add_error(f"Export failed: {err.message}")
        card.retry_button.hide()
        self.exportFinished.emit(err)

    def _load_saved_settings(self) -> None:
        try:
            raw = self.store.get_setting(COMMAND_TIMEOUT_SETTING)
        except AppError:
            raw = None
        if raw:
            try:
                self.config = replace(self.config, command_timeout_s=float(max(1, min(3600, int(float(raw))))))
            except ValueError:
                logger.warning("Ignoring a bad saved command timeout: %r", raw)
        try:
            self._fast_default = self.store.get_setting(DEFAULT_MODEL_MODE_SETTING) == "fast"
        except AppError:
            self._fast_default = False

    def _edit_settings(self, export_dir: str, timeout_s: float) -> tuple | None:
        dialog = SettingsDialog(export_dir, timeout_s, self, model_name=self.config.model_name,
                                fast_default=self._fast_default, fast_model_name=self.config.fast_model_name)
        if dialog.exec() == SettingsDialog.DialogCode.Accepted:
            return (*dialog.values(), dialog.fast_default())
        return None

    def open_settings(self) -> None:
        values = self.settings_editor(self.export_dir(), self.config.command_timeout_s)
        if values is None:
            return
        export_dir, timeout_s = values[0], values[1]
        fast_default = bool(values[2]) if len(values) > 2 else self._fast_default
        try:
            if export_dir:
                self.store.set_setting(EXPORT_DIR_SETTING, export_dir)
            self.store.set_setting(COMMAND_TIMEOUT_SETTING, str(int(timeout_s)))
            self.store.set_setting(DEFAULT_MODEL_MODE_SETTING, "fast" if fast_default else "quality")
        except AppError as exc:
            self._storage_failed(exc)
            return
        self.config = replace(self.config, command_timeout_s=float(timeout_s))
        self._fast_default = fast_default
        self.show_toast("Settings saved.")

    # --- lifecycle -------------------------------------------------------------
    def closeEvent(self, event) -> None:  # noqa: N802
        self._health_timer.stop()
        if self._handle is not None:
            self._handle.cancel()
            self._handle.wait(CLOSE_WAIT_MS)
            self._handle = None
        if self._health_handle is not None:
            self._health_handle.wait(CLOSE_WAIT_MS)
            self._health_handle = None
        if self._export_handle is not None:
            self._export_handle.wait(CLOSE_WAIT_MS)
            self._export_handle = None
        super().closeEvent(event)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(1600, 900)
