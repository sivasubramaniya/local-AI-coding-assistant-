"""Glass theme: tokens, stylesheet, live switching, settings and window effects (offscreen)."""

import hashlib
import re
import sys

import pytest

from app.ui import theme, window_effects

HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
RGBA = re.compile(r"^rgba\((\d{1,3}), (\d{1,3}), (\d{1,3}), (\d{1,3})\)$")
GLASS_OBJECTS = ("#sidebar", "#composerPill", "#userBubble", "#fileCard", "#previewHeader",
                 "#glassBackdrop", "#chatPanel")
# sha256 of the Dark output before the Glass theme existed (Segoe UI / Consolas); must never change
DARK_QSS_SHA256 = "2e8dc42516ca547c3562a81804170cc3c5f1a8314ab4681761d9c36a84654597"
DARK_CSS_SHA256 = "a4fff4a4c3f20f5a190705da46e22ec78fbe8bb5d2136d9003809f89d2d3c807"
DARK_BLOCK_SHA256 = "aeb8229b5226dc23c154952e8f76dd132f0ca6fb2e951899ad276a3be517343a"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


@pytest.fixture
def dark_after():
    """Tests that switch themes always leave the shared QApplication in Dark."""
    yield
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is not None:
        theme.apply_theme(app, theme.THEME_DARK)
    theme._current_theme["name"] = theme.THEME_DARK


# --- tokens -----------------------------------------------------------------
@pytest.mark.parametrize("name", sorted(theme.GLASS))
def test_glass_tokens_are_valid_rgba_or_hex(name):
    value = theme.GLASS[name]
    match = RGBA.match(value)
    if match:
        assert all(0 <= int(part) <= 255 for part in match.groups()), value
    else:
        assert HEX.match(value), f"{name} = {value!r}"


def test_colors_stay_hex_only():
    assert not any("rgba" in value for value in theme.COLORS.values())


def test_popup_and_code_tokens_are_opaque():
    for key in ("popup_bg", "popup_hover", "popup_border", "dialog_bg", "input_bg",
                "code_bg", "code_header", "inline_code", "selection"):
        assert HEX.match(theme.GLASS[key]), key


def test_theme_names():
    assert theme.THEMES == {"dark": "Dark", "glass": "Glass"}
    assert theme.DEFAULT_THEME == "dark"
    assert theme.normalize_theme("GLASS ") == "glass"
    for bad in (None, "", "light", "neon"):
        assert theme.normalize_theme(bad) == "dark"


# --- stylesheet ---------------------------------------------------------------
def test_dark_output_unchanged():
    from app.ui import markdown_render as mr

    assert _sha(theme.build_stylesheet("Segoe UI", "Consolas")) == DARK_QSS_SHA256
    assert _sha(theme.build_stylesheet("Segoe UI", "Consolas", "dark")) == DARK_QSS_SHA256
    assert _sha(theme.message_document_css("Consolas")) == DARK_CSS_SHA256
    block = mr.code_block_html(mr.CodeBlock("python", "x = 1"), 0, "Consolas")
    assert _sha(block) == DARK_BLOCK_SHA256


def test_unknown_theme_falls_back_to_dark():
    dark = theme.build_stylesheet("Segoe UI", "Consolas")
    assert theme.build_stylesheet("Segoe UI", "Consolas", "light") == dark
    assert theme.build_stylesheet("Segoe UI", "Consolas", "") == dark


def test_glass_stylesheet_is_dark_plus_overrides():
    dark = theme.build_stylesheet("Segoe UI", "Consolas")
    glass = theme.build_stylesheet("Segoe UI", "Consolas", "glass")
    assert glass.startswith(dark) and len(glass) > len(dark)
    assert glass.count("{") == glass.count("}")
    overrides = glass[len(dark):]
    for object_name in GLASS_OBJECTS:
        assert object_name in overrides, object_name
    assert "backdrop-filter" not in glass and "blur" not in glass
    assert "QSpinBox" not in glass  # styling it removes its arrow buttons
    assert theme.GLASS["glow_blue"] in overrides and theme.GLASS["panel"] in overrides


