"""Right-hand preview panel: file dropdown, file tree, Code | Preview tabs."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path, PurePosixPath

from PySide6.QtCore import QSize, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QStackedWidget,
    QTextBrowser,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.ui import theme
from app.ui.code_view import CodeView
from app.ui.icons import icon_size, load_icon
from app.ui.markdown_render import render_markdown

logger = logging.getLogger(__name__)

PATH_ROLE = Qt.ItemDataRole.UserRole + 1
HTML_SUFFIXES = {".html", ".htm"}
MARKDOWN_SUFFIXES = {".md", ".markdown"}
FALLBACK_NOTICE = "Basic preview: QtWebEngine is not installed, so scripts and modern CSS are not shown."


def webengine_available() -> bool:
    """True if QtWebEngineWidgets can be imported (used only for HTML file previews)."""
    try:
        from PySide6 import QtWebEngineWidgets  # noqa: F401
    except ImportError:
        return False
    return True


def preview_temp_dir() -> Path:
    return Path(tempfile.gettempdir()) / "LocalAIAssistant-preview"


class HtmlPreview(QWidget):
    """Renders HTML with QWebEngineView when available, else a QTextBrowser fallback."""

    def __init__(self, parent: QWidget | None = None, use_webengine: bool | None = None) -> None:
        super().__init__(parent)
        use_webengine = webengine_available() if use_webengine is None else use_webengine
        self._html = ""
        self._filename = "preview.html"
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.notice: QFrame | None = None
        self.open_button: QPushButton | None = None
        if use_webengine:
            from PySide6.QtWebEngineWidgets import QWebEngineView

            from app.ui.offline_web import make_offline_page

            self.view = QWebEngineView(self)
            self.page = make_offline_page(self.view, self)  # remote resources in previewed HTML are blocked
            self.view.setPage(self.page)
            self.is_fallback = False
        else:
            self.notice = QFrame()
            self.notice.setObjectName("previewNotice")
            notice_row = QHBoxLayout(self.notice)
            notice_row.setContentsMargins(14, 8, 10, 8)
            text = QLabel(FALLBACK_NOTICE)
            text.setObjectName("previewNoticeText")
            text.setWordWrap(True)
            self.open_button = QPushButton("Open in default browser")
            self.open_button.setObjectName("linkButton")
            self.open_button.setCursor(Qt.CursorShape.PointingHandCursor)
            self.open_button.clicked.connect(self.open_in_browser)
            notice_row.addWidget(text, 1)
            notice_row.addWidget(self.open_button)
            layout.addWidget(self.notice)
            browser = QTextBrowser(self)
            browser.setObjectName("htmlFallback")
            browser.setOpenLinks(False)
            self.view = browser
            self.is_fallback = True
        layout.addWidget(self.view, 1)

    def set_html(self, html: str, filename: str) -> None:
        self._html = html
        self._filename = PurePosixPath(filename).name or "preview.html"
        self.view.setHtml(html)

    def write_temp_file(self) -> Path:
        folder = preview_temp_dir()
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / self._filename
        path.write_text(self._html, encoding="utf-8")
        return path

    def open_in_browser(self) -> Path:
        """User-initiated only: save the HTML to a temp file and open it in the default browser."""
        path = self.write_temp_file()
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        return path


def _round_button(icon: str, tooltip: str) -> QToolButton:
    button = QToolButton()
    button.setObjectName("roundButton")
    button.setIcon(load_icon(icon, theme.TEXT_PRIMARY, 18))
    button.setIconSize(icon_size(18))
    button.setFixedSize(QSize(theme.ROUND_BUTTON_SIZE, theme.ROUND_BUTTON_SIZE))
    button.setToolTip(tooltip)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button


class PreviewPanel(QFrame):
    closeRequested = Signal()
    expandToggled = Signal(bool)
    exportRequested = Signal(str)
    fileChanged = Signal(str)

    PAGE_EMPTY, PAGE_CODE, PAGE_HTML, PAGE_MARKDOWN = range(4)

    def __init__(self, parent: QWidget | None = None, use_webengine: bool | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("previewPanel")
        self.setMinimumWidth(theme.PREVIEW_MIN_WIDTH)
        self._use_webengine = use_webengine
        self._project_name = ""
        self._files: dict[str, str] = {}
        self._current: str | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QFrame()
        header.setObjectName("previewHeader")
        header.setFixedHeight(theme.TOP_BAR_HEIGHT + 8)
        header_row = QHBoxLayout(header)
        header_row.setContentsMargins(12, 10, 12, 10)
        header_row.setSpacing(8)
        self.file_button = QToolButton()
        self.file_button.setObjectName("fileDropdown")
        self.file_button.setIcon(load_icon("code", theme.TEXT_PRIMARY, 18))
        self.file_button.setIconSize(icon_size(18))
        self.file_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.file_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.file_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.file_button.setToolTip("Switch file")
        self.file_menu = QMenu(self.file_button)
        self.file_button.setMenu(self.file_menu)
        self.export_button = _round_button("download", "Save / Export file")
        self.expand_button = _round_button("expand", "Expand preview")
        self.expand_button.setCheckable(True)
        self.close_button = _round_button("close", "Close preview")
        self.export_button.clicked.connect(lambda: self.exportRequested.emit(self._current or ""))
        self.expand_button.toggled.connect(self.expandToggled.emit)
        self.close_button.clicked.connect(self.closeRequested.emit)
        header_row.addWidget(self.file_button)
        header_row.addStretch(1)
        for button in (self.export_button, self.expand_button, self.close_button):
            header_row.addWidget(button)
        layout.addWidget(header)

        # Tools row: file-tree toggle + Code | Preview tabs
        self.tools = QWidget()
        tools_row = QHBoxLayout(self.tools)
        tools_row.setContentsMargins(12, 0, 12, 8)
        tools_row.setSpacing(4)
        self.tree_toggle = QToolButton()
        self.tree_toggle.setObjectName("treeToggle")
        self.tree_toggle.setCheckable(True)
        self.tree_toggle.setText("▸ Files")
        self.tree_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.tree_toggle.toggled.connect(self.set_tree_visible)
        self.code_tab = QPushButton("Code")
        self.preview_tab = QPushButton("Preview")
        self.tabs = QButtonGroup(self)
        self.tabs.setExclusive(True)
        for tab in (self.code_tab, self.preview_tab):
            tab.setObjectName("tabButton")
            tab.setCheckable(True)
            tab.setCursor(Qt.CursorShape.PointingHandCursor)
            self.tabs.addButton(tab)
        self.code_tab.clicked.connect(lambda: self.show_tab("code"))
        self.preview_tab.clicked.connect(lambda: self.show_tab("preview"))
        tools_row.addWidget(self.tree_toggle)
        tools_row.addStretch(1)
        tools_row.addWidget(self.code_tab)
        tools_row.addWidget(self.preview_tab)
        layout.addWidget(self.tools)

        self.tree = QTreeWidget()
        self.tree.setObjectName("fileTree")
        self.tree.setHeaderHidden(True)
        self.tree.setMaximumHeight(170)
        self.tree.itemClicked.connect(self._on_tree_clicked)
        self.tree.hide()
        layout.addWidget(self.tree)

        # Body
        self.stack = QStackedWidget()
        self.empty_label = QLabel("Select a file to preview")
        self.empty_label.setObjectName("emptyPreview")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.code_view = CodeView()
        self._html_preview: HtmlPreview | None = None
        self.html_container = QWidget()
        QVBoxLayout(self.html_container).setContentsMargins(0, 0, 0, 0)
        self.markdown_view = QTextBrowser()
        self.markdown_view.setObjectName("markdownPreview")
        self.markdown_view.setOpenExternalLinks(False)
        self.markdown_view.document().setDefaultStyleSheet(theme.message_document_css())
        for page in (self.empty_label, self.code_view, self.html_container, self.markdown_view):
            self.stack.addWidget(page)
        layout.addWidget(self.stack, 1)
        self.show_empty()

    # --- project/files -------------------------------------------------------
    @property
    def html_preview(self) -> HtmlPreview:
        if self._html_preview is None:
            self._html_preview = HtmlPreview(self.html_container, self._use_webengine)
            self.html_container.layout().addWidget(self._html_preview)
        return self._html_preview

    def project_name(self) -> str:
        return self._project_name

    def files(self) -> list[str]:
        return list(self._files)

    def current_path(self) -> str | None:
        return self._current

    def set_project(self, name: str, files: dict[str, str]) -> None:
        self._project_name = name
        self._files = dict(files)
        self.file_menu.clear()
        for path in self._files:
            self.file_menu.addAction(path, lambda p=path: self.open_file(p))
        self.tree.clear()
        root = QTreeWidgetItem([name])
        root.setIcon(0, load_icon("folder", theme.TEXT_SECONDARY, 16))
        self.tree.addTopLevelItem(root)
        for path in self._files:
            item = QTreeWidgetItem([path])
            item.setData(0, PATH_ROLE, path)
            item.setIcon(0, load_icon("file", theme.TEXT_SECONDARY, 16))
            root.addChild(item)
        root.setExpanded(True)
        self.tree_toggle.setVisible(len(self._files) > 1)
        if self._current not in self._files:
            self.show_empty()

    def clear_project(self) -> None:
        """No project: empty file list and tree."""
        self._project_name = ""
        self._files = {}
        self.file_menu.clear()
        self.tree.clear()
        self.tree_toggle.hide()
        self.show_empty()

    def open_file(self, path: str) -> bool:
        if path not in self._files:
            logger.warning("Preview requested for unknown file %r", path)
            return False
        self._current = path
        self.file_button.setText(f"{PurePosixPath(path).name}  ▾")
        self.file_button.show()
        self.tools.show()
        suffix = PurePosixPath(path).suffix.lower()
        previewable = suffix in HTML_SUFFIXES | MARKDOWN_SUFFIXES
        self.preview_tab.setEnabled(previewable)
        self.code_view.set_code(self._files[path], path)
        self._select_tree_item(path)
        self.show_tab("preview" if previewable else "code")
        self.fileChanged.emit(path)
        return True

    def show_empty(self) -> None:
        self._current = None
        self.file_button.setText("No file  ▾")
        self.file_button.setVisible(bool(self._files))
        self.tools.hide()
        self.tree.hide()
        self.stack.setCurrentIndex(self.PAGE_EMPTY)

    def show_tab(self, tab: str) -> None:
        if self._current is None:
            return
        suffix = PurePosixPath(self._current).suffix.lower()
        content = self._files[self._current]
        if tab == "preview" and suffix in HTML_SUFFIXES:
            self.html_preview.set_html(content, self._current)
            self.stack.setCurrentIndex(self.PAGE_HTML)
            self.preview_tab.setChecked(True)
        elif tab == "preview" and suffix in MARKDOWN_SUFFIXES:
            self.markdown_view.setHtml(render_markdown(content).html)
            self.stack.setCurrentIndex(self.PAGE_MARKDOWN)
            self.preview_tab.setChecked(True)
        else:
            self.stack.setCurrentIndex(self.PAGE_CODE)
            self.code_tab.setChecked(True)

    def current_tab(self) -> str:
        index = self.stack.currentIndex()
        return {self.PAGE_EMPTY: "empty", self.PAGE_CODE: "code"}.get(index, "preview")

    def refresh_theme(self) -> None:
        """Re-render the Markdown preview with the active theme's colors."""
        self.markdown_view.document().setDefaultStyleSheet(theme.message_document_css())
        if self.stack.currentIndex() == self.PAGE_MARKDOWN:
            self.show_tab("preview")
        self.code_view.viewport().update()

    # --- tree ----------------------------------------------------------------
    def set_tree_visible(self, visible: bool) -> None:
        self.tree.setVisible(visible)
        self.tree_toggle.setText("▾ Files" if visible else "▸ Files")
        if self.tree_toggle.isChecked() != visible:
            self.tree_toggle.setChecked(visible)

    def _on_tree_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        path = item.data(0, PATH_ROLE)
        if path:
            self.open_file(path)

    def _select_tree_item(self, path: str) -> None:
        root = self.tree.topLevelItem(0)
        if root is None:
            return
        for i in range(root.childCount()):
            child = root.child(i)
            if child.data(0, PATH_ROLE) == path:
                self.tree.setCurrentItem(child)
                return
