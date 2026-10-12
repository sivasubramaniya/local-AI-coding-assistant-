import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog

from app.backend.status import ConnectionState
from app.ui.composer import Composer
from app.ui.dialogs import CommandApprovalDialog
from app.ui.icons import available_icons, load_icon
from app.ui.message_widgets import AssistantMessage, FileCard, file_type_label
from app.ui.preview_panel import HtmlPreview, PreviewPanel
from app.ui.sidebar import ModelStatusCard

pytestmark = pytest.mark.gui

REQUIRED_ICONS = [
    "plus", "search", "sidebar", "new-chat", "folder", "code", "copy", "export", "download",
    "regenerate", "thumbs-down", "more", "send-arrow", "stop-square", "expand", "close",
    "file", "globe", "settings", "check", "project-mode",
]


# --- icons -------------------------------------------------------------------
def test_required_icons_exist_and_load(qapp):
    names = available_icons()
    for name in REQUIRED_ICONS:
        assert name in names
        assert not load_icon(name, "#ff0000", 20).isNull()


def test_unknown_icon_raises(qapp):
    with pytest.raises(KeyError):
        load_icon("no-such-icon")


# --- composer ----------------------------------------------------------------
@pytest.fixture
def composer(qtbot, themed_app):
    widget = Composer()
    qtbot.addWidget(widget)
    widget.resize(700, 120)
    widget.show()
    return widget


def test_enter_sends(qtbot, composer):
    qtbot.keyClicks(composer.input, "hello")
    with qtbot.waitSignal(composer.sendRequested) as blocker:
        qtbot.keyClick(composer.input, Qt.Key.Key_Return)
    assert blocker.args == ["hello", False]
    assert composer.input.toPlainText() == ""