def test_separate_windows_use_opaque_colors():
    overrides = theme.build_stylesheet("Segoe UI", "Consolas", "glass")[
        len(theme.build_stylesheet("Segoe UI", "Consolas")):]
    for selector in ("QMenu {", "QToolTip {", "QDialog {", "QComboBox QAbstractItemView {", "QLineEdit {"):
        rule = overrides[overrides.index(selector):]
        rule = rule[:rule.index("}")]
        assert "rgba" not in rule, selector


def test_glass_code_is_solid_and_darker_than_panels():
    colors = theme.code_colors("glass")
    for key in ("background", "header", "inline", "gutter_bg"):
        assert HEX.match(colors[key]), key
    assert theme.code_colors("glass")["background"] != theme.code_colors("dark")["background"]
    assert theme.code_colors("dark")["background"] == theme.BG_CODE_BLOCK
    assert theme.code_colors("dark")["inline"] == theme.BG_INLINE_CODE


def test_item_background_follows_theme():
    assert theme.item_background(True, "dark") == theme.BG_ITEM_SELECTED
    assert theme.item_background(False, "dark") == theme.BG_ITEM_HOVER
    assert theme.item_background(True, "glass") == theme.GLASS["panel_selected"]
    assert theme.item_background(False, "glass") == theme.GLASS["panel_hover"]


def test_qcolor_parses_rgba_and_hex():
    color = theme.qcolor("rgba(255, 128, 0, 64)")
    assert (color.red(), color.green(), color.blue(), color.alpha()) == (255, 128, 0, 64)
    assert theme.qcolor("rgba(0, 0, 0, 0.5)").alpha() == 128
    hex_color = theme.qcolor("#1A2B3C")
    assert (hex_color.red(), hex_color.green(), hex_color.blue(), hex_color.alpha()) == (0x1A, 0x2B, 0x3C, 255)
    for value in theme.GLASS.values():
        assert theme.qcolor(value).isValid()
    with pytest.raises(ValueError):
        theme.qcolor("rgba(1, 2, 3)")
    with pytest.raises(ValueError):
        theme.qcolor("not-a-color")


# --- live switching -------------------------------------------------------------
@pytest.mark.gui
def test_apply_theme_switches_live(themed_app, dark_after):
    dark_sheet = themed_app.styleSheet()
    assert theme.current_theme() == "dark" and "#glassBackdrop" not in dark_sheet
    theme.apply_theme(themed_app, "glass")
    assert theme.current_theme() == "glass"
    assert "#glassBackdrop" in themed_app.styleSheet()
    assert theme.code_colors()["background"] == theme.GLASS["code_bg"]
    assert theme.GLASS["inline_code"] in theme.message_document_css("Consolas")
    theme.apply_theme(themed_app, "dark")
    assert theme.current_theme() == "dark"
    assert themed_app.styleSheet() == dark_sheet
    assert theme.code_colors()["background"] == theme.BG_CODE_BLOCK


@pytest.mark.gui
def test_glass_renders_translucent_panels(qtbot, themed_app, dark_after):
    """The sidebar is a translucent panel over the gradient, not a solid color."""
    from PySide6.QtWidgets import QFrame, QHBoxLayout, QMainWindow, QWidget

    theme.apply_theme(themed_app, "glass")
    window = QMainWindow()
    central = QWidget()
    central.setObjectName("glassBackdrop")
    sidebar = QFrame()
    sidebar.setObjectName("sidebar")
    sidebar.setFixedWidth(100)
    QHBoxLayout(central).addWidget(sidebar)
    window.setCentralWidget(central)
    window.resize(400, 300)
    qtbot.addWidget(window)
    window.show()
    image = window.grab().toImage()
    pixel = image.pixelColor(sidebar.geometry().center())
    assert pixel.blue() > pixel.red()  # navy shows through the panel
    assert pixel.name() != "#000000"


