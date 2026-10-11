"""Main window: Sidebar | QSplitter(chat panel, preview panel).

The window wires widgets to the chat service, the Ollama workers and the health
checks. Business rules (message building, trimming, history) live in
app.backend.chat_service; network work runs in worker threads.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

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

from app.backend.chat_service import ChatService
from app.backend.memory_store import InMemoryChatStore
from app.backend.ollama_client import OllamaClient, StreamStats
from app.backend.status import ConnectionState, HealthResult, stub_connection_state
from app.config import AppConfig
from app.errors import AppError, ModelNotFoundError, OllamaUnavailableError
from app.ui import demo, theme
from app.ui.chat_view import ChatView
from app.ui.composer import Composer
from app.ui.icons import icon_size, load_icon
from app.ui.message_widgets import AssistantMessage, ErrorCard
from app.ui.preview_panel import PreviewPanel
from app.ui.sidebar import Sidebar
from app.ui.workers import (
    FakeStreamWorker,
    HealthCheckWorker,
    OllamaStreamWorker,
    WorkerHandle,
    start_worker,
)

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


def finished_status(config: AppConfig, stats: StreamStats | None) -> str:
    name = config.model_base_name
    if stats is None or stats.eval_count <= 0:
        return name
    return f"{name} · {stats.eval_count} tokens · {stats.tokens_per_second:.1f} tok/s"


class MainWindow(QMainWindow):
    streamFinished = Signal()
    healthChecked = Signal(object)  # HealthResult

    def __init__(
        self,
        config: AppConfig,
        store: InMemoryChatStore | None = None,
        token_delay_s: float = 0.04,
        use_webengine: bool | None = None,
        demo_mode: bool = False,
        client_factory: Callable[[], OllamaClient] | None = None,
        health_checks: bool = True,
        system_prompt: str | None = None,
    ) -> None:
        super().__init__()
        self.config = config
        self.store = store or InMemoryChatStore()
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
            self.sidebar.set_projects([])
            self.new_chat()

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
        sb.projectSelected.connect(lambda _name: self.open_preview())
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
    def current_chat_id(self) -> str | None:
        return self._current_chat_id

    def _refresh_sidebar(self) -> None:
        chats = [(c.id, c.title) for c in self.store.list()]
        self.sidebar.set_chats(chats, self._current_chat_id)

    def new_chat(self) -> str:
        self.stop_generation()
        chat = self.store.create()
        self._current_chat_id = chat.id
        self.chat_view.clear()
        self._refresh_sidebar()
        self.composer.input.setFocus()
        return chat.id

    def select_chat(self, chat_id: str) -> None:
        if chat_id == self._current_chat_id and self.chat_view.items:
            return
        self.stop_generation()
        try:
            chat = self.store.get(chat_id)
        except AppError as exc:
            self.show_toast(exc.message)
            return
        self._current_chat_id = chat_id
        self.chat_view.clear()
        for message in chat.messages:
            if message.role == "user":
                self.chat_view.add_user_message(message.content)
            else:
                widget = self._add_assistant_widget(message.status)
                widget.set_text(message.content)
                for path in message.files:
                    widget.add_file_card(path)
                widget.finish()
        self._refresh_sidebar()
        QTimer.singleShot(0, self.chat_view.scroll_to_bottom)

    def rename_chat(self, chat_id: str, title: str) -> bool:
        try:
            self.store.rename(chat_id, title)
        except AppError as exc:
            self.show_toast(exc.message)
            return False
        self._refresh_sidebar()
        return True

    def delete_chat(self, chat_id: str) -> None:
        if chat_id == self._current_chat_id:
            self.stop_generation()
        try:
            self.store.delete(chat_id)
        except AppError as exc:
            self.show_toast(exc.message)
            return
        if chat_id == self._current_chat_id:
            remaining = self.store.list()
            if remaining:
                self._current_chat_id = None
                self.select_chat(remaining[0].id)
                return
            self.new_chat()
            return
        self._refresh_sidebar()

    def _ask_rename(self, chat_id: str) -> None:
        try:
            current = self.store.get(chat_id).title
        except AppError:
            return
        title, ok = QInputDialog.getText(self, "Rename chat", "New name:", text=current)
        if ok:
            self.rename_chat(chat_id, title)

    def _ask_delete(self, chat_id: str) -> None:
        try:
            title = self.store.get(chat_id).title
        except AppError:
            return
        answer = QMessageBox.question(
            self, "Delete chat", f"Delete “{title}”? This cannot be undone.",
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
        if chat_id is None:
            return
        self.composer.set_busy(False)
        if chat_id != self._current_chat_id or not self.store.exists(chat_id):
            return
        if self._health.state is ConnectionState.CONNECTED:
            self._start_ollama(chat_id, self.service.regenerate(chat_id))
        else:
            self._show_not_ready()

    # --- generation ------------------------------------------------------------
    def is_busy(self) -> bool:
        return self._handle is not None or self._pending_chat_id is not None

    def _add_assistant_widget(self, status: str | None) -> AssistantMessage:
        widget = self.chat_view.add_assistant_message(status)
        widget.fileOpened.connect(self.open_file)
        widget.exportRequested.connect(self._export_pending)
        widget.regenerateRequested.connect(self.regenerate)
        return widget

    def submit_prompt(self, text: str, project_mode: bool = False) -> bool:
        text = text.strip()
        if not text or self.is_busy():
            return False
        if self._current_chat_id is None or not self.store.exists(self._current_chat_id):
            self.new_chat()
        chat_id = self._current_chat_id
        messages = self.service.send(chat_id, text)
        self._refresh_sidebar()
        self.chat_view.add_user_message(text)
        self._dispatch(chat_id, messages)
        return True

    def regenerate(self) -> None:
        """Re-run the last user message (also used by Retry)."""
        chat_id = self._current_chat_id
        if self.is_busy() or chat_id is None:
            return
        try:
            messages = self.service.regenerate(chat_id)
        except AppError as exc:
            self.show_toast(exc.message)
            return
        self.chat_view.remove_items_after_last_user()
        self._dispatch(chat_id, messages)

    def retry(self) -> None:
        """Re-run the health check, then send the last user message if Ollama is ready."""
        chat_id = self._current_chat_id
        if self.is_busy() or chat_id is None:
            return
        if self.demo_mode:
            self.regenerate()
            return
        self.chat_view.remove_items_after_last_user()
        self._wait_for_health(chat_id, force_check=True)

    def _dispatch(self, chat_id: str, messages: list[dict]) -> None:
        if self.demo_mode:
            self._start_fake(chat_id)
        elif self._health.state is ConnectionState.CONNECTED:
            self._start_ollama(chat_id, messages)
        elif self._health.state is ConnectionState.CHECKING:
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

    def _begin_stream(self, chat_id: str, worker, status: str) -> None:
        self._active_message = self._add_assistant_widget(status)
        self._active_chat_id = chat_id
        self._got_first_token = False
        worker.token.connect(self._on_token)
        worker.finished.connect(self._on_finished)
        worker.cancelled.connect(self._on_cancelled)
        worker.error.connect(self._on_error)
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

    def stop_generation(self) -> None:
        if self._pending_chat_id is not None and self._handle is None:
            self._pending_chat_id = None
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

    def _on_token(self, token: str) -> None:
        if self._active_message is None:
            return
        if not self._got_first_token:
            self._got_first_token = True
            if not self.demo_mode:
                self._active_message.set_status(STATUS_GENERATING)
        self._active_message.append_token(token)

    def _on_finished(self, result: object) -> None:
        if self._handle is None:
            return
        data = result if isinstance(result, dict) else {}
        text = str(data.get("text", ""))
        files = list(data.get("files", []))
        status = demo.DEMO_STATUS if self.demo_mode else finished_status(self.config, data.get("stats"))
        message = self._active_message
        if message is not None:
            message.set_text(text)
            for path in files:
                message.add_file_card(path)
            message.finish(status=status)
        if self._active_chat_id:
            self.service.record_reply(self._active_chat_id, text, status, files)
        self._end_stream()
        self.streamFinished.emit()

    def _on_cancelled(self) -> None:
        if self._handle is None:
            return
        message = self._active_message
        if message is not None:
            message.finish(status=STATUS_STOPPED)
            if self._active_chat_id:
                self.service.record_reply(self._active_chat_id, message.text(), STATUS_STOPPED)
        self._end_stream()

    def _on_error(self, error: object) -> None:
        if self._handle is None:
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
        card = self.chat_view.add_error(err.message)
        card.retryRequested.connect(self.retry)
        self._end_stream()

    def _end_stream(self) -> None:
        self._handle = None
        self._active_message = None
        self._active_chat_id = None
        self.composer.set_busy(False)

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
