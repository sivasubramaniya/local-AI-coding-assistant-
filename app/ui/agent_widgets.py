"""Chat cards for the coding agent: the project Plan card and the file Changes card.

Both only show data and emit signals. Writing files is decided by the main window
after the user clicks Apply.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.ui import theme

DIFF_MAX_HEIGHT = 320


def _button(text: str, name: str) -> QPushButton:
    button = QPushButton(text)
    button.setObjectName(name)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button


def _label(text: str, name: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName(name)
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return label


class _DecisionCard(QFrame):
    """A card with a body and Apply / Cancel buttons that can be answered once."""

    applyRequested = Signal()
    cancelRequested = Signal()

    def __init__(self, title: str, apply_text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("agentCard")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(18, 14, 18, 14)
        self._layout.setSpacing(8)
        self.title_label = _label(title, "agentTitle")
        self._layout.addWidget(self.title_label)
        self.body = QVBoxLayout()
        self.body.setSpacing(4)
        self._layout.addLayout(self.body)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.state_label = _label("", "agentText")
        self.state_label.hide()
        row.addWidget(self.state_label, 1)
        row.addStretch(0)
        self.cancel_button = _button("Cancel", "secondaryButton")
        self.apply_button = _button(apply_text, "primaryButton")
        row.addWidget(self.cancel_button)
        row.addWidget(self.apply_button)
        self._layout.addLayout(row)
        self.apply_button.clicked.connect(self._on_apply)
        self.cancel_button.clicked.connect(self._on_cancel)

    def _close_with(self, text: str) -> None:
        self.apply_button.setEnabled(False)
        self.cancel_button.setEnabled(False)
        self.apply_button.hide()
        self.cancel_button.hide()
        self.state_label.setText(text)
        self.state_label.show()

    def is_open(self) -> bool:
        return self.apply_button.isEnabled()

    def state_text(self) -> str:
        return self.state_label.text()

    def set_state(self, text: str) -> None:
        self._close_with(text)

    def _on_apply(self) -> None:
        if self.is_open():
            self._close_with("Applying…")
            self.applyRequested.emit()

    def _on_cancel(self) -> None:
        if self.is_open():
            self._close_with("Cancelled")
            self.cancelRequested.emit()


class PlanCard(_DecisionCard):
    """Shows the planned files before anything is written. Apply starts generation."""

    def __init__(self, plan, parent: QWidget | None = None) -> None:
        super().__init__(f"Plan: {plan.project_name}", "Generate files", parent)
        self.plan = plan
        self.body.addWidget(_label(f"{plan.description}  ·  {plan.language}", "agentText"))
        self.file_labels: list[QLabel] = []
        for planned in plan.files:
            label = _label(f"•  {planned.path}  —  {planned.purpose}", "agentText")
            self.file_labels.append(label)
            self.body.addWidget(label)
        self.body.addWidget(_label("Nothing is written until you click Generate files.", "agentText"))


class ChangesCard(_DecisionCard):
    """Shows proposed edits as a unified diff. Apply writes them (with backups)."""

    def __init__(self, project_name: str, pending: list, problems: dict[str, str],
                 parent: QWidget | None = None) -> None:
        count = len(pending)
        super().__init__(f"Suggested changes to {project_name}: {count} file{'s' if count != 1 else ''}",
                         "Apply changes", parent)
        self.pending = pending
        for change in pending:
            kind = "new file" if change.is_new else "modified"
            self.body.addWidget(_label(f"•  {change.path}  ({kind})", "agentText"))
        for path, reason in problems.items():
            self.body.addWidget(_label(f"•  {path}: not usable — {reason}", "agentText"))
        self.diff_view = QPlainTextEdit()
        self.diff_view.setObjectName("diffView")
        self.diff_view.setReadOnly(True)
        self.diff_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        font = QFont(theme.code_font_family())
        font.setPixelSize(theme.FONT_CODE - 1)
        self.diff_view.setFont(font)
        self.diff_view.setPlainText("".join(change.diff_text() for change in pending))
        self.diff_view.setMaximumHeight(DIFF_MAX_HEIGHT)
        self.body.addWidget(self.diff_view)
        self.body.addWidget(_label("Existing files are backed up as <file>.bak-<time> before writing.",
                                   "agentText"))
        if not pending:
            self.apply_button.setEnabled(False)


class ExportCard(QFrame):
    """Success card for an export: where it went, what was left out, and an Open folder button."""

    openRequested = Signal(str)

    def __init__(self, result, as_zip: bool, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("agentCard")
        self.result = result
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(6)
        kind = "ZIP archive created and verified" if as_zip else "Project exported and checked"
        self.title_label = _label(f"✓ {kind}: {len(result.files)} files", "agentTitle")
        layout.addWidget(self.title_label)
        self.path_label = _label(str(result.destination), "agentText")
        layout.addWidget(self.path_label)
        notes = []
        if result.skipped:
            notes.append(f"Left out {len(result.skipped)} file(s) (caches, build output, backups or secrets).")
        if result.readme_added:
            notes.append("Build, run and test instructions were added to README.md.")
        for note in notes:
            layout.addWidget(_label(note, "agentText"))
        row = QHBoxLayout()
        row.addStretch(1)
        self.open_button = _button("Open folder", "secondaryButton")
        folder = result.destination.parent if as_zip else result.destination
        self.open_button.clicked.connect(lambda: self.openRequested.emit(str(folder)))
        row.addWidget(self.open_button)
        layout.addLayout(row)
