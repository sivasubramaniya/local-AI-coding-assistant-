"""Light / Dark / System themes: palettes, contrast, live switching, persistence. Offscreen, MOCK model."""

import re
from pathlib import Path

import pytest

from app.ui import theme

ROOT = Path(__file__).resolve().parent.parent
HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")

# (foreground token, background token, minimum ratio). 4.5 = WCAG AA for text; 3.0 = AA for UI parts.
CONTRAST_PAIRS = [
    *[("text_primary", bg, 4.5) for bg in ("bg_app", "bg_sidebar", "bg_card", "bg_item_hover", "bg_item_selected",
                                            "bg_code_block", "bg_code_header", "bg_inline_code", "bg_error_card",
                                            "bg_button_round", "preview_bg_start", "preview_bg_end")],
    *[("text_secondary", bg, 4.5) for bg in ("bg_app", "bg_sidebar", "bg_card", "bg_item_hover",
                                              "bg_code_header", "bg_button_round")],
    ("user_bubble_text", "accent_user_bubble", 4.5),
    ("on_accent", "accent_primary", 4.5),
    ("chip_on_text", "chip_on_bg", 4.5),
    ("gutter_text", "gutter_bg", 4.5),
    *[(dot, bg, 3.0) for dot in ("success", "error", "warning") for bg in ("bg_sidebar", "bg_app")],
    ("error", "bg_error_card", 3.0),  # the error card border
]


def luminance(hex_color: str) -> float:
    def channel(value: int) -> float:
        c = value / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast(a: str, b: str) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


@pytest.fixture(autouse=True)
def back_to_dark():
    yield
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is not None:
        theme.apply_mode(app, "dark")
    else:
        theme.set_palette("dark")


# --- palettes ---------------------------------------------------------------------------------
def test_palettes_have_identical_tokens_and_valid_hex():
    assert set(theme.DARK) == set(theme.LIGHT)
    for name, palette in theme.PALETTES.items():
        bad = {k: v for k, v in palette.items() if not HEX.match(v)}
        assert not bad, f"{name}: invalid colors {bad}"


@pytest.mark.parametrize("palette_name", ["dark", "light"])
def test_text_contrast_meets_wcag_aa(palette_name):
    palette = theme.PALETTES[palette_name]
    failures = []
    for fg, bg, minimum in CONTRAST_PAIRS:
        ratio = contrast(palette[fg], palette[bg])
        if ratio < minimum:
            failures.append(f"{fg} {palette[fg]} on {bg} {palette[bg]}: {ratio:.2f} < {minimum}")
    assert not failures, "\n".join(failures)


def test_dark_palette_is_unchanged_from_the_original_design():
    original = {"bg_app": "#000000", "bg_card": "#171717", "text_primary": "#ECECEC", "text_secondary": "#9B9B9B",
                "accent_user_bubble": "#1E4A8C", "accent_primary": "#2F6FE0", "success": "#3FB950",
                "error": "#F85149", "warning": "#D29922", "preview_bg_start": "#1E2A5A"}
    assert {k: theme.DARK[k] for k in original} == original


def test_set_palette_updates_module_tokens_and_code_style():
    theme.set_palette("light")
    assert theme.TEXT_PRIMARY == theme.LIGHT["text_primary"] and theme.COLORS["bg_app"] == "#FFFFFF"
    assert theme.CODE_STYLE == "default"
    theme.set_palette("dark")
    assert theme.TEXT_PRIMARY == "#ECECEC" and theme.CODE_STYLE == "github-dark"
    with pytest.raises(ValueError):
        theme.set_palette("purple")


def test_no_hex_colors_in_ui_code_outside_theme():
    allow = {
        "theme.py": "the palettes live here",
        "demo.py": "colors inside the demo web page's own HTML (content, not UI)",
    }
    pattern = re.compile(r"#[0-9A-Fa-f]{6}\b|#[0-9A-Fa-f]{3}\b(?![0-9A-Za-z])")
    offenders = {}
    for path in sorted((ROOT / "app" / "ui").glob("*.py")):
        if path.name in allow:
            continue
        hits = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()
                if pattern.search(line) and not line.strip().startswith("#")]
        if hits:
            offenders[path.name] = hits[:3]
    assert not offenders, f"hard-coded colors outside theme.py: {offenders}"


# --- live switching in the window --------------------------------------------------------------
def _icon_color(icon, size=20):
    image = icon.pixmap(size, size).toImage()
    for y in range(image.height()):
        for x in range(image.width()):
            color = image.pixelColor(x, y)
            if color.alpha() > 230:
                return color.name().upper()
    return None


@pytest.fixture
def window(qtbot, themed_app, tmp_config, tmp_path):
    from app.backend.chat_store import ChatMessage
    from app.storage.chat_repository import SqliteChatRepository
    from app.ui.main_window import MainWindow

    repo = SqliteChatRepository.open(tmp_path / "db" / "assistant.db")
    chat = repo.create_chat("Theme test")
    repo.add_message(chat.id, ChatMessage("user", "show code"))
    repo.add_message(chat.id, ChatMessage("assistant", "Here:\n\n```python\ndef add(a, b):\n    return a + b\n```"))
    repo.set_setting("last_chat_id", chat.id)
    win = MainWindow(tmp_config, store=repo, use_webengine=False, health_checks=False)
    qtbot.addWidget(win)
    win.resize(1300, 850)
    win.show()
    win.preview.set_project("p", {"app.py": "def add(a, b):\n    return a + b\n"})
    win.open_file("app.py")
    yield win
    win.close()
    repo.close()


