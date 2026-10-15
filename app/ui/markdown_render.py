"""Markdown to Qt rich-text HTML, with Pygments-highlighted code blocks.

Fenced code blocks are split out before Markdown runs, so an unfinished block at
the end of a streaming answer still renders as code. Each code block gets a
header row with the language and a ``copy:N`` link handled by the browser widget.
"""

from __future__ import annotations

import html
from dataclasses import dataclass, field

import markdown
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import TextLexer, get_lexer_by_name
from pygments.util import ClassNotFound

from app.ui import theme

COPY_SCHEME = "copy"


@dataclass
class CodeBlock:
    language: str
    code: str
    closed: bool = True


@dataclass
class RenderedMarkdown:
    html: str
    code_blocks: list[str] = field(default_factory=list)


def split_fenced(text: str) -> list[str | CodeBlock]:
    """Split text into markdown strings and CodeBlock items (``` fences only)."""
    parts: list[str | CodeBlock] = []
    prose: list[str] = []
    code: list[str] = []
    language = ""
    in_code = False
    for line in text.replace("\r\n", "\n").split("\n"):
        stripped = line.strip()
        if not in_code and stripped.startswith("```"):
            if prose:
                parts.append("\n".join(prose))
                prose = []
            info = stripped.lstrip("`").strip()  # ``` or longer fences (````text)
            language = info.split()[0] if info else ""
            code = []
            in_code = True
        elif in_code and stripped.startswith("```") and not stripped.strip("`"):
            parts.append(CodeBlock(language, "\n".join(code), closed=True))
            in_code = False
        elif in_code:
            code.append(line)
        else:
            prose.append(line)
    if in_code:
        parts.append(CodeBlock(language, "\n".join(code), closed=False))
    elif prose:
        parts.append("\n".join(prose))
    return parts


def _formatter() -> HtmlFormatter:
    try:
        return HtmlFormatter(nowrap=True, noclasses=True, style=theme.CODE_STYLE)
    except ClassNotFound:  # pragma: no cover - older Pygments
        return HtmlFormatter(nowrap=True, noclasses=True, style="monokai")


def highlight_code(code: str, language: str) -> str:
    try:
        lexer = get_lexer_by_name(language) if language else TextLexer()
    except ClassNotFound:
        lexer = TextLexer()
    return highlight(code, lexer, _formatter()).rstrip("\n")


def code_block_html(block: CodeBlock, index: int, code_font: str) -> str:
    label = html.escape(block.language or "code")
    body = highlight_code(block.code, block.language) or "&nbsp;"
    colors = theme.code_colors()
    return (
        f'<table width="100%" cellspacing="0" cellpadding="10" '
        f'style="margin-top:4px; margin-bottom:16px; background-color:{colors["background"]};">'
        f'<tr>'
        f'<td style="background-color:{colors["header"]}; color:{colors["header_text"]}; font-size:13px;">{label}</td>'
        f'<td align="right" style="background-color:{colors["header"]}; font-size:13px;">'
        f'<a href="{COPY_SCHEME}:{index}" style="color:{colors["header_text"]}; text-decoration:none;">Copy</a></td>'
        f'</tr>'
        f'<tr><td colspan="2" style="background-color:{colors["background"]};">'
        f'<pre style="font-family:\'{code_font}\'; font-size:{theme.FONT_CODE}px; '
        f'white-space:pre-wrap; margin:0px;">{body}</pre></td></tr>'
        f'</table>'
    )


def render_markdown(text: str, code_font: str | None = None) -> RenderedMarkdown:
    code_font = code_font or theme.code_font_family()
    out: list[str] = []
    blocks: list[str] = []
    for part in split_fenced(text):
        if isinstance(part, CodeBlock):
            out.append(code_block_html(part, len(blocks), code_font))
            blocks.append(part.code)
        elif part.strip():
            out.append(markdown.markdown(part, extensions=["sane_lists", "tables"]))
    return RenderedMarkdown("\n".join(out), blocks)
