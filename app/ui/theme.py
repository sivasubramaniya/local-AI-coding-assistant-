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

# --- Themes -----------------------------------------------------------------
THEME_DARK = "dark"
THEME_GLASS = "glass"
THEMES: dict[str, str] = {THEME_DARK: "Dark", THEME_GLASS: "Glass"}  # name -> label in Settings
DEFAULT_THEME = THEME_DARK

# Glass: translucent panels over a navy -> purple gradient. Qt QSS has no blur, so the
# "frost" is a light rgba fill, a 1px light border and a brighter top edge. Separate
# windows (menus, tooltips, dialogs, combo popups) cannot be translucent: opaque values.
# rgba alpha is 0-255.
GLASS: dict[str, str] = {
    # backdrop
    "bg_gradient_start": "#0A0F26",
    "bg_gradient_mid": "#11173A",
    "bg_gradient_end": "#24164A",
    "glow_blue": "rgba(70, 116, 255, 72)",
    "glow_purple": "rgba(150, 88, 255, 60)",
    "glow_none": "rgba(0, 0, 0, 0)",
    # panels
    "panel": "rgba(255, 255, 255, 13)",
    "panel_strong": "rgba(255, 255, 255, 20)",
    "panel_hover": "rgba(255, 255, 255, 26)",
    "panel_selected": "rgba(255, 255, 255, 38)",
    "panel_reading": "rgba(8, 11, 30, 150)",
    "border": "rgba(255, 255, 255, 32)",
    "border_strong": "rgba(255, 255, 255, 56)",
    "highlight": "rgba(255, 255, 255, 72)",
    "user_bubble_top": "rgba(84, 136, 255, 175)",
    "user_bubble_bottom": "rgba(46, 92, 210, 165)",
    "scroll_handle": "rgba(255, 255, 255, 46)",
    "scroll_handle_hover": "rgba(255, 255, 255, 84)",
    # code stays solid and darker than the glass panels
    "code_bg": "#090C1A",
    "code_header": "#131833",
    "code_gutter_text": "#5C6488",
    "inline_code": "#262D52",
    # opaque colors for separate windows
    "popup_bg": "#171C3A",
    "popup_hover": "#272F5A",
    "popup_border": "#3B4377",
    "dialog_bg": "#12172F",
    "input_bg": "#1B2142",
    "selection": "#2F55B8",
}

_current_theme: dict[str, str] = {"name": DEFAULT_THEME}


def normalize_theme(name: str | None) -> str:
    """A known theme name; anything else (None, typos, old values) falls back to Dark."""
    key = (name or "").strip().lower()
    return key if key in THEMES else DEFAULT_THEME


def current_theme() -> str:
    return _current_theme["name"]


def qcolor(value: str):
    """QColor from '#RRGGBB' or 'rgba(r, g, b, a)' (a is 0-255, or 0-1 when it has a dot)."""
    from PySide6.QtGui import QColor

    text = value.strip()
    if text.lower().startswith("rgba(") and text.endswith(")"):
        parts = [p.strip() for p in text[5:-1].split(",")]
        if len(parts) != 4:
            raise ValueError(f"bad rgba color: {value!r}")
        r, g, b = (int(p) for p in parts[:3])
        alpha = round(float(parts[3]) * 255) if "." in parts[3] else int(parts[3])
        return QColor(r, g, b, alpha)
    color = QColor(text)
    if not color.isValid():
        raise ValueError(f"bad color: {value!r}")
    return color


def item_background(selected: bool, theme_name: str | None = None) -> str:
    """Row background for the sidebar lists (selected, else hover)."""
    if normalize_theme(theme_name or current_theme()) == THEME_GLASS:
        return GLASS["panel_selected"] if selected else GLASS["panel_hover"]
    return BG_ITEM_SELECTED if selected else BG_ITEM_HOVER


