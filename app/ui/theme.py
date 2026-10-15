"""Design tokens (colors, fonts, sizes) and the generated Qt stylesheet.

Values come from UI_DESIGN.md. Every color used by the UI is defined here once.
"""

from __future__ import annotations

from collections.abc import Iterable

# --- Color tokens (UI_DESIGN.md section 2) ---------------------------------
# Two complete palettes with identical token names. DARK is the original design.
# The active palette is copied into the module-level UPPERCASE names and COLORS by
# set_palette(), so code that reads ``theme.TEXT_PRIMARY`` at call time follows the theme.
DARK: dict[str, str] = {
    "bg_app": "#000000",
    "bg_sidebar": "#000000",
    "border_subtle": "#1F1F1F",
    "bg_item_hover": "#1A1A1A",
    "bg_item_selected": "#262626",
    "bg_card": "#171717",
    "border_card": "#333333",
    "border_hover": "#4A4A4A",
    "bg_inline_code": "#2A2A2A",
    "bg_code_block": "#0D0D0D",
    "bg_code_header": "#171717",
    "text_primary": "#ECECEC",
    "text_secondary": "#9B9B9B",
    "text_disabled": "#4A4A4A",
    "accent_user_bubble": "#1E4A8C",
    "user_bubble_text": "#FFFFFF",
    "accent_primary": "#2F6FE0",
    "accent_primary_hover": "#4A82E8",
    "accent_disabled": "#22324F",
    "on_accent": "#FFFFFF",
    "success": "#3FB950",
    "error": "#F85149",
    "warning": "#D29922",
    "bg_error_card": "#1C0F0F",
    "bg_retry_hover": "#2A1414",
    "preview_bg_start": "#1E2A5A",
    "preview_bg_end": "#4B3A9A",
    "bg_button_round": "#1F1F1F",
    "bg_button_round_hover": "#2E2E2E",
    "chip_on_bg": "#16243D",
    "chip_on_text": "#8FB6FF",
    "scrollbar": "#3A3A3A",
    "scrollbar_hover": "#555555",
    "gutter_bg": "#0D0D0D",
    "gutter_text": "#8A8A8A",
    "white": "#FFFFFF",
}

LIGHT: dict[str, str] = {
    "bg_app": "#FFFFFF",
    "bg_sidebar": "#F9F9F9",
    "border_subtle": "#E5E5E5",
    "bg_item_hover": "#EFEFEF",
    "bg_item_selected": "#E3E3E3",
    "bg_card": "#F4F4F4",
    "border_card": "#D9D9D9",
    "border_hover": "#B8B8B8",
    "bg_inline_code": "#ECECEC",
    "bg_code_block": "#F6F8FA",
    "bg_code_header": "#EAEEF2",
    "text_primary": "#1F1F1F",
    "text_secondary": "#5F5F5F",
    "text_disabled": "#A8A8A8",
    "accent_user_bubble": "#DCE8FB",
    "user_bubble_text": "#1F1F1F",
    "accent_primary": "#2F6FE0",
    "accent_primary_hover": "#2459B8",
    "accent_disabled": "#B8CBF2",
    "on_accent": "#FFFFFF",
    "success": "#1A7F37",
    "error": "#CF222E",
    "warning": "#9A6700",
    "bg_error_card": "#FFEBE9",
    "bg_retry_hover": "#FFD8D3",
    "preview_bg_start": "#EEF2FF",
    "preview_bg_end": "#E9E3FF",
    "bg_button_round": "#EDEDED",
    "bg_button_round_hover": "#E0E0E0",
    "chip_on_bg": "#DCE8FB",
    "chip_on_text": "#1F4FB0",
    "scrollbar": "#C8C8C8",
    "scrollbar_hover": "#A8A8A8",
    "gutter_bg": "#F6F8FA",
    "gutter_text": "#57606A",
    "white": "#FFFFFF",
}

