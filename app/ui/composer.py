"""Bottom composer: disclaimer, pill input with attach, Project mode and Send/Stop."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.ui import theme
from app.ui.icons import icon_size, load_icon

DISCLAIMER = "Local model output can contain mistakes. Review code before running."
PLACEHOLDER = "Ask a coding question…"


class ComposerInput(QPlainTextEdit):
    """Multiline input: Enter submits, Shift+Enter inserts a newline, grows to 8 lines."""

    submitted = Signal()
    heightChanged = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("composerInput")
        self.setPlaceholderText(PLACEHOLDER)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setTabChangesFocus(True)
        self.document().setDocumentMargin(2)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.textChanged.connect(self._update_height)
        self._update_height()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self.insertPlainText("\n")
            else:
                self.submitted.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def line_count(self) -> int:
        # QPlainTextDocumentLayout reports the document height in lines (wrapped lines included)
        return max(1, int(self.document().documentLayout().documentSize().height()))

    def _update_height(self) -> None:
        lines = min(self.line_count(), theme.COMPOSER_MAX_LINES)
        margins = self.contentsMargins()
        height = (
            lines * self.fontMetrics().lineSpacing()
            + int(self.document().documentMargin() * 2)
            + margins.top() + margins.bottom() + 4
        )
        if height != self.height():
            self.setFixedHeight(height)
            self.heightChanged.emit(height)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._update_height()


class Composer(QWidget):
    sendRequested = Signal(str, bool)  # text, project mode
    stopRequested = Signal()
    attachmentsChanged = Signal(list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._busy = False
        self._attachments: list[str] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)

        self.disclaimer = QLabel(DISCLAIMER)
        self.disclaimer.setObjectName("disclaimer")
        self.disclaimer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.attachment_label = QLabel()
        self.attachment_label.setObjectName("attachmentLabel")
        self.attachment_label.hide()

        self.pill = QFrame()
        self.pill.setObjectName("composerPill")
        self.pill.setMinimumHeight(theme.COMPOSER_MIN_HEIGHT)
        row = QHBoxLayout(self.pill)
        row.setContentsMargins(10, 8, 10, 8)
        row.setSpacing(8)

        self.attach_button = QToolButton()
        self.attach_button.setObjectName("iconButton")
        self.attach_button.setIcon(load_icon("plus", theme.TEXT_PRIMARY, 22))
        self.attach_button.setIconSize(icon_size(22))
        self.attach_button.setFixedSize(QSize(40, 40))
        self.attach_button.setToolTip("Attach files from disk")
        self.attach_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.attach_button.clicked.connect(self.choose_attachments)

        self.input = ComposerInput()
        self.input.submitted.connect(self.submit)

        self.project_chip = QPushButton(" Project mode")
        self.project_chip.setObjectName("projectChip")
        self.project_chip.setCheckable(True)
        self.project_chip.setIcon(load_icon("project-mode", theme.TEXT_SECONDARY, 18))
        self.project_chip.setIconSize(icon_size(18))
        self.project_chip.setCursor(Qt.CursorShape.PointingHandCursor)
        self.project_chip.setToolTip("When on, the request goes to the project generator")
        self.project_chip.toggled.connect(self._on_project_toggled)

        self.send_button = QToolButton()
        self.send_button.setObjectName("sendButton")
        self.send_button.setFixedSize(QSize(theme.SEND_BUTTON_SIZE, theme.SEND_BUTTON_SIZE))
        self.send_button.setIconSize(icon_size(20))
        self.send_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_button.clicked.connect(self._on_send_clicked)

        center = Qt.AlignmentFlag.AlignVCenter
        row.addWidget(self.attach_button, 0, center)
        row.addWidget(self.input, 1, center)
        row.addWidget(self.project_chip, 0, center)
        row.addWidget(self.send_button, 0, center)

        outer.addWidget(self.attachment_label)
        outer.addWidget(self.disclaimer)
        outer.addWidget(self.pill)
        self._refresh_send_button()

    # --- state -------------------------------------------------------------
    def is_busy(self) -> bool:
        return self._busy

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        self._refresh_send_button()

    def project_mode(self) -> bool:
        return self.project_chip.isChecked()

    def attachments(self) -> list[str]:
        return list(self._attachments)

    def set_attachments(self, paths: list[str]) -> None:
        self._attachments = list(paths)
        if paths:
            names = ", ".join(Path(p).name for p in paths[:3])
            more = f" +{len(paths) - 3}" if len(paths) > 3 else ""
            self.attachment_label.setText(f"Attached: {names}{more}")
        self.attachment_label.setVisible(bool(paths))
        self.attachmentsChanged.emit(list(paths))

    def choose_attachments(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Attach files")
        if paths:
            self.set_attachments(paths)

    # --- actions -------------------------------------------------------------
    def submit(self) -> bool:
        """Send the current text. Returns True if something was sent."""
        if self._busy:
            return False
        text = self.input.toPlainText().strip()
        if not text:
            return False
        self.input.clear()
        self.sendRequested.emit(text, self.project_mode())
        self.set_attachments([])
        return True

    def _on_send_clicked(self) -> None:
        if self._busy:
            self.stopRequested.emit()
        else:
            self.submit()

    def _on_project_toggled(self, checked: bool) -> None:
        color = theme.CHIP_ON_TEXT if checked else theme.TEXT_SECONDARY
        self.project_chip.setIcon(load_icon("project-mode", color, 18))

    def _refresh_send_button(self) -> None:
        if self._busy:
            self.send_button.setIcon(load_icon("stop-square", theme.WHITE, 20))
            self.send_button.setToolTip("Stop generating")
        else:
            self.send_button.setIcon(load_icon("send-arrow", theme.WHITE, 20))
            self.send_button.setToolTip("Send (Enter)")
