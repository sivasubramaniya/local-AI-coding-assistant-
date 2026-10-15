"""Glass theme (Phase 17): palette, stylesheet, readability, live switching, persistence, window effects.

Offscreen, MOCK model. Light / Dark / System output is locked by hashes taken before Glass existed.
"""

import hashlib
import re
import sys

import pytest

from app.ui import theme, window_effects
from tests.test_theme_switching import CONTRAST_PAIRS, _assistant, _icon_color, contrast

HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
RGBA = re.compile(r"^rgba\((\d{1,3}), (\d{1,3}), (\d{1,3}), (\d{1,3})\)$")
# sha256 of build_stylesheet / message_document_css / code_block_html ("Segoe UI", "Consolas") on main
# before Phase 17. They must never change: Glass must not alter the other themes.
UNCHANGED = {
    "dark": ("2e8dc42516ca547c3562a81804170cc3c5f1a8314ab4681761d9c36a84654597",
             "a4fff4a4c3f20f5a190705da46e22ec78fbe8bb5d2136d9003809f89d2d3c807",
             "aeb8229b5226dc23c154952e8f76dd132f0ca6fb2e951899ad276a3be517343a"),
    "light": ("abb72933c767bf7e70cb17f1d09dc5c4f8ffa1eba6276ec28bfffacabeec96fe",
              "bcd8ab2359e61c527411ec149ef8eb9cc899761255cb6a808b750691d454bda1",
              "dc48b514b8d8759e207a0a1cbebb95e7a3912931bb10ee257f88a129a822f7a4"),
}
GLASS_OBJECTS = ("#glassBackdrop", "#chatPanel", "#sidebar", "#topBar", "#composerPill", "#userBubble",
                 "#fileCard", "#agentCard", "#previewPanel", "#previewHeader", "#fileTree")


@pytest.fixture(autouse=True)
def back_to_dark():
    yield
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is not None:
        theme.apply_mode(app, "dark")
    else:
        theme.set_palette("dark")


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _outputs(palette: str) -> tuple[str, str, str]:
    from app.ui import markdown_render as mr

    theme.set_palette(palette)
    block = mr.code_block_html(mr.CodeBlock("python", "x = 1"), 0, "Consolas")
    return (_sha(theme.build_stylesheet("Segoe UI", "Consolas")), _sha(theme.message_document_css("Consolas")),
            _sha(block))


def _glass_sheet() -> str:
    theme.set_palette("glass")
    return theme.build_stylesheet("Segoe UI", "Consolas")


def _overrides() -> str:
    sheet = _glass_sheet()
    return sheet[sheet.index("/* ========== Glass overrides"):]


# --- other themes unchanged ------------------------------------------------------------------
@pytest.mark.parametrize("palette", ["dark", "light"])
def test_light_and_dark_output_unchanged(palette):
    assert _outputs(palette) == UNCHANGED[palette]


def test_system_mode_still_resolves_to_dark_or_light():
    from PySide6.QtCore import Qt

    assert theme.resolve_mode("system", Qt.ColorScheme.Light) == "light"
    assert theme.resolve_mode("system", Qt.ColorScheme.Dark) == "dark"
    assert theme.resolve_mode("system", Qt.ColorScheme.Unknown) == "dark"
    assert theme.resolve_mode("glass") == "glass"
    assert theme.resolve_mode("neon") == "dark"


def test_dark_and_light_never_get_glass_rules():
    for palette in ("dark", "light"):
        theme.set_palette(palette)
        assert "Glass overrides" not in theme.build_stylesheet("Segoe UI", "Consolas")
        assert theme.item_background(True) == theme.BG_ITEM_SELECTED
        assert theme.item_background(False) == theme.BG_ITEM_HOVER


# --- palette and effects -----------------------------------------------------------------------
def test_glass_palette_fits_the_phase_15_structure():
    assert set(theme.GLASS) == set(theme.DARK) == set(theme.LIGHT)
    assert not {k: v for k, v in theme.GLASS.items() if not HEX.match(v)}
    assert "glass" in theme.PALETTES and "glass" in theme.THEME_MODES and "glass" in theme.CODE_STYLES
    theme.set_palette("glass")
    assert theme.active_palette() == "glass" and theme.TEXT_PRIMARY == theme.GLASS["text_primary"]
    assert theme.CODE_STYLE == "github-dark"


@pytest.mark.parametrize("name", sorted(theme.GLASS_EFFECTS))
def test_glass_effects_are_valid_rgba_or_hex(name):
    value = theme.GLASS_EFFECTS[name]
    match = RGBA.match(value)
    assert match or HEX.match(value), f"{name} = {value!r}"
    if match:
        assert all(0 <= int(part) <= 255 for part in match.groups()), value
    assert theme.qcolor(value).isValid()