# Glass: the same tokens, all opaque. They color dialogs, menus, tooltips, the Qt palette and
# code (code stays solid). The translucent look comes from GLASS_EFFECTS, used only by the
# override block that build_stylesheet() appends while Glass is active. Qt QSS has no blur.
GLASS: dict[str, str] = {
    "bg_app": "#0E1330",
    "bg_sidebar": "#111737",
    "border_subtle": "#2A3160",
    "bg_item_hover": "#1D2448",
    "bg_item_selected": "#283058",
    "bg_card": "#161C3B",
    "border_card": "#3B4377",
    "border_hover": "#56609A",
    "bg_inline_code": "#262D52",
    "bg_code_block": "#090C1A",
    "bg_code_header": "#131833",
    "text_primary": "#ECECEC",
    "text_secondary": "#B4BAD6",
    "text_disabled": "#4E5680",
    "accent_user_bubble": "#2F55B8",
    "user_bubble_text": "#FFFFFF",
    "accent_primary": "#2F6FE0",
    "accent_primary_hover": "#4A82E8",
    "accent_disabled": "#2A3A6E",
    "on_accent": "#FFFFFF",
    "success": "#3FB950",
    "error": "#F85149",
    "warning": "#D29922",
    "bg_error_card": "#2A1424",
    "bg_retry_hover": "#3A1A2C",
    "preview_bg_start": "#1E2A5A",
    "preview_bg_end": "#4B3A9A",
    "bg_button_round": "#1B2142",
    "bg_button_round_hover": "#272F5A",
    "chip_on_bg": "#1B2B55",
    "chip_on_text": "#8FB6FF",
    "scrollbar": "#3B4377",
    "scrollbar_hover": "#56609A",
    "gutter_bg": "#090C1A",
    "gutter_text": "#8A90B0",
    "white": "#FFFFFF",
}

# Glass-only effects (rgba alpha is 0-255): backdrop gradient + glows, translucent panels,
# light borders and a brighter top edge. Only for widgets inside the main window.
GLASS_EFFECTS: dict[str, str] = {
    "bg_gradient_start": "#0A0F26",
    "bg_gradient_mid": "#11173A",
    "bg_gradient_end": "#24164A",
    "glow_blue": "rgba(70, 116, 255, 72)",
    "glow_purple": "rgba(150, 88, 255, 60)",
    "glow_none": "rgba(0, 0, 0, 0)",
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
}

PALETTES: dict[str, dict[str, str]] = {"dark": DARK, "light": LIGHT, "glass": GLASS}
CODE_STYLES: dict[str, str] = {"dark": "github-dark", "light": "default", "glass": "github-dark"}  # Pygments
THEME_MODES = ("dark", "light", "system", "glass")
DEFAULT_THEME_MODE = "dark"

COLORS: dict[str, str] = dict(DARK)
_active_palette = "dark"
CODE_STYLE = CODE_STYLES["dark"]

# Module-level names (set from the active palette by set_palette)
BG_APP = BG_SIDEBAR = BORDER_SUBTLE = BG_ITEM_HOVER = BG_ITEM_SELECTED = BG_CARD = BORDER_CARD = ""
BORDER_HOVER = BG_INLINE_CODE = BG_CODE_BLOCK = BG_CODE_HEADER = TEXT_PRIMARY = TEXT_SECONDARY = ""
TEXT_DISABLED = ACCENT_USER_BUBBLE = USER_BUBBLE_TEXT = ACCENT_PRIMARY = ACCENT_PRIMARY_HOVER = ""
ACCENT_DISABLED = ON_ACCENT = SUCCESS = ERROR = WARNING = BG_ERROR_CARD = BG_RETRY_HOVER = ""
PREVIEW_BG_START = PREVIEW_BG_END = BG_BUTTON_ROUND = BG_BUTTON_ROUND_HOVER = CHIP_ON_BG = ""
CHIP_ON_TEXT = SCROLLBAR = SCROLLBAR_HOVER = GUTTER_BG = GUTTER_TEXT = WHITE = ""


def set_palette(name: str) -> None:
    """Make ``name`` ("dark", "light" or "glass") the active palette for every later ``theme.X`` read."""
    global _active_palette, CODE_STYLE
    if name not in PALETTES:
        raise ValueError(f"Unknown palette {name!r}; use one of {', '.join(PALETTES)}")
    palette = PALETTES[name]
    COLORS.clear()
    COLORS.update(palette)
    globals().update({key.upper(): value for key, value in palette.items()})
    _active_palette = name
    CODE_STYLE = CODE_STYLES[name]


def active_palette() -> str:
    return _active_palette


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


def item_background(selected: bool) -> str:
    """Sidebar row background (selected, else hover); translucent in Glass."""
    if _active_palette == "glass":
        return GLASS_EFFECTS["panel_selected" if selected else "panel_hover"]
    return BG_ITEM_SELECTED if selected else BG_ITEM_HOVER


set_palette("dark")


# --- Typography (section 3) -------------------------------------------------
UI_FONT_CANDIDATES = ("Segoe UI", "Arial")
CODE_FONT_CANDIDATES = ("Cascadia Code", "Cascadia Mono", "Consolas", "Courier New")
FONT_APP_TITLE = 20
FONT_SIDEBAR_ITEM = 15
FONT_SECTION_LABEL = 14
FONT_MESSAGE = 16
FONT_CODE = 14
FONT_DISCLAIMER = 12

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
    """One QSS string for the whole application, generated from the tokens (+ Glass overrides)."""
    ui_font = ui_font or ui_font_family()
    code_font = code_font or code_font_family()
    sheet = _base_stylesheet(ui_font, code_font)
    if _active_palette == "glass":
        sheet += _glass_overrides()
    return sheet


