"""Design tokens (colors, fonts, sizes) and the generated Qt stylesheet.

Values come from UI_DESIGN.md. Every color used by the UI is defined here once.
"""

from __future__ import annotations

from collections.abc import Iterable

# --- Color tokens (UI_DESIGN.md section 2) ---------------------------------
BG_APP = "#000000"
BG_SIDEBAR = "#000000"
BORDER_SUBTLE = "#1F1F1F"
BG_ITEM_HOVER = "#1A1A1A"
BG_ITEM_SELECTED = "#262626"
BG_CARD = "#171717"
BORDER_CARD = "#333333"
BG_INLINE_CODE = "#2A2A2A"
BG_CODE_BLOCK = "#0D0D0D"
TEXT_PRIMARY = "#ECECEC"
TEXT_SECONDARY = "#9B9B9B"
ACCENT_USER_BUBBLE = "#1E4A8C"
ACCENT_PRIMARY = "#2F6FE0"
SUCCESS = "#3FB950"
ERROR = "#F85149"
WARNING = "#D29922"
PREVIEW_BG_START = "#1E2A5A"
PREVIEW_BG_END = "#4B3A9A"

# Derived shades (not in the spec table, kept here so nothing is hard-coded elsewhere)
BG_BUTTON_ROUND = "#1F1F1F"
BG_BUTTON_ROUND_HOVER = "#2E2E2E"
BG_CODE_HEADER = "#171717"
BG_ERROR_CARD = "#1C0F0F"
ACCENT_PRIMARY_HOVER = "#4A82E8"
ACCENT_DISABLED = "#22324F"
CHIP_ON_BG = "#16243D"
CHIP_ON_TEXT = "#8FB6FF"
WHITE = "#FFFFFF"

COLORS: dict[str, str] = {
    "bg_app": BG_APP,
    "bg_sidebar": BG_SIDEBAR,
    "border_subtle": BORDER_SUBTLE,
    "bg_item_hover": BG_ITEM_HOVER,
    "bg_item_selected": BG_ITEM_SELECTED,
    "bg_card": BG_CARD,
    "border_card": BORDER_CARD,
    "bg_inline_code": BG_INLINE_CODE,
    "bg_code_block": BG_CODE_BLOCK,
    "text_primary": TEXT_PRIMARY,
    "text_secondary": TEXT_SECONDARY,
    "accent_user_bubble": ACCENT_USER_BUBBLE,
    "accent_primary": ACCENT_PRIMARY,
    "success": SUCCESS,
    "error": ERROR,
    "warning": WARNING,
    "preview_bg_start": PREVIEW_BG_START,
    "preview_bg_end": PREVIEW_BG_END,
    "bg_button_round": BG_BUTTON_ROUND,
    "bg_button_round_hover": BG_BUTTON_ROUND_HOVER,
    "bg_code_header": BG_CODE_HEADER,
    "bg_error_card": BG_ERROR_CARD,
    "accent_primary_hover": ACCENT_PRIMARY_HOVER,
    "accent_disabled": ACCENT_DISABLED,
    "chip_on_bg": CHIP_ON_BG,
    "chip_on_text": CHIP_ON_TEXT,
    "white": WHITE,
}

# --- Typography (section 3) -------------------------------------------------
UI_FONT_CANDIDATES = ("Segoe UI", "Arial")
CODE_FONT_CANDIDATES = ("Cascadia Code", "Cascadia Mono", "Consolas", "Courier New")
FONT_APP_TITLE = 20
FONT_SIDEBAR_ITEM = 15
FONT_SECTION_LABEL = 14
FONT_MESSAGE = 16
FONT_CODE = 14
FONT_DISCLAIMER = 12
CODE_STYLE = "github-dark"  # Pygments style for code blocks and the code viewer

# --- Sizes (sections 1, 4-6) ------------------------------------------------
SIDEBAR_WIDTH = 300
SIDEBAR_COLLAPSED_WIDTH = 64
CONTENT_MAX_WIDTH = 760
TOP_BAR_HEIGHT = 56
NAV_ROW_HEIGHT = 40
COMPOSER_RADIUS = 28
COMPOSER_MIN_HEIGHT = 64
COMPOSER_MAX_LINES = 8
SEND_BUTTON_SIZE = 40
ROUND_BUTTON_SIZE = 36
ACTION_ICON_SIZE = 18
WINDOW_MIN_WIDTH = 1100
WINDOW_MIN_HEIGHT = 700
PREVIEW_MIN_WIDTH = 360
CHAT_MIN_WIDTH = 440

