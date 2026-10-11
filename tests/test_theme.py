import re

import pytest

from app.ui import theme

HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
SPEC_TOKENS = {
    "bg_app": "#000000", "bg_sidebar": "#000000", "border_subtle": "#1F1F1F",
    "bg_item_hover": "#1A1A1A", "bg_item_selected": "#262626", "bg_card": "#171717",
    "border_card": "#333333", "bg_inline_code": "#2A2A2A", "bg_code_block": "#0D0D0D",
    "text_primary": "#ECECEC", "text_secondary": "#9B9B9B", "accent_user_bubble": "#1E4A8C",
    "accent_primary": "#2F6FE0", "success": "#3FB950", "error": "#F85149",
    "preview_bg_start": "#1E2A5A", "preview_bg_end": "#4B3A9A",
}


@pytest.mark.parametrize("name", sorted(theme.COLORS))
def test_all_tokens_are_valid_hex(name):
    assert HEX.match(theme.COLORS[name]), f"{name} = {theme.COLORS[name]!r}"


def test_spec_tokens_match_ui_design():
    for name, value in SPEC_TOKENS.items():
        assert theme.COLORS[name].upper() == value


def test_stylesheet_builds_from_tokens():
    qss = theme.build_stylesheet("Segoe UI", "Consolas")
    assert qss.count("{") == qss.count("}")
    for key in ("bg_card", "accent_primary", "accent_user_bubble", "text_secondary"):
        assert theme.COLORS[key] in qss
    for object_name in ("#sidebar", "#userBubble", "#composerPill", "#sendButton", "#fileCard", "#previewHeader"):
        assert object_name in qss
    assert '"Consolas"' in qss


def test_message_css_uses_code_font():
    css = theme.message_document_css("Consolas")
    assert "Consolas" in css and theme.BG_INLINE_CODE in css


def test_pick_font_prefers_first_installed():
    assert theme.pick_font(("Cascadia Code", "Consolas"), ["Arial", "consolas"]) == "Consolas"
    assert theme.pick_font(("Cascadia Code", "Consolas"), ["Cascadia Code"]) == "Cascadia Code"
    assert theme.pick_font(("A", "B"), []) == "B"


@pytest.mark.gui
def test_resolve_fonts_returns_candidates(qapp):
    ui, code = theme.resolve_fonts()
    assert ui in theme.UI_FONT_CANDIDATES
    assert code in theme.CODE_FONT_CANDIDATES


@pytest.mark.gui
def test_apply_theme(themed_app):
    assert "#composerPill" in themed_app.styleSheet()