def _base_stylesheet(ui_font: str, code_font: str) -> str:
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
    color: {c['user_bubble_text']};
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
QFrame#fileCard:hover {{ border-color: {c['border_hover']}; }}
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
QPushButton#retryButton:hover {{ background: {c['bg_retry_hover']}; }}
QFrame#agentCard {{
    background: {c['bg_card']};
    border: 1px solid {c['border_card']};
    border-radius: 14px;
}}
QLabel#agentTitle {{ font-weight: 600; font-size: {FONT_MESSAGE}px; background: transparent; }}
QLabel#agentText {{ color: {c['text_secondary']}; background: transparent; }}
QPushButton#primaryButton {{
    background: {c['accent_primary']};
    color: {c['on_accent']};
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
QPushButton#secondaryButton:disabled {{ color: {c['text_disabled']}; }}
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
QPushButton#tabButton:disabled {{ color: {c['text_disabled']}; }}
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
QScrollBar::handle:vertical {{ background: {c['scrollbar']}; border-radius: 3px; min-height: 32px; }}
QScrollBar::handle:vertical:hover {{ background: {c['scrollbar_hover']}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {c['scrollbar']}; border-radius: 3px; min-width: 32px; }}
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
QPushButton#approveButton {{ background: {c['accent_primary']}; border-color: {c['accent_primary']}; color: {c['on_accent']}; }}
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
    """Translucent panels over a gradient + glow backdrop. Appended after the base sheet (later
    rules win). Menus, tooltips and dialogs keep the opaque Glass tokens from the base sheet."""
    g = GLASS_EFFECTS
    c = COLORS
    return f"""
/* ========== Glass overrides ========== */
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
QFrame#sidebar {{ background: {g['panel']}; border-right: 1px solid {g['border']}; }}
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
QTextBrowser#markdownPreview, QTextBrowser#htmlFallback {{ background: {g['panel_reading']}; }}
QFrame#previewNotice {{ background: {g['panel_strong']}; border-bottom-color: {g['border']}; }}

/* ---------- Common ---------- */
QSplitter::handle {{ background: {g['border']}; }}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{ background: {g['scroll_handle']}; }}
QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {{ background: {g['scroll_handle_hover']}; }}
"""


def apply_theme(app, palette_name: str | None = None) -> tuple[str, str]:
    """Apply Fusion style, the palette (dark by default), fonts and the stylesheet to a QApplication."""
    from PySide6.QtGui import QColor, QFont, QPalette

    if palette_name is not None:
        set_palette(palette_name)
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
        (role.HighlightedText, ON_ACCENT if _active_palette != "light" else TEXT_PRIMARY),
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


# --- theme mode: Dark / Light / System ----------------------------------------------------
_mode = DEFAULT_THEME_MODE
_system_hooked = False


def theme_mode() -> str:
    return _mode


def resolve_mode(mode: str, scheme=None) -> str:
    """Palette name for a mode. "system" follows Windows (unknown -> dark); "glass" is its own palette."""
    if mode not in THEME_MODES:
        mode = DEFAULT_THEME_MODE
    if mode != "system":
        return mode
    if scheme is None:
        scheme = _system_scheme()
    from PySide6.QtCore import Qt

    return "light" if scheme == Qt.ColorScheme.Light else "dark"


def _system_scheme():
    """Windows' current light/dark setting as a Qt.ColorScheme (Unknown when not available)."""
    from PySide6.QtGui import QGuiApplication

    app = QGuiApplication.instance()
    return app.styleHints().colorScheme() if app is not None else None


def apply_mode(app, mode: str) -> str:
    """Switch the whole running app to ``mode`` now (no restart). Returns the palette used."""
    global _mode, _system_hooked
    _mode = mode if mode in THEME_MODES else DEFAULT_THEME_MODE
    palette = resolve_mode(_mode)
    apply_theme(app, palette)
    from app.ui.icons import refresh_themed

    refresh_themed()
    if not _system_hooked:
        app.styleHints().colorSchemeChanged.connect(_on_system_scheme_changed)
        _system_hooked = True
    return palette


def _on_system_scheme_changed(_scheme=None) -> None:
    if _mode != "system":
        return
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is not None:
        apply_mode(app, "system")
