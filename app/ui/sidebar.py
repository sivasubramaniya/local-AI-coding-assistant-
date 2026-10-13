"""Left sidebar: header, primary actions, Projects, Recents and the model status footer."""

from __future__ import annotations

from PySide6.QtCore import QModelIndex, QPoint, QRect, QSize, QSortFilterProxyModel, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QMenu,
    QPushButton,
    QSizePolicy,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.backend.status import ConnectionState
from app.ui import theme
from app.ui.icons import icon_size, load_icon

ID_ROLE = Qt.ItemDataRole.UserRole + 1
NAV_ICON_GAP = "  "
SETTINGS_BUTTON_HEIGHT = 44


class SidebarItemDelegate(QStyledItemDelegate):
    """Rounded hover/selected background, optional icon, elided text."""

    ROW_HEIGHT = theme.NAV_ROW_HEIGHT

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = option.rect.adjusted(0, 1, 0, -1)
        state = option.state
        background = None
        if state & QStyle.StateFlag.State_Selected:
            background = theme.BG_ITEM_SELECTED
        elif state & QStyle.StateFlag.State_MouseOver:
            background = theme.BG_ITEM_HOVER
        if background:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(background))
            painter.drawRoundedRect(rect, 10, 10)

        x = rect.left() + 12
        icon = index.data(Qt.ItemDataRole.DecorationRole)
        if icon is not None:
            size = 20
            icon.paint(painter, QRect(x, rect.center().y() - size // 2 + 1, size, size))
            x += size + 12

        font = QFont(option.font)
        font.setPixelSize(theme.FONT_SIDEBAR_ITEM)
        painter.setFont(font)
        painter.setPen(QColor(theme.TEXT_PRIMARY))
        text_rect = QRect(x, rect.top(), rect.right() - x - 10, rect.height())
        text = QFontMetrics(font).elidedText(
            str(index.data(Qt.ItemDataRole.DisplayRole) or ""), Qt.TextElideMode.ElideRight, text_rect.width()
        )
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)
        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:  # noqa: N802
        return QSize(option.rect.width(), self.ROW_HEIGHT)


def _nav_button(icon: str, text: str) -> QToolButton:
    button = QToolButton()
    button.setObjectName("navButton")
    button.setText(NAV_ICON_GAP + text)  # QSS cannot set the icon-to-text gap
    button.setIcon(load_icon(icon, theme.TEXT_PRIMARY, 20))
    button.setIconSize(icon_size(20))
    button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
    button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    button.setFixedHeight(theme.NAV_ROW_HEIGHT)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setToolTip(text)
    return button


def _icon_button(icon: str, tooltip: str, size: int = 20) -> QToolButton:
    button = QToolButton()
    button.setObjectName("iconButton")
    button.setIcon(load_icon(icon, theme.TEXT_SECONDARY, size, hover_color=theme.TEXT_PRIMARY))
    button.setIconSize(icon_size(size))
    button.setFixedSize(QSize(36, 36))
    button.setToolTip(tooltip)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setAutoRaise(True)
    return button


class ModelStatusCard(QFrame):
    """Circular badge, model name, and an 'Ollama · <state>' line with a colored dot."""

    def __init__(self, model_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("modelCard")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)

        self.badge = QLabel()
        self.badge.setObjectName("modelBadge")
        self.badge.setFixedSize(32, 32)
        self.badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.badge.setPixmap(load_icon("code", theme.TEXT_PRIMARY, 16).pixmap(16, 16))
        layout.addWidget(self.badge)

        self.text_box = QWidget()
        text_layout = QVBoxLayout(self.text_box)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(1)
        display_name = model_name.removesuffix(":latest")
        self.name_label = QLabel(display_name)
        self.name_label.setObjectName("modelName")
        self.name_label.setToolTip(model_name)
        status_row = QHBoxLayout()
        status_row.setSpacing(6)
        self.dot = QLabel()
        self.dot.setFixedSize(8, 8)
        self.status_label = QLabel()
        self.status_label.setObjectName("modelStatus")
        status_row.addWidget(self.dot)
        status_row.addWidget(self.status_label)
        status_row.addStretch(1)
        text_layout.addWidget(self.name_label)
        text_layout.addLayout(status_row)
        layout.addWidget(self.text_box, 1)

        self.state = ConnectionState.CHECKING
        self.set_state(ConnectionState.CHECKING)

    def set_state(self, state: ConnectionState, detail: str | None = None) -> None:
        self.state = state
        color = {
            ConnectionState.CONNECTED: theme.SUCCESS,
            ConnectionState.DISCONNECTED: theme.ERROR,
            ConnectionState.MODEL_MISSING: theme.WARNING,
            ConnectionState.CHECKING: theme.TEXT_SECONDARY,
        }[state]
        self.dot.setStyleSheet(f"background: {color}; border-radius: 4px;")
        self.status_label.setText(f"Ollama · {state.value}")
        self.setToolTip(detail or f"Ollama · {state.value}")

    def status_text(self) -> str:
        return self.status_label.text()

    def set_model_name(self, model_name: str) -> None:
        """The selected model (Quality 14B or Fast 7B) shown on the card."""
        self.name_label.setText(model_name.removesuffix(":latest"))
        self.name_label.setToolTip(model_name)

    def model_text(self) -> str:
        return self.name_label.text()

    def set_compact(self, compact: bool) -> None:
        self.text_box.setVisible(not compact)


class Sidebar(QFrame):
    newChatRequested = Signal()
    chatSelected = Signal(str)
    renameRequested = Signal(str)
    deleteRequested = Signal(str)
    projectSelected = Signal(str)
    generatedProjectsRequested = Signal()
    settingsRequested = Signal()
    collapsedChanged = Signal(bool)

    def __init__(self, app_name: str, model_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(theme.SIDEBAR_WIDTH)
        self._collapsed = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 14, 10, 12)
        layout.setSpacing(2)

        # Header
        header = QHBoxLayout()
        header.setContentsMargins(10, 0, 0, 10)
        header.setSpacing(4)
        self.title_label = QLabel(app_name)
        self.title_label.setObjectName("appTitle")
        self.header_search_button = _icon_button("search", "Search chats")
        self.collapse_button = _icon_button("sidebar", "Collapse sidebar")
        self.collapse_button.clicked.connect(self.toggle_collapsed)
        header.addWidget(self.title_label, 1)
        header.addWidget(self.header_search_button)
        header.addWidget(self.collapse_button)
        layout.addLayout(header)

        # Primary actions
        self.new_chat_button = _nav_button("new-chat", "New chat")
        self.search_button = _nav_button("search", "Search chats")
        self.projects_button = _nav_button("folder", "Generated Projects")
        self.new_chat_button.clicked.connect(self.newChatRequested.emit)
        self.search_button.clicked.connect(self.toggle_search)
        self.header_search_button.clicked.connect(self.toggle_search)
        self.projects_button.clicked.connect(self.generatedProjectsRequested.emit)
        self.nav_buttons = [self.new_chat_button, self.search_button, self.projects_button]
        for button in self.nav_buttons:
            layout.addWidget(button)

        self.search_field = QLineEdit()
        self.search_field.setObjectName("searchField")
        self.search_field.setPlaceholderText("Search chats")
        self.search_field.setClearButtonEnabled(True)
        self.search_field.hide()
        layout.addWidget(self.search_field)

        # Projects
        self.projects_label = QLabel("Projects")
        self.projects_label.setObjectName("sectionLabel")
        layout.addWidget(self.projects_label)
        self.project_model = QStandardItemModel(self)
        self.project_list = self._make_list("projectList", self.project_model)
        self.project_list.clicked.connect(
            lambda index: self.projectSelected.emit(str(index.data(ID_ROLE)))
        )
        layout.addWidget(self.project_list)

        # Recents
        self.recents_label = QLabel("Recents")
        self.recents_label.setObjectName("sectionLabel")
        layout.addWidget(self.recents_label)
        self.chat_model = QStandardItemModel(self)
        self.chat_proxy = QSortFilterProxyModel(self)
        self.chat_proxy.setSourceModel(self.chat_model)
        self.chat_proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.search_field.textChanged.connect(self.chat_proxy.setFilterFixedString)
        self.chat_list = self._make_list("chatList", self.chat_proxy)
        self.chat_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.chat_list.clicked.connect(self._on_chat_clicked)
        self.chat_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.chat_list.customContextMenuRequested.connect(self._show_chat_menu)
        layout.addWidget(self.chat_list, 1)

        self.spacer = QWidget()
        self.spacer.hide()
        layout.addWidget(self.spacer, 1)

        # Footer
        self.status_card = ModelStatusCard(model_name)
        layout.addWidget(self.status_card)
        self.settings_button = QPushButton(NAV_ICON_GAP + "Settings")
        self.settings_button.setObjectName("settingsButton")
        self.settings_button.setFixedHeight(SETTINGS_BUTTON_HEIGHT)
        self.settings_button.setIcon(load_icon("settings", theme.TEXT_PRIMARY, 18))
        self.settings_button.setIconSize(icon_size(18))
        self.settings_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.settings_button.clicked.connect(self.settingsRequested.emit)
        layout.addSpacing(6)
        layout.addWidget(self.settings_button)

    def _make_list(self, name: str, model) -> QListView:
        view = QListView()
        view.setObjectName(name)
        view.setModel(model)
        view.setItemDelegate(SidebarItemDelegate(view))
        view.setMouseTracking(True)
        view.setEditTriggers(QListView.EditTrigger.NoEditTriggers)
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        view.setUniformItemSizes(True)
        view.setCursor(Qt.CursorShape.PointingHandCursor)
        return view

    # --- data ----------------------------------------------------------------
    def set_projects(self, projects: list[str] | list[tuple[str, str]]) -> None:
        """``projects`` is a list of names, or of (id, name); projectSelected emits the id."""
        self.project_model.clear()
        names = []
        for entry in projects:
            project_id, name = entry if isinstance(entry, tuple) else (entry, entry)
            names.append(name)
            item = QStandardItem(name)
            item.setData(project_id, ID_ROLE)
            item.setToolTip(name)
            item.setData(load_icon("folder", theme.TEXT_PRIMARY, 20), Qt.ItemDataRole.DecorationRole)
            self.project_model.appendRow(item)
        self.project_list.setFixedHeight(len(names) * theme.NAV_ROW_HEIGHT + 2)
        self.projects_label.setVisible(bool(names) and not self._collapsed)
        self.project_list.setVisible(bool(names) and not self._collapsed)

    def set_chats(self, chats: list[tuple[str, str]], current_id: str | None = None) -> None:
        """``chats`` is a list of (id, title), most recent first."""
        self.chat_model.clear()
        for chat_id, title in chats:
            item = QStandardItem(title)
            item.setData(chat_id, ID_ROLE)
            item.setToolTip(title)
            self.chat_model.appendRow(item)
        self.set_current_chat(current_id)

    def chat_titles(self) -> list[str]:
        return [self.chat_model.item(row).text() for row in range(self.chat_model.rowCount())]

    def chat_ids(self) -> list[str]:
        return [self.chat_model.item(row).data(ID_ROLE) for row in range(self.chat_model.rowCount())]

    def current_chat_id(self) -> str | None:
        index = self.chat_list.currentIndex()
        return index.data(ID_ROLE) if index.isValid() else None

    def set_current_chat(self, chat_id: str | None) -> None:
        selection = self.chat_list.selectionModel()
        selection.clearSelection()
        if chat_id is None:
            self.chat_list.setCurrentIndex(QModelIndex())
            return
        for row in range(self.chat_proxy.rowCount()):
            index = self.chat_proxy.index(row, 0)
            if index.data(ID_ROLE) == chat_id:
                self.chat_list.setCurrentIndex(index)
                return

    # --- interaction ---------------------------------------------------------
    def _on_chat_clicked(self, index: QModelIndex) -> None:
        chat_id = index.data(ID_ROLE)
        if chat_id:
            self.chatSelected.emit(chat_id)

    def _show_chat_menu(self, pos: QPoint) -> None:
        index = self.chat_list.indexAt(pos)
        if not index.isValid():
            return
        chat_id = index.data(ID_ROLE)
        menu = QMenu(self)
        menu.addAction("Rename", lambda: self.renameRequested.emit(chat_id))
        menu.addAction("Delete", lambda: self.deleteRequested.emit(chat_id))
        menu.exec(self.chat_list.viewport().mapToGlobal(pos))

    def toggle_search(self) -> None:
        if self._collapsed:
            self.set_collapsed(False)
        visible = not self.search_field.isVisible()
        self.search_field.setVisible(visible)
        if visible:
            self.search_field.setFocus()
        else:
            self.search_field.clear()

    # --- collapse ------------------------------------------------------------
    def is_collapsed(self) -> bool:
        return self._collapsed

    def toggle_collapsed(self) -> None:
        self.set_collapsed(not self._collapsed)

    def set_collapsed(self, collapsed: bool) -> None:
        if collapsed == self._collapsed:
            return
        self._collapsed = collapsed
        self.setFixedWidth(theme.SIDEBAR_COLLAPSED_WIDTH if collapsed else theme.SIDEBAR_WIDTH)
        for widget in (self.title_label, self.header_search_button, self.recents_label, self.chat_list):
            widget.setVisible(not collapsed)
        has_projects = self.project_model.rowCount() > 0
        self.projects_label.setVisible(not collapsed and has_projects)
        self.project_list.setVisible(not collapsed and has_projects)
        if collapsed:
            self.search_field.hide()
        self.spacer.setVisible(collapsed)
        style = Qt.ToolButtonStyle.ToolButtonIconOnly if collapsed else Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        for button in self.nav_buttons:
            button.setToolButtonStyle(style)
        self.status_card.set_compact(collapsed)
        self.settings_button.setText("" if collapsed else NAV_ICON_GAP + "Settings")
        self.settings_button.setToolTip("Settings")
        self.collapse_button.setToolTip("Expand sidebar" if collapsed else "Collapse sidebar")
        self.collapsedChanged.emit(collapsed)