# --- main window ----------------------------------------------------------------
@pytest.fixture
def make_window(qtbot, themed_app, tmp_config, tmp_path, dark_after):
    from app.backend.ollama_client import OllamaClient
    from app.storage.chat_repository import SqliteChatRepository
    from app.ui.main_window import MainWindow
    from tests.fake_ollama import FakeOllama

    opened = []
    fake = FakeOllama()

    def start():
        repo = SqliteChatRepository.open(tmp_path / "db" / "assistant.db")
        win = MainWindow(tmp_config, store=repo, use_webengine=False, health_checks=False,
                         client_factory=lambda: OllamaClient(tmp_config, transport=fake.transport()))
        qtbot.addWidget(win)
        win.show()
        opened.append((win, repo))
        return win

    yield start
    for win, repo in opened:
        win.close()
        repo.close()


@pytest.mark.gui
def test_window_has_glass_backdrop(make_window):
    win = make_window()
    assert win.centralWidget().objectName() == "glassBackdrop"
    assert win.chat_panel.objectName() == "chatPanel"
    assert win.theme_name() == "dark"


@pytest.mark.gui
def test_settings_theme_saved_applied_live_and_restored(make_window, themed_app, tmp_path):
    from app.ui.main_window import THEME_SETTING
    from app.ui.message_widgets import MarkdownBrowser

    win = make_window()
    browser = MarkdownBrowser(win.chat_panel)
    browser.set_markdown("```python\nx = 1\n```")
    assert theme.BG_CODE_BLOCK.lower() in browser.toHtml().lower()

    win.settings_editor = lambda export_dir, timeout: (str(tmp_path / "e"), 60, False, "glass")
    win.open_settings()
    assert win.store.get_setting(THEME_SETTING) == "glass"
    assert win.theme_name() == "glass" and theme.current_theme() == "glass"
    assert "#glassBackdrop" in themed_app.styleSheet()
    assert theme.GLASS["code_bg"].lower() in browser.toHtml().lower()  # existing answers re-rendered

    # old 2- and 3-value editors keep working and keep the current theme
    win.settings_editor = lambda export_dir, timeout: (str(tmp_path / "e"), 60)
    win.open_settings()
    assert win.theme_name() == "glass" and win.store.get_setting(THEME_SETTING) == "glass"
    win.settings_editor = lambda export_dir, timeout: (str(tmp_path / "e"), 60, False)
    win.open_settings()
    assert win.theme_name() == "glass"

    win.close()
    win.store.close()
    theme.apply_theme(themed_app, "dark")  # a fresh start begins in Dark
    win2 = make_window()
    assert win2.theme_name() == "glass" and theme.current_theme() == "glass"

    win2.settings_editor = lambda export_dir, timeout: (str(tmp_path / "e"), 60, False, "dark")
    win2.open_settings()
    assert win2.store.get_setting(THEME_SETTING) == "dark"
    assert theme.current_theme() == "dark" and "#glassBackdrop" not in themed_app.styleSheet()


@pytest.mark.gui
def test_bad_saved_theme_falls_back_to_dark(make_window, tmp_path):
    from app.storage.chat_repository import SqliteChatRepository
    from app.ui.main_window import THEME_SETTING

    repo = SqliteChatRepository.open(tmp_path / "db" / "assistant.db")
    repo.set_setting(THEME_SETTING, "light")
    repo.close()
    win = make_window()
    assert win.theme_name() == "dark" and theme.current_theme() == "dark"


# --- window effects -------------------------------------------------------------
def test_window_effects_no_op_off_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    assert window_effects.supported() is False
    assert window_effects.apply_window_effects(object(), True) is False
    assert window_effects.apply_window_effects(object(), False) is False


@pytest.mark.gui
def test_window_effects_no_op_on_offscreen_platform(qtbot, themed_app):
    from PySide6.QtWidgets import QMainWindow

    window = QMainWindow()
    qtbot.addWidget(window)
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
