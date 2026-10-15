"""Dialogs. CommandApprovalDialog (wired to tool_runner in Phase 7) and the storage recovery prompt."""

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


RECOVER_FRESH = "fresh"
RECOVER_MEMORY = "memory"
RECOVER_QUIT = "quit"


def ask_storage_recovery(message: str, offer_fresh: bool, parent: QWidget | None = None) -> str:
    """Ask what to do when the history database cannot be opened.

    Returns RECOVER_FRESH (start a new database; the old file was kept as a backup),
    RECOVER_MEMORY (run without saving history) or RECOVER_QUIT.
    """
    from PySide6.QtWidgets import QMessageBox

    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle("Chat history")
    box.setText(message)
    fresh = box.addButton("Start a fresh database", QMessageBox.ButtonRole.AcceptRole) if offer_fresh else None
    memory = box.addButton("Continue without saving history", QMessageBox.ButtonRole.ActionRole)
    box.addButton("Quit", QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(fresh or memory)
    box.exec()
    clicked = box.clickedButton()
    if fresh is not None and clicked is fresh:
        return RECOVER_FRESH
    if clicked is memory:
        return RECOVER_MEMORY
    return RECOVER_QUIT


TIMEOUT_MIN_S = 10
TIMEOUT_MAX_S = 600
THEME_CHOICES = (("Dark", "dark"), ("Light", "light"), ("System", "system"), ("Glass", "glass"))


class SettingsDialog(QDialog):
    """Export folder, command timeout and a theme placeholder. Values are saved by the caller."""

    def __init__(self, export_dir: str, command_timeout_s: float, parent: QWidget | None = None,
                 model_name: str = "", fast_default: bool = False, fast_model_name: str = "",
                 theme_mode: str = "dark") -> None:
        from PySide6.QtWidgets import QComboBox, QFileDialog, QFormLayout, QLineEdit, QSpinBox

        from app.__version__ import __version__

        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.setMinimumWidth(560)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        title = QLabel("Settings")
        title.setObjectName("dialogTitle")
        layout.addWidget(title)
        form = QFormLayout()
        row = QHBoxLayout()
        self.export_edit = QLineEdit(export_dir)
        browse = QPushButton("Browse…")
        browse.setObjectName("secondaryButton")
        browse.clicked.connect(lambda: self._browse(QFileDialog))
        row.addWidget(self.export_edit, 1)
        row.addWidget(browse)
        form.addRow("Export folder", row)
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(TIMEOUT_MIN_S, TIMEOUT_MAX_S)  # typing outside the range is refused
        self.timeout_spin.setSuffix(" s")
        self.timeout_spin.setSingleStep(10)
        self.timeout_spin.setValue(max(TIMEOUT_MIN_S, min(TIMEOUT_MAX_S, int(command_timeout_s))))
        self.timeout_spin.setToolTip(f"How long an approved command may run ({TIMEOUT_MIN_S}–{TIMEOUT_MAX_S} s).")
        form.addRow("Command timeout", self.timeout_spin)
        self.model_combo = QComboBox()
        self.model_combo.addItems(["Quality (14B) — default", "Fast (7B)"])
        self.model_combo.setCurrentIndex(1 if fast_default else 0)
        self.model_combo.setToolTip(f"Model for new chats. Fast uses {fast_model_name or 'the 7B model'}; "
                                    "each chat keeps its own choice.")
        form.addRow("New chats use", self.model_combo)
        self.theme_combo = QComboBox()
        self.theme_combo.addItems([label for label, _ in THEME_CHOICES])
        modes = [mode for _, mode in THEME_CHOICES]
        self.theme_combo.setCurrentIndex(modes.index(theme_mode) if theme_mode in modes else 0)
        self.theme_combo.setToolTip("System follows the Windows light/dark setting. "
                                     "Glass: translucent panels over a dark gradient.")
        form.addRow("Theme", self.theme_combo)
        layout.addLayout(form)
        about = f"About: Local AI Assistant {__version__}"
        if model_name:
            about += f" · local model {model_name} · runs offline"
        self.about_label = self._label(about)
        self.about_label.setWordWrap(True)
        layout.addSpacing(6)
        layout.addWidget(self.about_label)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.setObjectName("secondaryButton")
        save = QPushButton("Save")
        save.setObjectName("approveButton")
        cancel.clicked.connect(self.reject)
        save.clicked.connect(self.accept)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        layout.addSpacing(8)
        layout.addLayout(buttons)

    def _browse(self, file_dialog) -> None:
        chosen = file_dialog.getExistingDirectory(self, "Export folder", self.export_edit.text())
        if chosen:
            self.export_edit.setText(chosen)

    @staticmethod
    def _label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("dialogLabel")
        return label

    def values(self) -> tuple[str, int]:
        return self.export_edit.text().strip(), self.timeout_spin.value()

    def theme_mode(self) -> str:
        return THEME_CHOICES[self.theme_combo.currentIndex()][1]

    def fast_default(self) -> bool:
        return self.model_combo.currentIndex() == 1