_current_fonts: dict[str, str] = {"ui": UI_FONT_CANDIDATES[0], "code": CODE_FONT_CANDIDATES[0]}


def pick_font(candidates: Iterable[str], available: Iterable[str]) -> str:
    """First candidate that is installed, else the last candidate."""
    installed = {name.lower() for name in available}
    candidates = tuple(candidates)
    for name in candidates:
        if name.lower() in installed:
            return name
    return candidates[-1]


def resolve_fonts() -> tuple[str, str]:
    """Pick UI and code fonts from the installed families (needs a QGuiApplication)."""
    from PySide6.QtGui import QFontDatabase

    families = QFontDatabase.families()
    ui = pick_font(UI_FONT_CANDIDATES, families)
    code = pick_font(CODE_FONT_CANDIDATES, families)
    _current_fonts.update(ui=ui, code=code)
    return ui, code


def ui_font_family() -> str:
    return _current_fonts["ui"]


def code_font_family() -> str:
    return _current_fonts["code"]


def message_document_css(code_font: str | None = None) -> str:
    """Default stylesheet for rendered assistant markdown (QTextDocument CSS subset)."""
    code_font = code_font or code_font_family()
    return f"""
        body {{ color: {TEXT_PRIMARY}; font-size: {FONT_MESSAGE}px; }}
        p {{ margin-top: 0px; margin-bottom: 14px; line-height: 160%; }}
        ul, ol {{ margin-top: 0px; margin-bottom: 14px; }}
        li {{ margin-bottom: 2px; line-height: 135%; }}
        h1, h2, h3, h4, h5, h6 {{ font-size: {FONT_MESSAGE}px; font-weight: 700;
            margin-top: 10px; margin-bottom: 12px; }}
        a {{ color: {TEXT_PRIMARY}; text-decoration: underline; }}
        code {{ background-color: {BG_INLINE_CODE}; font-family: '{code_font}';
            font-size: {FONT_CODE}px; }}
        strong, b {{ font-weight: 700; }}
    """


