"""Widgets that make up the conversation: bubbles, assistant text, file cards, actions."""

from __future__ import annotations

import math
from pathlib import PurePosixPath

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSizePolicy,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.ui import theme
from app.ui.icons import icon_size, load_icon
from app.ui.markdown_render import COPY_SCHEME, render_markdown

RENDER_INTERVAL_MS = 50  # batch streamed tokens; re-render at most ~20 times a second

FILE_TYPES = {
    ".html": "HTML", ".htm": "HTML", ".css": "CSS", ".js": "JavaScript", ".ts": "TypeScript",
    ".py": "Python", ".java": "Java", ".md": "Markdown", ".json": "JSON", ".txt": "Text",
    ".sql": "SQL", ".ps1": "PowerShell", ".sh": "Shell", ".yml": "YAML", ".yaml": "YAML",
    ".toml": "TOML", ".xml": "XML", ".c": "C", ".cpp": "C++", ".cs": "C#", ".go": "Go", ".rs": "Rust",
}


def file_type_label(path: str) -> str:
    suffix = PurePosixPath(path).suffix.lower()
    return FILE_TYPES.get(suffix, suffix.lstrip(".").upper() or "File")


class UserBubble(QWidget):
    """Right-aligned rounded pill with the user's text."""

    MAX_WIDTH_RATIO = 0.7

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addStretch(1)
        self.label = QLabel(text)
        self.label.setObjectName("userBubble")
        self.label.setTextFormat(Qt.TextFormat.PlainText)
        self.label.setWordWrap(True)
        self.label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.label.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        layout.addWidget(self.label)

    def text(self) -> str:
        return self.label.text()

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        self.label.setMaximumWidth(max(120, int(self.width() * self.MAX_WIDTH_RATIO)))
        super().resizeEvent(event)