def test_shift_enter_adds_newline(qtbot, composer):
    qtbot.keyClicks(composer.input, "a")
    with qtbot.assertNotEmitted(composer.sendRequested):
        qtbot.keyClick(composer.input, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
    qtbot.keyClicks(composer.input, "b")
    assert composer.input.toPlainText() == "a\nb"


def test_empty_input_does_not_send(qtbot, composer):
    qtbot.keyClicks(composer.input, "   ")
    with qtbot.assertNotEmitted(composer.sendRequested):
        qtbot.keyClick(composer.input, Qt.Key.Key_Return)


def test_project_mode_flag(qtbot, composer):
    composer.project_chip.setChecked(True)
    qtbot.keyClicks(composer.input, "make a project")
    with qtbot.waitSignal(composer.sendRequested) as blocker:
        qtbot.mouseClick(composer.send_button, Qt.MouseButton.LeftButton)
    assert blocker.args == ["make a project", True]


def test_busy_turns_send_into_stop(qtbot, composer):
    composer.set_busy(True)
    assert composer.send_button.toolTip().startswith("Stop")
    with qtbot.waitSignal(composer.stopRequested):
        qtbot.mouseClick(composer.send_button, Qt.MouseButton.LeftButton)
    composer.set_busy(False)
    assert composer.send_button.toolTip().startswith("Send")


def test_input_grows_up_to_eight_lines(qtbot, composer):
    one_line = composer.input.height()
    composer.input.setPlainText("\n".join(["x"] * 4))
    four_lines = composer.input.height()
    composer.input.setPlainText("\n".join(["x"] * 30))
    many_lines = composer.input.height()
    assert one_line < four_lines < many_lines
    composer.input.setPlainText("\n".join(["x"] * 8))
    assert composer.input.height() == many_lines  # capped at 8 lines


def test_attachments_label(qtbot, composer):
    composer.set_attachments(["C:/tmp/a.py", "C:/tmp/b.py"])
    assert composer.attachment_label.isVisible()
    assert "a.py" in composer.attachment_label.text()


# --- messages ----------------------------------------------------------------
def test_file_card_click_emits_path(qtbot, themed_app):
    card = FileCard("site/index.html")
    qtbot.addWidget(card)
    card.show()
    with qtbot.waitSignal(card.fileOpened) as blocker:
        qtbot.mouseClick(card, Qt.MouseButton.LeftButton)
    assert blocker.args == ["site/index.html"]


def test_file_type_labels():
    assert file_type_label("a.html") == "HTML"
    assert file_type_label("b.py") == "Python"
    assert file_type_label("c.xyz") == "XYZ"


def test_assistant_message_renders_and_copies(qtbot, themed_app):
    message = AssistantMessage(status="Analyzed")
    qtbot.addWidget(message)
    message.resize(700, 400)
    message.show()
    for token in ["Use ", "`pip`", "\n\n```python\n", "x = 1\n", "```\n"]:
        message.append_token(token)
    message.finish()
    assert message.status_label.text() == "Analyzed"
    assert message.browser.code_blocks == ["x = 1"]
    assert message.actions.isVisible()
    message.browser.copy_code_block(0)
    assert themed_app.clipboard().text() == "x = 1"
    message.copy_text()
    assert "`pip`" in themed_app.clipboard().text()


# --- sidebar status card -------------------------------------------------------
def test_status_card_states(qtbot, themed_app):
    card = ModelStatusCard("qwen2.5-coder-14b:latest")
    qtbot.addWidget(card)
    assert card.name_label.text() == "qwen2.5-coder-14b"
    card.set_state(ConnectionState.DISCONNECTED)
    assert card.status_text() == "Ollama · Disconnected"
    card.set_state(ConnectionState.MODEL_MISSING)
    assert card.status_text() == "Ollama · Model missing"
    card.set_state(ConnectionState.CONNECTED)
    assert card.status_text() == "Ollama · Connected"


# --- preview panel -------------------------------------------------------------
FILES = {"index.html": "<h1>Hi</h1>", "app.py": "print('x')\n", "README.md": "# Title\n\nText"}


@pytest.fixture
def preview(qtbot, themed_app):
    panel = PreviewPanel(use_webengine=False)
    qtbot.addWidget(panel)
    panel.resize(600, 700)
    panel.show()
    panel.set_project("demo", FILES)
    return panel


def test_preview_empty_state(preview):
    assert preview.current_tab() == "empty"
    assert preview.empty_label.text() == "Select a file to preview"


def test_preview_tabs_by_file_type(preview):
    preview.open_file("app.py")
    assert preview.current_tab() == "code" and not preview.preview_tab.isEnabled()
    assert preview.code_view.toPlainText() == "print('x')\n"
    preview.open_file("README.md")
    assert preview.current_tab() == "preview"
    assert "Title" in preview.markdown_view.toPlainText()
    preview.show_tab("code")
    assert preview.current_tab() == "code"


def test_preview_dropdown_switches_files(preview):
    actions = {a.text(): a for a in preview.file_menu.actions()}
    assert set(actions) == set(FILES)
    actions["app.py"].trigger()
    assert preview.current_path() == "app.py"
    assert "app.py" in preview.file_button.text()


def test_preview_tree_toggle(preview):
    preview.open_file("app.py")
    preview.tree_toggle.setChecked(True)
    assert preview.tree.isVisible()
    preview.tree_toggle.setChecked(False)
    assert not preview.tree.isVisible()


def test_html_fallback_when_webengine_unavailable(qtbot, themed_app, monkeypatch, tmp_path):
    import app.ui.preview_panel as preview_module

    monkeypatch.setattr(preview_module, "webengine_available", lambda: False)
    monkeypatch.setattr(preview_module, "preview_temp_dir", lambda: tmp_path)
    opened = []
    monkeypatch.setattr(preview_module.QDesktopServices, "openUrl", lambda url: opened.append(url))
    widget = HtmlPreview()
    qtbot.addWidget(widget)
    assert widget.is_fallback and widget.open_button is not None
    widget.set_html("<h1>Hello</h1>", "site/page.html")
    assert "Hello" in widget.view.toPlainText()
    path = widget.open_in_browser()
    assert path == tmp_path / "page.html" and path.read_text(encoding="utf-8") == "<h1>Hello</h1>"
    assert opened and opened[0].toLocalFile().endswith("page.html")


# --- dialogs -----------------------------------------------------------------------
def test_command_approval_dialog(qtbot, themed_app):
    dialog = CommandApprovalDialog("pytest -q", "C:/projects/demo", reason="Run the tests")
    qtbot.addWidget(dialog)
    assert dialog.command_label.text() == "pytest -q"
    assert dialog.reject_button.isDefault()
    dialog.approve_button.click()
    assert dialog.result() == QDialog.DialogCode.Accepted
    dialog2 = CommandApprovalDialog("rm -rf /", "C:/")
    qtbot.addWidget(dialog2)
    dialog2.reject_button.click()
    assert dialog2.result() == QDialog.DialogCode.Rejected


def test_action_row_is_below_the_text_as_soon_as_an_answer_finishes(themed_app):
    """Regression (seen in a REAL app screenshot): the action row overlapped the last lines
    of a long streamed answer until the next event-loop pass."""
    from app.ui.chat_view import ChatView

    text = "Intro\n\n```python\n" + "x = 1\n" * 30 + "```\n\n" + "\n".join(
        f"- point {i}: " + "word " * 25 for i in range(12))
    view = ChatView()
    view.resize(1300, 850)
    view.show()
    message = view.add_assistant_message("status")
    for start in range(0, len(text), 150):
        message.append_token(text[start:start + 150])
        themed_app.processEvents()
    message.finish()  # no event processing before the check
    assert message.actions.y() >= message.browser.y() + message.browser.height()