def build_stylesheet(ui_font: str | None = None, code_font: str | None = None) -> str:
    """One QSS string for the whole application, generated from the tokens."""
    ui_font = ui_font or ui_font_family()
    code_font = code_font or code_font_family()
    c = COLORS
    return f"""
QWidget {{
    color: {c['text_primary']};
    font-family: "{ui_font}";
    font-size: {FONT_SIDEBAR_ITEM}px;
}}
QMainWindow, QWidget#chatPanel, QWidget#chatInner, QScrollArea#chatView {{
    background: {c['bg_app']};
}}
QScrollArea {{ border: none; background: transparent; }}

/* ---------- Sidebar ---------- */
QFrame#sidebar {{
    background: {c['bg_sidebar']};
    border-right: 1px solid {c['border_subtle']};
}}
QLabel#appTitle {{ font-size: {FONT_APP_TITLE}px; font-weight: 600; }}
QLabel#sectionLabel {{
    color: {c['text_secondary']};
    font-size: {FONT_SECTION_LABEL}px;
    padding: 18px 12px 6px 12px;
}}
QToolButton#navButton {{
    background: transparent;
    border: none;
    border-radius: 8px;
    padding: 8px 10px;
    text-align: left;
    font-size: {FONT_SIDEBAR_ITEM}px;
}}
QToolButton#navButton:hover {{ background: {c['bg_item_hover']}; }}
QToolButton#iconButton {{
    background: transparent;
    border: none;
    border-radius: 8px;
    padding: 6px;
}}
QToolButton#iconButton:hover, QToolButton#iconButton:checked {{ background: {c['bg_item_hover']}; }}
QListView#chatList, QListView#projectList {{
    background: transparent;
    border: none;
    outline: 0;
}}
QLineEdit#searchField {{
    background: {c['bg_card']};
    border: 1px solid {c['border_card']};
    border-radius: 10px;
    padding: 7px 10px;
    margin: 4px 0px;
}}
QLineEdit#searchField:focus {{ border-color: {c['accent_primary']}; }}
QFrame#modelCard {{ background: transparent; border-radius: 10px; }}
QFrame#modelCard:hover {{ background: {c['bg_item_hover']}; }}
QLabel#modelBadge {{
    background: {c['bg_item_selected']};
    border-radius: 16px;
}}
QLabel#modelName {{ font-weight: 600; font-size: {FONT_SIDEBAR_ITEM}px; }}
QLabel#modelStatus {{ color: {c['text_secondary']}; font-size: {FONT_SECTION_LABEL}px; }}
QPushButton#settingsButton {{
    background: transparent;
    border: 1px solid {c['border_card']};
    border-radius: 21px;
    padding: 0px 14px;
    font-weight: 600;
    font-size: {FONT_SECTION_LABEL}px;
}}
QPushButton#settingsButton:hover {{ background: {c['bg_item_hover']}; }}

/* ---------- Chat top bar ---------- */
QFrame#topBar {{ background: {c['bg_app']}; }}
QToolButton#topBarButton {{
    background: transparent;
    border: none;
    border-radius: 10px;
    padding: 7px 12px;
    font-size: {FONT_SIDEBAR_ITEM}px;
}}
QToolButton#topBarButton:hover, QToolButton#topBarButton:checked {{ background: {c['bg_item_hover']}; }}
QToolButton::menu-indicator {{ image: none; width: 0px; }}

/* ---------- Messages ---------- */
QLabel#emptyTitle {{ font-size: 28px; font-weight: 600; color: {c['text_primary']}; }}
QLabel#userBubble {{
    background: {c['accent_user_bubble']};
    color: {c['white']};
    border-radius: 22px;
    padding: 12px 20px;
    font-size: {FONT_MESSAGE}px;
}}
QLabel#statusLine {{ color: {c['text_secondary']}; font-size: {FONT_MESSAGE}px; }}
QTextBrowser#assistantText {{
    background: transparent;
    border: none;
    font-size: {FONT_MESSAGE}px;
    selection-background-color: {c['accent_user_bubble']};
}}
QLabel#codeChip {{
    background: {c['bg_card']};
    border-radius: 13px;
}}
QFrame#fileCard {{
    background: {c['bg_card']};
    border: 1px solid {c['border_card']};
    border-radius: 14px;
}}
QFrame#fileCard:hover {{ border-color: #4A4A4A; }}
QLabel#fileName {{ font-weight: 600; font-size: {FONT_MESSAGE}px; background: transparent; }}
QLabel#fileType {{ color: {c['text_secondary']}; font-size: {FONT_SECTION_LABEL}px; background: transparent; }}
QToolButton#actionButton {{
    background: transparent;
    border: none;
    border-radius: 8px;
    padding: 5px;
}}
QToolButton#actionButton:hover {{ background: {c['bg_item_hover']}; }}
QFrame#errorCard {{
    background: {c['bg_error_card']};
    border: 1px solid {c['error']};
    border-radius: 12px;
}}
QLabel#errorText {{ color: {c['text_primary']}; background: transparent; }}
QPushButton#retryButton {{
    background: transparent;
    color: {c['text_primary']};
    border: 1px solid {c['error']};
    border-radius: 14px;
    padding: 6px 16px;
}}
QPushButton#retryButton:hover {{ background: #2A1414; }}
QFrame#agentCard {{
    background: {c['bg_card']};
    border: 1px solid {c['border_card']};
    border-radius: 14px;
}}
QLabel#agentTitle {{ font-weight: 600; font-size: {FONT_MESSAGE}px; background: transparent; }}
QLabel#agentText {{ color: {c['text_secondary']}; background: transparent; }}
QPushButton#primaryButton {{
    background: {c['accent_primary']};
    color: {c['white']};
    border: none;
    border-radius: 14px;
    padding: 6px 18px;
    font-weight: 600;
}}
QPushButton#primaryButton:hover {{ background: {c['accent_primary_hover']}; }}
QPushButton#primaryButton:disabled {{ background: {c['accent_disabled']}; color: {c['text_secondary']}; }}
QPushButton#secondaryButton {{
    background: transparent;
    color: {c['text_primary']};
    border: 1px solid {c['border_card']};
    border-radius: 14px;
    padding: 6px 16px;
}}
QPushButton#secondaryButton:hover {{ background: {c['bg_item_hover']}; }}
QPushButton#secondaryButton:disabled {{ color: #4A4A4A; }}
QPlainTextEdit#diffView {{
    background: {c['bg_code_block']};
    border: 1px solid {c['border_subtle']};
    border-radius: 8px;
}}
QLabel#toast {{
    background: {c['bg_button_round']};
    border: 1px solid {c['border_card']};
    border-radius: 12px;
    padding: 8px 16px;
    font-size: {FONT_SECTION_LABEL}px;
}}

/* ---------- Composer ---------- */
QLabel#disclaimer {{ color: {c['text_secondary']}; font-size: {FONT_DISCLAIMER}px; }}
QFrame#composerPill {{
    background: {c['bg_card']};
    border: 1px solid {c['border_card']};
    border-radius: {COMPOSER_RADIUS}px;
}}
QPlainTextEdit#composerInput {{
    background: transparent;
    border: none;
    font-size: {FONT_MESSAGE + 1}px;
    selection-background-color: {c['accent_user_bubble']};
}}
QPushButton#projectChip {{
    background: transparent;
    color: {c['text_secondary']};
    border: 1px solid transparent;
    border-radius: 17px;
    padding: 7px 12px;
    font-size: {FONT_SIDEBAR_ITEM}px;
}}
QPushButton#projectChip:hover {{ background: {c['bg_item_hover']}; color: {c['text_primary']}; }}
QPushButton#projectChip:checked {{
    background: {c['chip_on_bg']};
    color: {c['chip_on_text']};
    border-color: {c['accent_primary']};
}}
QToolButton#sendButton {{
    background: {c['accent_primary']};
    border: none;
    border-radius: {SEND_BUTTON_SIZE // 2}px;
}}
QToolButton#sendButton:hover {{ background: {c['accent_primary_hover']}; }}
QToolButton#sendButton:disabled {{ background: {c['accent_disabled']}; }}
QLabel#attachmentLabel {{ color: {c['text_secondary']}; font-size: {FONT_DISCLAIMER + 1}px; }}

/* ---------- Preview panel ---------- */
QFrame#previewPanel {{ background: {c['bg_app']}; border-left: 1px solid {c['border_subtle']}; }}
QFrame#previewHeader {{ background: {c['bg_app']}; }}
QToolButton#fileDropdown {{
    background: {c['bg_button_round']};
    border: none;
    border-radius: 18px;
    padding: 7px 14px;
    font-size: {FONT_SIDEBAR_ITEM + 1}px;
}}
QToolButton#fileDropdown:hover {{ background: {c['bg_button_round_hover']}; }}
QToolButton#roundButton {{
    background: {c['bg_button_round']};
    border: none;
    border-radius: {ROUND_BUTTON_SIZE // 2}px;
}}
QToolButton#roundButton:hover, QToolButton#roundButton:checked {{ background: {c['bg_button_round_hover']}; }}
QToolButton#treeToggle {{
    background: transparent;
    border: none;
    color: {c['text_secondary']};
    padding: 4px 6px;
    font-size: {FONT_SECTION_LABEL}px;
}}
QToolButton#treeToggle:hover {{ color: {c['text_primary']}; }}
QPushButton#tabButton {{
    background: transparent;
    border: none;
    border-radius: 14px;
    padding: 6px 14px;
    color: {c['text_secondary']};
    font-size: {FONT_SECTION_LABEL}px;
}}
QPushButton#tabButton:hover {{ color: {c['text_primary']}; }}
QPushButton#tabButton:checked {{ background: {c['bg_item_selected']}; color: {c['text_primary']}; }}
QPushButton#tabButton:disabled {{ color: #4A4A4A; }}
QTreeWidget#fileTree {{
    background: {c['bg_app']};
    border: none;
    border-bottom: 1px solid {c['border_subtle']};
    outline: 0;
}}
QTreeWidget#fileTree::item {{ padding: 4px; border-radius: 6px; }}
QTreeWidget#fileTree::item:selected {{ background: {c['bg_item_selected']}; color: {c['text_primary']}; }}
QTreeWidget#fileTree::item:hover {{ background: {c['bg_item_hover']}; }}
QLabel#emptyPreview {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 {c['preview_bg_start']}, stop:1 {c['preview_bg_end']});
    color: {c['text_primary']};
    font-size: {FONT_MESSAGE + 2}px;
}}
QPlainTextEdit#codeView {{
    background: {c['bg_code_block']};
    border: none;
    font-family: "{code_font}";
    font-size: {FONT_CODE}px;
    selection-background-color: {c['accent_user_bubble']};
}}
QTextBrowser#markdownPreview, QTextBrowser#htmlFallback {{
    background: {c['bg_app']};
    border: none;
    padding: 16px;
}}
QFrame#previewNotice {{
    background: {c['bg_card']};
    border-bottom: 1px solid {c['border_subtle']};
}}
QLabel#previewNoticeText {{ color: {c['text_secondary']}; font-size: {FONT_DISCLAIMER + 1}px; background: transparent; }}
QPushButton#linkButton {{
    background: {c['bg_button_round']};
    border: none;
    border-radius: 12px;
    padding: 5px 12px;
    font-size: {FONT_DISCLAIMER + 1}px;
}}
QPushButton#linkButton:hover {{ background: {c['bg_button_round_hover']}; }}

/* ---------- Common ---------- */
QSplitter::handle {{ background: {c['border_subtle']}; }}
QSplitter::handle:hover {{ background: {c['accent_primary']}; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #3A3A3A; border-radius: 3px; min-height: 32px; }}
QScrollBar::handle:vertical:hover {{ background: #555555; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: #3A3A3A; border-radius: 3px; min-width: 32px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0px; height: 0px; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QMenu {{
    background: {c['bg_button_round']};
    border: 1px solid {c['border_card']};
    border-radius: 10px;
    padding: 6px;
}}
QMenu::item {{ padding: 7px 18px; border-radius: 6px; }}
QMenu::item:selected {{ background: {c['bg_button_round_hover']}; }}
QToolTip {{
    background: {c['bg_button_round']};
    color: {c['text_primary']};
    border: 1px solid {c['border_card']};
    border-radius: 6px;
    padding: 4px 8px;
}}
QDialog {{ background: {c['bg_card']}; }}
QPushButton {{
    background: {c['bg_button_round']};
    border: 1px solid {c['border_card']};
    border-radius: 8px;
    padding: 6px 16px;
}}
QPushButton:hover {{ background: {c['bg_button_round_hover']}; }}
QPushButton#approveButton {{ background: {c['accent_primary']}; border-color: {c['accent_primary']}; color: {c['white']}; }}
QPushButton#rejectButton {{ border-color: {c['error']}; }}
QLabel#dialogTitle {{ font-size: 18px; font-weight: 600; }}
QLabel#dialogLabel {{ color: {c['text_secondary']}; font-size: {FONT_SECTION_LABEL}px; }}
QLabel#commandText {{
    background: {c['bg_code_block']};
    border: 1px solid {c['border_card']};
    border-radius: 8px;
    padding: 10px;
    font-family: "{code_font}";
    font-size: {FONT_CODE}px;
}}
QLineEdit {{
    background: {c['bg_card']};
    border: 1px solid {c['border_card']};
    border-radius: 8px;
    padding: 6px 8px;
}}
"""