class MarkdownBrowser(QTextBrowser):
    """Read-only rich text that grows to fit its content (no inner scrollbar)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("assistantText")
        self.setOpenLinks(False)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.document().setDocumentMargin(0)
        self.document().setDefaultStyleSheet(theme.message_document_css())
        self.anchorClicked.connect(self._on_anchor)
        self._code_blocks: list[str] = []
        self.setFixedHeight(24)

    @property
    def code_blocks(self) -> list[str]:
        return list(self._code_blocks)

    def set_markdown(self, text: str) -> None:
        rendered = render_markdown(text)
        self._code_blocks = rendered.code_blocks
        self.setHtml(rendered.html)
        self._update_height()

    def copy_code_block(self, index: int) -> None:
        if 0 <= index < len(self._code_blocks):
            QGuiApplication.clipboard().setText(self._code_blocks[index])

    def _on_anchor(self, url: QUrl) -> None:
        if url.scheme() == COPY_SCHEME:
            try:
                self.copy_code_block(int(url.path()))
            except ValueError:
                pass
        elif url.scheme() in ("http", "https", "mailto"):
            QDesktopServices.openUrl(url)  # only on an explicit user click

    def _update_height(self) -> None:
        width = self.viewport().width() or self.width()
        self.document().setTextWidth(width)
        height = math.ceil(self.document().size().height()) + 2
        if height != self.height():
            self.setFixedHeight(max(height, 8))

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._update_height()

    def wheelEvent(self, event) -> None:  # noqa: N802
        event.ignore()  # let the chat scroll area handle scrolling


class FileCard(QFrame):
    """A generated or edited file. Clicking it emits ``fileOpened(path)``."""

    fileOpened = Signal(str)

    def __init__(self, path: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.path = path
        self.setObjectName("fileCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(76)
        self.setToolTip(f"Open {path} in the preview panel")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 12, 20, 12)
        layout.setSpacing(16)
        icon_name = "globe" if file_type_label(path) == "HTML" else "file"
        icon = QLabel()
        icon.setPixmap(load_icon(icon_name, theme.TEXT_PRIMARY, 22).pixmap(22, 22))
        icon.setStyleSheet("background: transparent;")
        layout.addWidget(icon)
        text_box = QVBoxLayout()
        text_box.setSpacing(2)
        name = QLabel(PurePosixPath(path).name)
        name.setObjectName("fileName")
        kind = QLabel(file_type_label(path))
        kind.setObjectName("fileType")
        text_box.addWidget(name)
        text_box.addWidget(kind)
        layout.addLayout(text_box)
        layout.addStretch(1)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.fileOpened.emit(self.path)
        super().mouseReleaseEvent(event)


def _action_button(icon: str, tooltip: str, parent: QWidget) -> QToolButton:
    button = QToolButton(parent)
    button.setObjectName("actionButton")
    button.setIcon(load_icon(icon, theme.TEXT_SECONDARY, theme.ACTION_ICON_SIZE, hover_color=theme.TEXT_PRIMARY))
    button.setIconSize(icon_size(theme.ACTION_ICON_SIZE))
    button.setToolTip(tooltip)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setAutoRaise(True)
    return button


class ActionRow(QWidget):
    """Copy, Export, Regenerate, Thumbs-down and More under an assistant message."""

    copyRequested = Signal()
    exportRequested = Signal()
    regenerateRequested = Signal()
    thumbsDownToggled = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        self.copy_button = _action_button("copy", "Copy", self)
        self.export_button = _action_button("export", "Export", self)
        self.regenerate_button = _action_button("regenerate", "Regenerate", self)
        self.thumbs_button = _action_button("thumbs-down", "Bad response (saved locally)", self)
        self.thumbs_button.setCheckable(True)
        self.more_button = _action_button("more", "More", self)
        self.more_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        more_menu = QMenu(self.more_button)
        more_menu.addAction("Copy as Markdown", self.copyRequested.emit)
        self.more_button.setMenu(more_menu)

        self.copy_button.clicked.connect(self.copyRequested.emit)
        self.export_button.clicked.connect(self.exportRequested.emit)
        self.regenerate_button.clicked.connect(self.regenerateRequested.emit)
        self.thumbs_button.toggled.connect(self._on_thumbs)
        for button in (self.copy_button, self.export_button, self.regenerate_button,
                       self.thumbs_button, self.more_button):
            layout.addWidget(button)
        layout.addStretch(1)

    def _on_thumbs(self, checked: bool) -> None:
        color = theme.ERROR if checked else theme.TEXT_SECONDARY
        self.thumbs_button.setIcon(load_icon("thumbs-down", color, theme.ACTION_ICON_SIZE, hover_color=theme.TEXT_PRIMARY))
        self.thumbsDownToggled.emit(checked)


class AssistantMessage(QWidget):
    """Plain left-aligned assistant answer with status line, file cards and actions."""

    fileOpened = Signal(str)
    exportRequested = Signal()
    regenerateRequested = Signal()

    FILE_CARD_RATIO = 0.75

    def __init__(self, status: str | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._text = ""
        self._finished = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.status_label = QLabel()
        self.status_label.setObjectName("statusLine")
        layout.addWidget(self.status_label)
        self.set_status(status)

        self.browser = MarkdownBrowser(self)
        layout.addWidget(self.browser)

        self.code_chip = QLabel()
        self.code_chip.setObjectName("codeChip")
        self.code_chip.setFixedSize(26, 26)
        self.code_chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.code_chip.setPixmap(load_icon("code", theme.TEXT_PRIMARY, 14).pixmap(14, 14))
        self.code_chip.setToolTip("Generated files")
        self.code_chip.hide()
        layout.addWidget(self.code_chip)

        self.files_layout = QVBoxLayout()
        self.files_layout.setSpacing(8)
        layout.addLayout(self.files_layout)
        self.file_cards: list[FileCard] = []

        self.actions = ActionRow(self)
        self.actions.hide()
        self.actions.copyRequested.connect(self.copy_text)
        self.actions.exportRequested.connect(self.exportRequested.emit)
        self.actions.regenerateRequested.connect(self.regenerateRequested.emit)
        layout.addWidget(self.actions)

        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.setInterval(RENDER_INTERVAL_MS)
        self._render_timer.timeout.connect(self._render)

    # --- content ---------------------------------------------------------
    def text(self) -> str:
        return self._text

    def is_finished(self) -> bool:
        return self._finished

    def set_status(self, status: str | None) -> None:
        self.status_label.setText(status or "")
        self.status_label.setVisible(bool(status))

    def append_token(self, token: str) -> None:
        self._text += token
        if not self._render_timer.isActive():
            self._render_timer.start()

    def set_text(self, text: str) -> None:
        self._text = text
        self._render()

    def finish(self, status: str | None = None) -> None:
        self._render_timer.stop()
        self._render()
        self._finished = True
        if status is not None:
            self.set_status(status)
        self.actions.show()

    def add_file_card(self, path: str) -> FileCard:
        card = FileCard(path, self)
        card.fileOpened.connect(self.fileOpened.emit)
        card.setMaximumWidth(max(260, int(self.width() * self.FILE_CARD_RATIO)))
        self.files_layout.addWidget(card)
        self.file_cards.append(card)
        self.code_chip.show()
        return card

    def copy_text(self) -> None:
        QGuiApplication.clipboard().setText(self._text)

    def _render(self) -> None:
        self.browser.set_markdown(self._text)

    def resizeEvent(self, event) -> None:  # noqa: N802
        for card in self.file_cards:
            card.setMaximumWidth(max(260, int(self.width() * self.FILE_CARD_RATIO)))
        super().resizeEvent(event)


class ErrorCard(QFrame):
    """Inline red-bordered error with a Retry button."""

    retryRequested = Signal()

    def __init__(self, message: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("errorCard")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 12, 12)
        layout.setSpacing(12)
        self.label = QLabel(message)
        self.label.setObjectName("errorText")
        self.label.setWordWrap(True)
        layout.addWidget(self.label, 1)
        self.retry_button = QPushButton("Retry")
        self.retry_button.setObjectName("retryButton")
        self.retry_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.retry_button.clicked.connect(self.retryRequested.emit)
        layout.addWidget(self.retry_button, 0, Qt.AlignmentFlag.AlignVCenter)
