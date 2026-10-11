"""Main window: Sidebar | QSplitter(chat panel, preview panel).

The window wires widgets to the in-memory store and the demo worker. It holds no
business rules; Phase 4/5 swap the fake worker and store for real services.
"""

from __future__ import annotations

import logging

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

from app.backend.memory_store import ChatMessage, InMemoryChatStore, title_from_prompt
from app.backend.status import ConnectionState, stub_connection_state
from app.config import AppConfig
from app.errors import AppError
from app.ui import demo, theme
from app.ui.chat_view import ChatView
from app.ui.composer import Composer
from app.ui.icons import icon_size, load_icon
from app.ui.message_widgets import AssistantMessage
from app.ui.preview_panel import PreviewPanel
from app.ui.sidebar import Sidebar
from app.ui.workers import FakeStreamWorker, WorkerHandle, start_worker

logger = logging.getLogger(__name__)

EXPORT_PENDING = "Export is coming in Phase 9."
TOAST_MS = 2600
PREVIEW_SHARE = 0.45


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


class MainWindow(QMainWindow):
    streamFinished = Signal()

    def __init__(
        self,
        config: AppConfig,
        store: InMemoryChatStore | None = None,
        token_delay_s: float = 0.04,
        use_webengine: bool | None = None,
        seed_demo: bool = True,
    ) -> None:
        super().__init__()
        self.config = config
        self.store = store or InMemoryChatStore()
        self.token_delay_s = token_delay_s
        self._handle: WorkerHandle | None = None
        self._active_message: AssistantMessage | None = None
        self._active_chat_id: str | None = None
        self._last_prompt: tuple[str, bool] | None = None
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
        self.preview.set_project(demo.DEMO_PROJECT_NAME, demo.DEMO_FILES)
        self.sidebar.set_projects([demo.DEMO_PROJECT_NAME])
        self.set_connection_state(stub_connection_state())

        if seed_demo:
            current = demo.seed_demo_store(self.store)
            self.select_chat(current)
        else:
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

    # --- generation ------------------------------------------------------------
    def is_busy(self) -> bool:
        return self._handle is not None

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
        chat = self.store.get(chat_id)
        if not chat.messages and chat.title == "New chat":
            self.store.rename(chat_id, title_from_prompt(text))
        self.store.add_message(chat_id, ChatMessage("user", text))
        self._refresh_sidebar()
        self.chat_view.add_user_message(text)
        self._last_prompt = (text, project_mode)
        self._start_stream(chat_id)
        return True

    def regenerate(self) -> None:
        if self._last_prompt and not self.is_busy():
            self._start_stream(self._current_chat_id)

    def _start_stream(self, chat_id: str | None) -> None:
        status = demo.DEMO_STATUS
        self._active_message = self._add_assistant_widget(status)
        self._active_chat_id = chat_id
        worker = FakeStreamWorker(demo.DEMO_ANSWER, demo.DEMO_ANSWER_FILES, delay_s=self.token_delay_s)
        worker.token.connect(self._on_token)
        worker.finished.connect(self._on_finished)
        worker.cancelled.connect(self._on_cancelled)
        worker.error.connect(self._on_error)
        self._handle = start_worker(worker, self)
        self.composer.set_busy(True)
        logger.info("Demo stream started (chat %s)", chat_id)

    def stop_generation(self) -> None:
        if self._handle is None:
            return
        handle = self._handle
        handle.cancel()
        handle.wait(3000)
        # the queued 'cancelled' signal may not be delivered yet; finish the UI state now
        self._on_cancelled()

    def _on_token(self, token: str) -> None:
        if self._active_message is not None:
            self._active_message.append_token(token)

    def _on_finished(self, result: object) -> None:
        if self._handle is None:
            return
        message = self._active_message
        files: list[str] = list(result.get("files", [])) if isinstance(result, dict) else []
        text = result.get("text", "") if isinstance(result, dict) else ""
        if message is not None:
            message.set_text(text)
            for path in files:
                message.add_file_card(path)
            message.finish()
        if self._active_chat_id and self.store.exists(self._active_chat_id):
            self.store.add_message(
                self._active_chat_id,
                ChatMessage("assistant", text, files=files, status=demo.DEMO_STATUS),
            )
        self._end_stream()
        self.streamFinished.emit()

    def _on_cancelled(self) -> None:
        if self._handle is None:
            return
        message = self._active_message
        if message is not None:
            message.finish(status="Stopped")
            if self._active_chat_id and self.store.exists(self._active_chat_id) and message.text():
                self.store.add_message(
                    self._active_chat_id, ChatMessage("assistant", message.text(), status="Stopped")
                )
        self._end_stream()

    def _on_error(self, error: str) -> None:
        if self._handle is None:
            return
        if self._active_message is not None:
            self._active_message.finish(status="Failed")
        card = self.chat_view.add_error(error)
        card.retryRequested.connect(self.regenerate)
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

    # --- status and feedback ---------------------------------------------------
    def set_connection_state(self, state: ConnectionState) -> None:
        detail = None
        if state is ConnectionState.DISCONNECTED:
            detail = "Not connected. The Ollama connection check arrives in Phase 4."
        self.sidebar.status_card.set_state(state, detail)

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
        if self._handle is not None:
            self._handle.cancel()
            self._handle.wait(3000)
            self._handle = None
        super().closeEvent(event)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(1600, 900)
