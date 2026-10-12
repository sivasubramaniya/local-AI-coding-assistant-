import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QInputDialog, QMessageBox

from app.ui import demo
from app.ui.main_window import NO_PROJECT_TO_EXPORT, MainWindow
from app.ui.message_widgets import AssistantMessage, UserBubble

pytestmark = pytest.mark.gui


@pytest.fixture
def window(qtbot, themed_app, tmp_config):
    win = MainWindow(tmp_config, token_delay_s=0.005, use_webengine=False, demo_mode=True, health_checks=False)
    qtbot.addWidget(win)
    win.resize(1400, 850)
    win.show()
    qtbot.waitExposed(win)
    return win


def test_window_basics(window):
    assert window.windowTitle() == "Local AI Assistant"
    assert window.minimumWidth() == 1100 and window.minimumHeight() == 700
    assert not window.is_preview_open()


def test_status_card_shows_disconnected_stub(window):
    assert window.sidebar.status_card.status_text() == "Ollama · Disconnected"


def test_sidebar_collapse_and_expand(qtbot, window):
    sidebar = window.sidebar
    assert sidebar.width() == 300
    qtbot.mouseClick(sidebar.collapse_button, Qt.MouseButton.LeftButton)
    assert sidebar.is_collapsed() and sidebar.width() == 64
    assert not sidebar.chat_list.isVisible()
    sidebar.toggle_collapsed()
    assert not sidebar.is_collapsed() and sidebar.width() == 300
    assert sidebar.chat_list.isVisible()


def test_send_streams_into_assistant_message(qtbot, window):
    window.new_chat()
    with qtbot.waitSignal(window.streamFinished, timeout=15000):
        assert window.submit_prompt("write hello world")
        assert window.composer.is_busy()
        assert window.composer.send_button.toolTip().startswith("Stop")
    items = window.chat_view.items
    assert isinstance(items[0], UserBubble) and items[0].text() == "write hello world"
    assistant = items[1]
    assert isinstance(assistant, AssistantMessage)
    assert assistant.text() == demo.DEMO_ANSWER
    assert [c.path for c in assistant.file_cards] == demo.DEMO_ANSWER_FILES
    assert not window.composer.is_busy()
    chat = window.store.get_chat(window.current_chat_id())
    assert [m.role for m in window.store.get_messages(chat.id)] == ["user", "assistant"]
    assert chat.title == "Write hello world"


def test_stop_cancels_and_restores_send(qtbot, window):
    window.token_delay_s = 0.05
    window.new_chat()
    window.submit_prompt("long answer please")
    qtbot.wait(150)
    assert window.is_busy()
    window.stop_generation()
    assert not window.is_busy()
    assert window.composer.send_button.toolTip().startswith("Send")
    assistant = window.chat_view.items[-1]
    assert assistant.status_label.text() == "(stopped)"
    assert len(assistant.text()) < len(demo.DEMO_ANSWER)


def test_ui_responsive_during_stream(qtbot, window):
    ticks = []
    timer = QTimer()
    timer.timeout.connect(lambda: ticks.append(1))
    timer.start(10)
    window.new_chat()
    with qtbot.waitSignal(window.streamFinished, timeout=15000):
        window.submit_prompt("go")
    timer.stop()
    assert len(ticks) >= 10


def test_file_card_opens_preview_and_close_hides(qtbot, window):
    window.new_chat()
    with qtbot.waitSignal(window.streamFinished, timeout=15000):
        window.submit_prompt("make a page")
    card = window.chat_view.items[-1].file_cards[0]
    card.fileOpened.emit(card.path)
    assert window.is_preview_open()
    assert window.preview.current_path() == "welcome.html"
    assert window.preview.html_preview.is_fallback
    window.preview.close_button.click()
    assert not window.is_preview_open()


def test_preview_dropdown_switches_file(window):
    window.open_file("welcome.html")
    actions = {a.text(): a for a in window.preview.file_menu.actions()}
    actions["server.py"].trigger()
    assert window.preview.current_path() == "server.py"
    assert window.preview.current_tab() == "code"


def test_preview_expand_hides_chat(window):
    window.open_file("README.md")
    window.preview.expand_button.setChecked(True)
    assert window.chat_panel.isHidden() and window.sidebar.isHidden()
    window.preview.expand_button.setChecked(False)
    assert not window.chat_panel.isHidden()


def test_top_bar_toggle_and_export_toast(window):
    window.files_button.click()
    assert window.is_preview_open()
    window.files_button.click()
    assert not window.is_preview_open()
    window.export_button.click()
    assert window.toast.isVisible() and window.toast.text() == NO_PROJECT_TO_EXPORT


def test_new_chat_rename_delete(window, monkeypatch):
    before = len(window.sidebar.chat_ids())
    chat_id = window.new_chat()
    assert window.sidebar.chat_ids()[0] == chat_id
    assert len(window.sidebar.chat_ids()) == before + 1
    assert window.sidebar.chat_titles()[0] == "New chat"

    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: ("Renamed chat", True))
    window.sidebar.renameRequested.emit(chat_id)
    assert window.store.get_chat(chat_id).title == "Renamed chat"
    assert "Renamed chat" in window.sidebar.chat_titles()

    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    window.sidebar.deleteRequested.emit(chat_id)
    assert not window.store.chat_exists(chat_id)
    assert chat_id not in window.sidebar.chat_ids()
    assert window.current_chat_id() is not None


def test_delete_cancelled_keeps_chat(window, monkeypatch):
    chat_id = window.new_chat()
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No)
    window.sidebar.deleteRequested.emit(chat_id)
    assert window.store.chat_exists(chat_id)


def test_switching_chats_swaps_messages(window):
    welcome_id = next(c.id for c in window.store.list_chats() if c.title == demo.WELCOME_CHAT_TITLE)
    window.select_chat(welcome_id)
    assert window.chat_view.items[0].text() == demo.WELCOME_PROMPT
    other_id = next(c.id for c in window.store.list_chats() if c.title == "Flask login bug")
    window.select_chat(other_id)
    assert "flask login bug" in window.chat_view.items[0].text()
    assert window.sidebar.current_chat_id() == other_id


def test_search_filters_recents(window):
    window.sidebar.toggle_search()
    window.sidebar.search_field.setText("flask")
    assert window.sidebar.chat_proxy.rowCount() == 1
    window.sidebar.search_field.clear()
    assert window.sidebar.chat_proxy.rowCount() == len(window.store.list_chats())


def test_close_while_streaming_does_not_crash(qtbot, window):
    window.token_delay_s = 0.05
    window.new_chat()
    window.submit_prompt("stream then close")
    qtbot.wait(100)
    assert window.is_busy()
    window.close()
    assert not window.is_busy()