def code_colors(theme_name: str | None = None) -> dict[str, str]:
    """Solid colors for code blocks, their header, inline code and the line-number gutter."""
    if normalize_theme(theme_name or current_theme()) == THEME_GLASS:
        return {
            "background": GLASS["code_bg"],
            "header": GLASS["code_header"],
            "header_text": TEXT_SECONDARY,
            "inline": GLASS["inline_code"],
            "gutter_bg": GLASS["code_bg"],
            "gutter_text": GLASS["code_gutter_text"],
        }
    return {
        "background": BG_CODE_BLOCK,
        "header": BG_CODE_HEADER,
        "header_text": TEXT_SECONDARY,
        "inline": BG_INLINE_CODE,
        "gutter_bg": BG_CODE_BLOCK,
        "gutter_text": "#5A5A5A",
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
        code {{ background-color: {code_colors()['inline']}; font-family: '{code_font}';
            font-size: {FONT_CODE}px; }}
        strong, b {{ font-weight: 700; }}
    """


def build_stylesheet(ui_font: str | None = None, code_font: str | None = None,
                     theme_name: str = DEFAULT_THEME) -> str:
    """One QSS string for the whole application. Glass = the Dark sheet + an override block."""
    ui_font = ui_font or ui_font_family()
    code_font = code_font or code_font_family()
    sheet = _dark_stylesheet(ui_font, code_font)
    if normalize_theme(theme_name) == THEME_GLASS:
        sheet += _glass_overrides()
    return sheet


def _dark_stylesheet(ui_font: str, code_font: str) -> str:
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


def _glass_overrides() -> str:
    """Appended after the Dark sheet; later rules with the same selector win."""
    g = GLASS
    c = COLORS
    return f"""
/* ========== Glass theme overrides ========== */
QMainWindow {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 {g['bg_gradient_start']}, stop:0.55 {g['bg_gradient_mid']}, stop:1 {g['bg_gradient_end']});
}}
QWidget#glassBackdrop {{
    background: qradialgradient(cx:0.12, cy:0.06, radius:0.75, fx:0.12, fy:0.06,
        stop:0 {g['glow_blue']}, stop:1 {g['glow_none']});
}}
QWidget#chatPanel {{
    background: qradialgradient(cx:0.85, cy:0.95, radius:0.8, fx:0.85, fy:0.95,
        stop:0 {g['glow_purple']}, stop:1 {g['glow_none']});
}}
QWidget#chatInner, QScrollArea#chatView {{ background: transparent; }}

/* ---------- Sidebar ---------- */
QFrame#sidebar {{
    background: {g['panel']};
    border-right: 1px solid {g['border']};
}}
QToolButton#navButton:hover, QToolButton#iconButton:hover, QToolButton#iconButton:checked,
QFrame#modelCard:hover, QPushButton#settingsButton:hover {{ background: {g['panel_hover']}; }}
QLineEdit#searchField {{
    background: {g['panel_strong']};
    border: 1px solid {g['border']};
    border-top-color: {g['highlight']};
}}
QLineEdit#searchField:focus {{ border-color: {c['accent_primary']}; }}
QLabel#modelBadge {{ background: {g['panel_selected']}; }}
QPushButton#settingsButton {{ border-color: {g['border_strong']}; }}

/* ---------- Chat top bar ---------- */
QFrame#topBar {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {g['panel']}, stop:1 {g['glow_none']});
}}
QToolButton#topBarButton:hover, QToolButton#topBarButton:checked {{ background: {g['panel_hover']}; }}

/* ---------- Messages ---------- */
QLabel#userBubble {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 {g['user_bubble_top']}, stop:1 {g['user_bubble_bottom']});
}}
QLabel#codeChip {{ background: {g['panel_strong']}; }}
QFrame#fileCard, QFrame#agentCard {{
    background: {g['panel_strong']};
    border: 1px solid {g['border']};
    border-top-color: {g['highlight']};
}}
QFrame#fileCard:hover {{ border-color: {g['border_strong']}; border-top-color: {g['highlight']}; }}
QToolButton#actionButton:hover, QPushButton#secondaryButton:hover {{ background: {g['panel_hover']}; }}
QPushButton#secondaryButton {{ border-color: {g['border_strong']}; }}
QPlainTextEdit#diffView {{ background: {g['code_bg']}; border-color: {g['border']}; }}
QLabel#toast {{ background: {g['popup_bg']}; border-color: {g['popup_border']}; }}

/* ---------- Composer ---------- */
QFrame#composerPill {{
    background: {g['panel_strong']};
    border: 1px solid {g['border']};
    border-top-color: {g['highlight']};
}}
QPushButton#projectChip:hover {{ background: {g['panel_hover']}; }}