def _assistant(win):
    from app.ui.message_widgets import AssistantMessage

    return [w for w in win.chat_view.items if isinstance(w, AssistantMessage)][0]


def test_switch_dark_light_dark_updates_everything_live(qtbot, window, themed_app):
    win = window
    message = _assistant(win)
    assert theme.active_palette() == "dark"
    dark_html = message.browser.toHtml()
    assert _icon_color(win.export_button.icon()) == theme.DARK["text_primary"]

    with qtbot.waitSignal(win.themeApplied, timeout=3000) as blocker:
        win.apply_theme_mode("light")
    assert blocker.args == ["light"]
    assert "#ffffff" in themed_app.styleSheet().lower()  # light backgrounds in the app stylesheet
    assert _icon_color(win.export_button.icon()) == theme.LIGHT["text_primary"]
    assert _icon_color(win.composer.attach_button.icon(), 22) == theme.LIGHT["text_primary"]
    light_html = message.browser.toHtml()
    assert light_html != dark_html  # the already-rendered answer was re-rendered
    assert theme.LIGHT["text_primary"].lower() in message.browser.document().defaultStyleSheet().lower()
    assert theme.LIGHT["bg_code_block"].lower() in light_html.lower()
    gutter = win.preview.code_view
    assert gutter.toPlainText().startswith("def add")  # code viewer kept its file after re-highlighting
    assert win.sidebar.status_card.dot.styleSheet()  # status dot repainted with the light palette

    win.apply_theme_mode("dark")
    assert _icon_color(win.export_button.icon()) == theme.DARK["text_primary"]
    assert theme.DARK["bg_code_block"].lower() in message.browser.toHtml().lower()


def test_new_widgets_after_switch_use_the_new_theme(qtbot, window):
    from app.ui.dialogs import SettingsDialog

    window.apply_theme_mode("light")
    window.new_chat()
    message = window.chat_view.add_assistant_message("status")
    message.set_text("plain text")
    message.finish()
    assert _icon_color(message.actions.copy_button.icon(), theme.ACTION_ICON_SIZE) == theme.LIGHT["text_secondary"]
    dialog = SettingsDialog("C:/x", 60, theme_mode="light")
    assert dialog.theme_mode() == "light"


def test_system_mode_follows_windows_and_its_change_signal(qtbot, window, themed_app, monkeypatch):
    """The offscreen test platform has no color scheme, so the scheme *read* is mocked; the change
    notification is Qt's real styleHints().colorSchemeChanged signal."""
    from PySide6.QtCore import Qt

    assert theme.resolve_mode("system", Qt.ColorScheme.Light) == "light"
    assert theme.resolve_mode("system", Qt.ColorScheme.Dark) == "dark"
    assert theme.resolve_mode("system", Qt.ColorScheme.Unknown) == "dark"
    windows = {"scheme": Qt.ColorScheme.Dark}
    monkeypatch.setattr(theme, "_system_scheme", lambda: windows["scheme"])
    hints = themed_app.styleHints()

    window.apply_theme_mode("system")
    assert theme.active_palette() == "dark"
    windows["scheme"] = Qt.ColorScheme.Light  # Windows switched to light...
    hints.colorSchemeChanged.emit(Qt.ColorScheme.Light)  # ...and Qt announces it
    assert theme.active_palette() == "light"
    assert _icon_color(window.export_button.icon()) == theme.LIGHT["text_primary"]

    window.apply_theme_mode("dark")  # an explicit choice ignores later system changes
    windows["scheme"] = Qt.ColorScheme.Light
    hints.colorSchemeChanged.emit(Qt.ColorScheme.Light)
    assert theme.active_palette() == "dark"


def test_choice_is_saved_and_restored_on_restart(qtbot, themed_app, tmp_config, tmp_path):
    from app.storage.chat_repository import SqliteChatRepository
    from app.ui.main_window import THEME_SETTING, MainWindow

    db = tmp_path / "db2" / "assistant.db"
    repo = SqliteChatRepository.open(db)
    win = MainWindow(tmp_config, store=repo, use_webengine=False, health_checks=False)
    qtbot.addWidget(win)
    win.settings_editor = lambda export_dir, timeout: (str(tmp_path / "e"), 60, False, "light")
    win.open_settings()
    assert repo.get_setting(THEME_SETTING) == "light" and theme.active_palette() == "light"
    win.close()
    repo.close()

    theme.apply_mode(themed_app, "dark")  # simulate a fresh start (the app starts dark)
    repo2 = SqliteChatRepository.open(db)
    win2 = MainWindow(tmp_config, store=repo2, use_webengine=False, health_checks=False)
    qtbot.addWidget(win2)
    assert theme.active_palette() == "light"  # restored before the window is shown
    assert not win2.isVisible()
    assert _icon_color(win2.export_button.icon()) == theme.LIGHT["text_primary"]
    win2.close()
    repo2.close()