def test_glass_palette_meets_wcag_aa():
    failures = [f"{fg} on {bg}" for fg, bg, minimum in CONTRAST_PAIRS
                if contrast(theme.GLASS[fg], theme.GLASS[bg]) < minimum]
    assert not failures, failures


def _blend(top: str, bottom: str) -> str:
    """Composite a (possibly rgba) color over an opaque one; returns opaque hex."""
    t, b = theme.qcolor(top), theme.qcolor(bottom)
    a = t.alphaF()
    mix = [round(a * x + (1 - a) * y) for x, y in ((t.red(), b.red()), (t.green(), b.green()), (t.blue(), b.blue()))]
    return "#{:02X}{:02X}{:02X}".format(*mix)


def test_text_is_readable_on_translucent_panels():
    """Translucent panels composited over every backdrop color (gradient stops, with and without the
    glows) still give WCAG AA (4.5:1) for the text that is drawn on them."""
    e, g = theme.GLASS_EFFECTS, theme.GLASS
    backdrops = []
    for stop in ("bg_gradient_start", "bg_gradient_mid", "bg_gradient_end"):
        backdrops += [e[stop], _blend(e["glow_blue"], e[stop]), _blend(e["glow_purple"], e[stop])]
    surfaces = {  # surface -> text tokens drawn on it
        "chat": ([], ("text_primary", "text_secondary")),
        "sidebar": (["panel"], ("text_primary", "text_secondary")),
        "sidebar row hover": (["panel", "panel_hover"], ("text_primary",)),
        "sidebar row selected": (["panel", "panel_selected"], ("text_primary",)),
        "card / composer": (["panel_strong"], ("text_primary", "text_secondary")),
        "preview reading": (["panel", "panel_reading"], ("text_primary",)),
    }
    failures = []
    for backdrop in backdrops:
        for name, (layers, texts) in surfaces.items():
            color = backdrop
            for layer in layers:
                color = _blend(e[layer], color)
            failures += [f"{t} on {name} over {backdrop}: {contrast(g[t], color):.2f}"
                         for t in texts if contrast(g[t], color) < 4.5]
        for bubble in ("user_bubble_top", "user_bubble_bottom"):
            color = _blend(e[bubble], backdrop)
            if contrast(g["user_bubble_text"], color) < 4.5:
                failures.append(f"bubble text on {bubble} over {backdrop}")
    assert not failures, "\n".join(failures)


def test_qcolor_parses_rgba_and_hex():
    color = theme.qcolor("rgba(255, 128, 0, 64)")
    assert (color.red(), color.green(), color.blue(), color.alpha()) == (255, 128, 0, 64)
    assert theme.qcolor("rgba(0, 0, 0, 0.5)").alpha() == 128
    assert theme.qcolor("#1A2B3C").name().upper() == "#1A2B3C"
    with pytest.raises(ValueError):
        theme.qcolor("rgba(1, 2, 3)")
    with pytest.raises(ValueError):
        theme.qcolor("not-a-color")


def test_glass_sidebar_rows_are_translucent():
    theme.set_palette("glass")
    assert theme.item_background(True) == theme.GLASS_EFFECTS["panel_selected"]
    assert theme.qcolor(theme.item_background(False)).alpha() < 255


# --- stylesheet --------------------------------------------------------------------------------
def test_glass_stylesheet_builds():
    sheet = _glass_sheet()
    assert sheet.count("{") == sheet.count("}")
    overrides = _overrides()
    for object_name in GLASS_OBJECTS:
        assert object_name in overrides, object_name
    assert "qlineargradient" in overrides and "qradialgradient" in overrides
    assert "backdrop-filter" not in sheet and "blur" not in sheet
    assert "QSpinBox" not in sheet  # styling it removes its arrow buttons


def test_separate_windows_and_code_stay_opaque():
    sheet = _glass_sheet()
    overrides = _overrides()
    for selector in ("QMenu", "QToolTip", "QDialog", "QComboBox", "QLineEdit {", "QPlainTextEdit#codeView",
                     "QPlainTextEdit#diffView", "QLabel#commandText"):
        assert selector not in overrides, selector  # never made translucent
    for selector in ("QMenu {", "QToolTip {", "QDialog {", "QPlainTextEdit#codeView {"):
        rule = sheet[sheet.index(selector):]
        assert "rgba" not in rule[:rule.index("}")], selector
    assert theme.GLASS["bg_code_block"] in sheet