/* ---------- Preview panel ---------- */
QFrame#previewPanel {{ background: {g['panel']}; border-left: 1px solid {g['border']}; }}
QFrame#previewHeader {{ background: {g['panel']}; }}
QToolButton#fileDropdown, QToolButton#roundButton, QPushButton#linkButton {{ background: {g['panel_strong']}; }}
QToolButton#fileDropdown:hover, QToolButton#roundButton:hover, QToolButton#roundButton:checked,
QPushButton#linkButton:hover {{ background: {g['panel_selected']}; }}
QPushButton#tabButton:checked {{ background: {g['panel_selected']}; }}
QTreeWidget#fileTree {{ background: transparent; border-bottom: 1px solid {g['border']}; }}
QTreeWidget#fileTree::item:selected {{ background: {g['panel_selected']}; }}
QTreeWidget#fileTree::item:hover {{ background: {g['panel_hover']}; }}
QPlainTextEdit#codeView {{ background: {g['code_bg']}; }}
QTextBrowser#markdownPreview, QTextBrowser#htmlFallback {{ background: {g['panel_reading']}; }}
QFrame#previewNotice {{ background: {g['panel_strong']}; border-bottom-color: {g['border']}; }}

/* ---------- Common ---------- */
QSplitter::handle {{ background: {g['border']}; }}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{ background: {g['scroll_handle']}; }}
QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {{ background: {g['scroll_handle_hover']}; }}
/* menus, tooltips, dialogs and combo popups are separate windows: opaque colors only */
QMenu {{ background: {g['popup_bg']}; border: 1px solid {g['popup_border']}; }}
QMenu::item:selected {{ background: {g['popup_hover']}; }}
QToolTip {{ background: {g['popup_bg']}; border: 1px solid {g['popup_border']}; }}
QDialog {{ background: {g['dialog_bg']}; }}
QPushButton {{ background: {g['popup_bg']}; border-color: {g['popup_border']}; }}
QPushButton:hover {{ background: {g['popup_hover']}; }}
QLabel#commandText {{ background: {g['code_bg']}; border-color: {g['popup_border']}; }}
QLineEdit {{ background: {g['input_bg']}; border: 1px solid {g['popup_border']}; }}
QComboBox {{
    background: {g['input_bg']};
    border: 1px solid {g['popup_border']};
    border-radius: 8px;
    padding: 4px 8px;
}}
QComboBox QAbstractItemView {{
    background: {g['popup_bg']};
    border: 1px solid {g['popup_border']};
    selection-background-color: {g['popup_hover']};
    outline: 0;
}}
"""


def _palette_colors(theme_name: str) -> dict[str, str]:
    """QPalette role name -> color. Glass uses opaque colors (palettes also back separate windows)."""
    if theme_name == THEME_GLASS:
        g = GLASS
        return {
            "Window": g["dialog_bg"], "WindowText": TEXT_PRIMARY, "Base": g["input_bg"],
            "AlternateBase": g["popup_hover"], "Text": TEXT_PRIMARY, "Button": g["popup_bg"],
            "ButtonText": TEXT_PRIMARY, "Highlight": g["selection"], "HighlightedText": WHITE,
            "ToolTipBase": g["popup_bg"], "ToolTipText": TEXT_PRIMARY, "PlaceholderText": TEXT_SECONDARY,
            "Link": ACCENT_PRIMARY,
        }
    return {
        "Window": BG_APP, "WindowText": TEXT_PRIMARY, "Base": BG_CARD, "AlternateBase": BG_ITEM_HOVER,
        "Text": TEXT_PRIMARY, "Button": BG_BUTTON_ROUND, "ButtonText": TEXT_PRIMARY,
        "Highlight": ACCENT_USER_BUBBLE, "HighlightedText": WHITE, "ToolTipBase": BG_BUTTON_ROUND,
        "ToolTipText": TEXT_PRIMARY, "PlaceholderText": TEXT_SECONDARY, "Link": ACCENT_PRIMARY,
    }


def apply_theme(app, theme_name: str = DEFAULT_THEME) -> tuple[str, str]:
    """Apply Fusion style, the theme's palette, fonts and stylesheet to a QApplication.

    Can be called again at any time to switch themes live.
    """
    from PySide6.QtGui import QColor, QFont, QPalette

    name = normalize_theme(theme_name)
    ui_font, code_font = resolve_fonts()
    app.setStyle("Fusion")

    palette = QPalette()
    for role_name, color in _palette_colors(name).items():
        palette.setColor(getattr(QPalette.ColorRole, role_name), QColor(color))
    app.setPalette(palette)

    font = QFont(ui_font)
    font.setPixelSize(FONT_SIDEBAR_ITEM)
    app.setFont(font)
    _current_theme["name"] = name  # set before the repaint, so Python-drawn colors follow
    app.setStyleSheet(build_stylesheet(ui_font, code_font, name))
    return ui_font, code_font
