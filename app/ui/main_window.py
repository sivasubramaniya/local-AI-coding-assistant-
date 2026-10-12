"""Main window: Sidebar | QSplitter(chat panel, preview panel).

The window wires widgets to the chat service, the Ollama workers and the health
checks. Business rules (message building, trimming, history) live in
app.backend.chat_service; network work runs in worker threads.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtWidgets import (
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
    default_test_command,
    display_command,
    result_markdown,
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
from app.backend.ollama_client import OllamaClient, StreamStats
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
from app.ui.agent_widgets import ChangesCard, PlanCard
from app.ui.dialogs import CommandApprovalDialog
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
    ToolWorker,
    WorkerHandle,
    start_worker,
)
from app.validation.project_validator import validate_project

logger = logging.getLogger(__name__)

EXPORT_PENDING = "Export is coming in Phase 9."
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


def finished_status(config: AppConfig, stats: StreamStats | None) -> str:
    if stats is None:
        return reply_status(config.model_name, None, None)
    return reply_status(config.model_name, stats.eval_count, stats.tokens_per_second)


class MainWindow(QMainWindow):
    streamFinished = Signal()
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
        # Asks the user to approve a command (command text, working dir) -> bool. Tests replace it.
        self.approver: Callable[[str, str], bool] = self._ask_approval
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
        self.export_zip_action = more.addAction("Export ZIP", self._export_pending)
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
        sb.settingsRequested.connect(lambda: self.show_toast("Settings arrive in a later phase."))

        self.composer.sendRequested.connect(self.submit_prompt)
        self.composer.stopRequested.connect(self.stop_generation)

        self.export_button.clicked.connect(self._export_pending)
        self.files_button.clicked.connect(self.toggle_preview)

        self.preview.closeRequested.connect(self.close_preview)
        self.preview.expandToggled.connect(self.set_preview_expanded)
        self.preview.exportRequested.connect(lambda _path: self._export_pending())

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
                chat_id = self.store.create_chat(model_name=self.config.model_name).id
            except AppError as exc:
                self._storage_failed(exc)
                return None
        self._set_current(chat_id)
        self.chat_view.clear()
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
        for message in messages:
            self._render_stored(chat, message)
        self._load_chat_project(chat_id)
        self._refresh_sidebar()
        QTimer.singleShot(0, self.chat_view.scroll_to_bottom)

    def _render_stored(self, chat: Conversation, message: ChatMessage) -> None:
        if message.role == "user":
            self.chat_view.add_user_message(message.content)
            return
        if message.status == "error":
            card = self.chat_view.add_error(message.content)
            card.retryRequested.connect(self.retry)
            return
        if message.status == "stopped":
            status = STATUS_STOPPED
        elif self.demo_mode:
            status = demo.DEMO_STATUS
        else:
            status = reply_status(chat.model_name or self.config.model_name, message.eval_count,
                                  message.tokens_per_sec)
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
                    stats: StreamStats | None = None, project_id: str | None = None) -> ChatMessage | None:
        has_stats = stats is not None and stats.eval_count > 0
        try:
            return self.service.record_reply(
                chat_id, text, status, files,
                eval_count=stats.eval_count if has_stats else None,
                tokens_per_sec=round(stats.tokens_per_second, 2) if has_stats else None,
                project_id=project_id,
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
        worker = HealthCheckWorker(self._client_factory())
        worker.finished.connect(self._on_health)
        worker.error.connect(self._on_health_error)
        self._health_handle = start_worker(worker, self)

    def _on_health(self, result: object) -> None:
        self._health_handle = None
        if isinstance(result, HealthResult):
            self.set_health(result)
            self.healthChecked.emit(result)
        self._resume_pending()

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
        widget.exportRequested.connect(self._export_pending)
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
        worker = OllamaStreamWorker(self._client_factory(), messages)
        self._begin_stream(chat_id, worker, STATUS_LOADING)
        logger.info("Model stream started (%d messages)", len(messages))

    def _start_plan(self, chat_id: str, request: str) -> None:
        worker = PlanWorker(self._client_factory(), request, self.service.system_prompt)
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
        worker = GenerateWorker(self._client_factory(), plan, writer, self.service.system_prompt)
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
        status = demo.DEMO_STATUS if self.demo_mode else finished_status(self.config, data.get("stats"))
        message = self._active_message
        chat_id = self._active_chat_id
        if message is not None:
            message.set_text(text)
            for path in files:
                message.add_file_card(path)
            message.finish(status=status)
        if chat_id:
            stats = data.get("stats") if isinstance(data.get("stats"), StreamStats) else None
            saved = self._save_reply(chat_id, text, "complete", files, stats)
            if saved is not None and message is not None:
                message.message_id = saved.id
        self._end_stream()
        if chat_id and not self.demo_mode:
            self._offer_changes(chat_id, text)

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
        saved = self._save_reply(chat_id, text, "complete")
        if saved is not None and message is not None:
            message.message_id = saved.id
        card = PlanCard(result)
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
                                     result.written, project_id=project.id if project else None)
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
            return False
        try:
            runner = ToolRunner(Path(project.path), self.config.command_timeout_s)
            checked = runner.check(argv)  # refused here even if the user would approve it
            runner.resolve_executable(checked[0])
        except AppError as exc:
            logger.warning("Command refused: %s", exc.full_text())
            self._command_refused(exc.message)
            return False
        command = display_command(checked)
        if not self.approver(command, str(runner.root)):
            self._command_refused(CommandRejectedError(f"You rejected the command, so it was not run: {command}").message)
            return False
        worker = ToolWorker(runner, checked)
        self._begin_stream(chat_id, worker, f"{STATUS_RUNNING} {command}", JOB_TOOL)
        return True

    def run_project_tests(self) -> bool:
        chat_id = self._current_chat_id
        try:
            project = self.store.latest_project_for_chat(chat_id) if chat_id else None
        except AppError as exc:
            self._storage_failed(exc)
            return False
        if project is None:
            self.show_toast("This chat has no project to test.")
            return False
        argv = default_test_command(Path(project.path))
        if argv is None:
            self.show_toast("No tests were found in this project.")
            return False
        return self.run_project_command(argv)

    def _tool_finished(self, result: object) -> None:
        chat_id = self._active_chat_id
        message = self._active_message
        self._end_stream()
        if not isinstance(result, CommandResult):
            return
        self.command_results.append(result)
        text = result_markdown(result)
        status = "Command passed" if result.ok else "Command failed"
        if message is not None:
            message.set_text(text)
            message.finish(status=status)
        if chat_id:
            saved = self._save_reply(chat_id, text, "complete" if result.ok else "error")
            if saved is not None and message is not None:
                message.message_id = saved.id

    def _offer_changes(self, chat_id: str, answer: str) -> None:
        """If the answer proposes edits to the chat's project, show them as a Changes card."""
        try:
            project = self.store.latest_project_for_chat(chat_id)
        except AppError:
            return
        if project is None or not Path(project.path).is_dir():
            return
        changes = parse_changes(answer)
        if not changes:
            return
        pending, problems = prepare_changes(Path(project.path), changes)
        if not pending:
            self.show_toast("The suggested changes could not be used: " + "; ".join(problems.values())[:200])
            return
        card = ChangesCard(project.name, pending, problems)
        card.applyRequested.connect(lambda c=card, p=project: self.apply_suggested_changes(c, p))
        self.chat_view.add_card(card)
        self.changes_cards.append(card)

    def apply_suggested_changes(self, card: ChangesCard, project: ProjectRecord) -> bool:
        root = Path(project.path)
        try:
            written = apply_changes(root, card.pending)
        except (AppError, OSError) as exc:
            message = exc.message if isinstance(exc, AppError) else str(exc)
            logger.warning("Applying changes failed: %s", message)
            card.set_state(f"Not applied: {message}")
            return False
        card.set_state(f"Applied to {len(written)} file{'s' if len(written) != 1 else ''}; originals backed up.")
        try:
            self.store.update_project_status(project.id, "complete")
        except AppError as exc:
            logger.warning("Could not update the project: %s", exc.full_text())
        self._show_project_files(project.name, root)
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
                saved = self._save_reply(self._active_chat_id, message.text(), "stopped")
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

    def _export_pending(self) -> None:
        self.show_toast(EXPORT_PENDING)

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
        super().closeEvent(event)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(1600, 900)