# --- in the window -----------------------------------------------------------------------------
@pytest.fixture
def window(qtbot, themed_app, tmp_config, tmp_path):
    from app.backend.chat_store import ChatMessage
    from app.storage.chat_repository import SqliteChatRepository
    from app.ui.main_window import MainWindow

    repo = SqliteChatRepository.open(tmp_path / "db" / "assistant.db")
    chat = repo.create_chat("Glass test")
    repo.add_message(chat.id, ChatMessage("user", "show code"))
    repo.add_message(chat.id, ChatMessage("assistant", "Here:\n\n```python\ndef add(a, b):\n    return a + b\n```"))
    repo.set_setting("last_chat_id", chat.id)
    win = MainWindow(tmp_config, store=repo, use_webengine=False, health_checks=False)
    qtbot.addWidget(win)
    win.resize(1300, 850)
    win.show()
    yield win
    win.close()
    repo.close()


def test_window_has_the_glass_backdrop(window):
    assert window.centralWidget().objectName() == "glassBackdrop"
    assert window.chat_panel.objectName() == "chatPanel"


def test_switch_dark_glass_dark_live(qtbot, window, themed_app):
    message = _assistant(window)
    dark_sheet = themed_app.styleSheet()
    with qtbot.waitSignal(window.themeApplied, timeout=3000) as blocker:
        window.apply_theme_mode("glass")
    assert blocker.args == ["glass"]
    assert "Glass overrides" in themed_app.styleSheet()
    assert theme.GLASS["bg_code_block"].lower() in message.browser.toHtml().lower()  # re-rendered
    assert _icon_color(window.export_button.icon()) == theme.GLASS["text_primary"]

    window.apply_theme_mode("dark")
    assert themed_app.styleSheet() == dark_sheet
    assert theme.DARK["bg_code_block"].lower() in message.browser.toHtml().lower()


def test_glass_renders_translucent_sidebar(window):
    window.apply_theme_mode("glass")
    sidebar = window.sidebar
    image = window.grab().toImage()
    pixel = image.pixelColor(sidebar.mapTo(window, sidebar.rect().center()))
    assert pixel.name().upper() not in {theme.GLASS["bg_sidebar"], "#000000"}  # backdrop shows through
    assert pixel.blue() > pixel.red()  # navy / purple gradient


def test_settings_offer_glass():
    from app.ui.dialogs import THEME_CHOICES, SettingsDialog

    assert ("Glass", "glass") in THEME_CHOICES
    assert [mode for _, mode in THEME_CHOICES][:3] == ["dark", "light", "system"]  # existing order kept
    assert SettingsDialog("C:/x", 60, theme_mode="glass").theme_mode() == "glass"


def test_glass_is_saved_and_restored_on_restart(qtbot, themed_app, tmp_config, tmp_path):
    from app.storage.chat_repository import SqliteChatRepository
    from app.ui.main_window import THEME_SETTING, MainWindow

    db = tmp_path / "db2" / "assistant.db"
    repo = SqliteChatRepository.open(db)
    win = MainWindow(tmp_config, store=repo, use_webengine=False, health_checks=False)
    qtbot.addWidget(win)
    win.settings_editor = lambda export_dir, timeout: (str(tmp_path / "e"), 60, False, "glass")
    win.open_settings()
    assert repo.get_setting(THEME_SETTING) == "glass" and theme.active_palette() == "glass"
    win.close()
    repo.close()

    theme.apply_mode(themed_app, "dark")  # a fresh start begins dark
    repo2 = SqliteChatRepository.open(db)
    win2 = MainWindow(tmp_config, store=repo2, use_webengine=False, health_checks=False)
    qtbot.addWidget(win2)
    assert theme.active_palette() == "glass" and theme.theme_mode() == "glass"
    assert "Glass overrides" in themed_app.styleSheet()
    win2.close()
    repo2.close()


# --- window effects ----------------------------------------------------------------------------
def test_window_effects_no_op_off_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    assert window_effects.supported() is False
    assert window_effects.apply_window_effects(object(), True) is False
    assert window_effects.apply_window_effects(object(), False) is False


def test_window_effects_no_op_on_offscreen_platform(window):
    assert window_effects.supported() is False  # tests run on the offscreen platform
    assert window_effects.apply_window_effects(window, True) is False


def test_window_effects_never_raise(monkeypatch):
    monkeypatch.setattr(window_effects, "supported", lambda: True)

    class Broken:
        def property(self, _name):
            return True

        def winId(self):  # noqa: N802
            raise RuntimeError("no native window")

    assert window_effects.apply_window_effects(Broken(), True) is False
    assert window_effects.apply_window_effects(Broken(), False) is False


def test_window_switches_effects_with_the_theme(window, monkeypatch):
    calls = []
    monkeypatch.setattr("app.ui.main_window.apply_window_effects", lambda win, enabled: calls.append(enabled))
    window.apply_theme_mode("glass")
    window.apply_theme_mode("light")
    window.apply_theme_mode("dark")
    assert calls == [True, False, False]
