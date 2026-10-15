"""Read-only code viewer with a line-number gutter and Pygments highlighting."""

from __future__ import annotations

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QPlainTextEdit, QWidget
from pygments.lexers import get_lexer_for_filename
from pygments.styles import get_style_by_name
from pygments.token import Token
from pygments.util import ClassNotFound

from app.ui import theme

# Dark values; painting reads theme.code_colors() so the gutter follows the active theme.
GUTTER_BG = theme.BG_CODE_BLOCK
GUTTER_TEXT = "#5A5A5A"


class _LineNumberArea(QWidget):
    def __init__(self, editor: CodeView) -> None:
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(self._editor.line_number_width(), 0)

    def paintEvent(self, event) -> None:  # noqa: N802
        self._editor.paint_line_numbers(event)


def _utf16_len(text: str) -> int:
    """Length in UTF-16 code units, which is how QTextDocument counts positions."""
    return len(text.encode("utf-16-le")) // 2


class CodeView(QPlainTextEdit):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("codeView")
        self.setReadOnly(True)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        font = QFont(theme.code_font_family())
        font.setPixelSize(theme.FONT_CODE)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)
        self.document().setDocumentMargin(10)
        self._filename = ""
        self._gutter = _LineNumberArea(self)
        self.blockCountChanged.connect(self._update_margins)
        self.updateRequest.connect(self._on_update_request)
        self._update_margins()

    # --- content -------------------------------------------------------------
    @property
    def filename(self) -> str:
        return self._filename

    def set_code(self, text: str, filename: str = "") -> None:
        text = text.replace("\r\n", "\n")
        self._filename = filename
        self.setPlainText(text)
        self._highlight(text, filename)
        self.moveCursor(QTextCursor.MoveOperation.Start)

    def _highlight(self, text: str, filename: str) -> None:
        try:
            lexer = get_lexer_for_filename(filename or "x.txt", stripnl=False, ensurenl=False)
        except ClassNotFound:
            return
        try:
            style = get_style_by_name(theme.CODE_STYLE)
        except ClassNotFound:  # pragma: no cover
            style = get_style_by_name("monokai")
        cursor = QTextCursor(self.document())
        cursor.beginEditBlock()
        pos = 0
        formats: dict[object, QTextCharFormat | None] = {}
        for token_type, value in lexer.get_tokens(text):
            length = _utf16_len(value)
            if token_type not in formats:
                formats[token_type] = self._format_for(style, token_type)
            fmt = formats[token_type]
            if fmt is not None and length:
                cursor.setPosition(pos)
                cursor.setPosition(pos + length, QTextCursor.MoveMode.KeepAnchor)
                cursor.setCharFormat(fmt)
            pos += length
        cursor.endEditBlock()

    @staticmethod
    def _format_for(style, token_type) -> QTextCharFormat | None:
        if token_type in Token.Text.Whitespace:
            return None
        info = style.style_for_token(token_type)
        if not (info["color"] or info["bold"] or info["italic"]):
            return None
        fmt = QTextCharFormat()
        if info["color"]:
            fmt.setForeground(QColor(f"#{info['color']}"))
        if info["bold"]:
            fmt.setFontWeight(QFont.Weight.Bold)
        if info["italic"]:
            fmt.setFontItalic(True)
        return fmt

    # --- gutter --------------------------------------------------------------
    def line_number_width(self) -> int:
        digits = max(2, len(str(max(1, self.blockCount()))))
        return 20 + self.fontMetrics().horizontalAdvance("9") * digits

    def _update_margins(self, _count: int = 0) -> None:
        self.setViewportMargins(self.line_number_width(), 0, 0, 0)

    def _on_update_request(self, rect: QRect, dy: int) -> None:
        if dy:
            self._gutter.scroll(0, dy)
        else:
            self._gutter.update(0, rect.y(), self._gutter.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_margins()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        cr = self.contentsRect()
        self._gutter.setGeometry(QRect(cr.left(), cr.top(), self.line_number_width(), cr.height()))

    def paint_line_numbers(self, event) -> None:
        colors = theme.code_colors()
        painter = QPainter(self._gutter)
        painter.fillRect(event.rect(), QColor(colors["gutter_bg"]))
        painter.setPen(QColor(colors["gutter_text"]))
        painter.setFont(self.font())
        block = self.firstVisibleBlock()
        number = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())
        width = self._gutter.width() - 10
        line_height = self.fontMetrics().height()
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                painter.drawText(0, top, width, line_height, Qt.AlignmentFlag.AlignRight, str(number + 1))
            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            number += 1
        painter.end()
