"""Scrollable, centered message column with stick-to-bottom auto-scroll."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.ui import theme
from app.ui.message_widgets import AssistantMessage, ErrorCard, UserBubble

STICK_THRESHOLD_PX = 24


class ChatView(QScrollArea):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("chatView")
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        inner = QWidget()
        inner.setObjectName("chatInner")
        row = QHBoxLayout(inner)
        row.setContentsMargins(24, 12, 24, 24)
        row.setSpacing(0)
        row.addStretch(1)

        self.column = QWidget()
        self.column.setObjectName("chatColumn")
        self.column.setMaximumWidth(theme.CONTENT_MAX_WIDTH)
        self.column.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.column_layout = QVBoxLayout(self.column)
        self.column_layout.setContentsMargins(0, 0, 0, 0)
        self.column_layout.setSpacing(28)

        self.empty_label = QLabel("What are we coding today?")
        self.empty_label.setObjectName("emptyTitle")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.column_layout.addStretch(1)
        self.column_layout.addWidget(self.empty_label)
        self.column_layout.addStretch(2)

        row.addWidget(self.column, 1000)
        row.addStretch(1)
        self.setWidget(inner)

        self._items: list[QWidget] = []
        self._stick_to_bottom = True
        bar = self.verticalScrollBar()
        bar.rangeChanged.connect(self._on_range_changed)
        bar.valueChanged.connect(self._on_value_changed)

    # --- messages --------------------------------------------------------
    @property
    def items(self) -> list[QWidget]:
        return list(self._items)

    def _add(self, widget: QWidget) -> QWidget:
        if not self._items:
            self.empty_label.hide()
            # drop the centering stretches; messages stack from the top
            while self.column_layout.count():
                self.column_layout.takeAt(0)
            self.column_layout.addStretch(1)
        self.column_layout.insertWidget(self.column_layout.count() - 1, widget)
        self._items.append(widget)
        return widget

    def add_user_message(self, text: str) -> UserBubble:
        self._stick_to_bottom = True
        return self._add(UserBubble(text))  # type: ignore[return-value]

    def add_assistant_message(self, status: str | None = None) -> AssistantMessage:
        return self._add(AssistantMessage(status))  # type: ignore[return-value]

    def add_error(self, message: str) -> ErrorCard:
        return self._add(ErrorCard(message))  # type: ignore[return-value]

    def clear(self) -> None:
        for widget in self._items:
            widget.setParent(None)
            widget.deleteLater()
        self._items.clear()
        while self.column_layout.count():
            self.column_layout.takeAt(0)
        self.column_layout.addStretch(1)
        self.column_layout.addWidget(self.empty_label)
        self.column_layout.addStretch(2)
        self.empty_label.show()
        self._stick_to_bottom = True

    # --- auto-scroll -----------------------------------------------------
    def is_stuck_to_bottom(self) -> bool:
        return self._stick_to_bottom

    def scroll_to_bottom(self) -> None:
        self._stick_to_bottom = True
        bar = self.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _on_value_changed(self, value: int) -> None:
        self._stick_to_bottom = value >= self.verticalScrollBar().maximum() - STICK_THRESHOLD_PX

    def _on_range_changed(self, _minimum: int, maximum: int) -> None:
        if self._stick_to_bottom:
            self.verticalScrollBar().setValue(maximum)