def apply_theme(app) -> tuple[str, str]:
    """Apply Fusion style, a dark palette, fonts and the stylesheet to a QApplication."""
    from PySide6.QtGui import QColor, QFont, QPalette

    ui_font, code_font = resolve_fonts()
    app.setStyle("Fusion")

    palette = QPalette()
    role = QPalette.ColorRole
    for r, color in (
        (role.Window, BG_APP),
        (role.WindowText, TEXT_PRIMARY),
        (role.Base, BG_CARD),
        (role.AlternateBase, BG_ITEM_HOVER),
        (role.Text, TEXT_PRIMARY),
        (role.Button, BG_BUTTON_ROUND),
        (role.ButtonText, TEXT_PRIMARY),
        (role.Highlight, ACCENT_USER_BUBBLE),
        (role.HighlightedText, WHITE),
        (role.ToolTipBase, BG_BUTTON_ROUND),
        (role.ToolTipText, TEXT_PRIMARY),
        (role.PlaceholderText, TEXT_SECONDARY),
        (role.Link, ACCENT_PRIMARY),
    ):
        palette.setColor(r, QColor(color))
    app.setPalette(palette)

    font = QFont(ui_font)
    font.setPixelSize(FONT_SIDEBAR_ITEM)
    app.setFont(font)
    app.setStyleSheet(build_stylesheet(ui_font, code_font))
    return ui_font, code_font
