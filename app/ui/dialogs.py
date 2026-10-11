"""Dialogs. CommandApprovalDialog is built in Phase 3 and wired to tool_runner in Phase 7."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget


class CommandApprovalDialog(QDialog):
    """Modal dark dialog showing a command and its working directory. Approve or Reject."""

    def __init__(self, command: str, working_dir: str, reason: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Approve command")
        self.setModal(True)
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(10)

        title = QLabel("Run this command?")
        title.setObjectName("dialogTitle")
        layout.addWidget(title)
        if reason:
            why = QLabel(reason)
            why.setObjectName("dialogLabel")
            why.setWordWrap(True)
            layout.addWidget(why)

        layout.addWidget(self._label("Command"))
        self.command_label = QLabel(command)
        self.command_label.setObjectName("commandText")
        self.command_label.setWordWrap(True)
        self.command_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.command_label)

        layout.addWidget(self._label("Working directory"))
        self.dir_label = QLabel(working_dir)
        self.dir_label.setObjectName("commandText")
        self.dir_label.setWordWrap(True)
        self.dir_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.dir_label)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.reject_button = QPushButton("Reject")
        self.reject_button.setObjectName("rejectButton")
        self.approve_button = QPushButton("Approve")
        self.approve_button.setObjectName("approveButton")
        self.reject_button.setDefault(True)  # the safe choice is the default
        self.reject_button.clicked.connect(self.reject)
        self.approve_button.clicked.connect(self.accept)
        buttons.addWidget(self.reject_button)
        buttons.addWidget(self.approve_button)
        layout.addSpacing(8)
        layout.addLayout(buttons)

    @staticmethod
    def _label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("dialogLabel")
        return label
