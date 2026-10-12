"""Export and Settings in the window (offscreen; folder pickers replaced; tmp_path only)."""

import zipfile

import pytest

from app.backend.chat_store import ChatMessage
from app.backend.ollama_client import OllamaClient
from app.storage.chat_repository import SqliteChatRepository
from app.ui.agent_widgets import ExportCard
from app.ui.main_window import COMMAND_TIMEOUT_SETTING, EXPORT_DIR_SETTING, NO_PROJECT_TO_EXPORT, MainWindow
from app.ui.message_widgets import ErrorCard
from tests.fake_ollama import FakeOllama

pytestmark = pytest.mark.gui


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "db" / "assistant.db"


@pytest.fixture
def make(qtbot, themed_app, tmp_config, db_path):
    opened = []
    fake = FakeOllama()

    def start():
        repo = SqliteChatRepository.open(db_path)
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


@pytest.fixture
def project_win(make, tmp_path):
    win = make()
    root = tmp_path / "projects" / "calc"
    root.mkdir(parents=True)
    (root / "calc.py").write_text("print(1)\n")
    (root / ".env").write_text("TOKEN=secret")
    win.store.add_message(win.current_chat_id(), ChatMessage("user", "make calc"))
    win.store.create_project("calc", str(root), win.current_chat_id(), "complete")
    return win


def _cards(win, kind):
    return [w for w in win.chat_view.items if isinstance(w, kind)]


def test_export_folder_flow(qtbot, project_win, tmp_path, tmp_config):
    win = project_win
    offered = []
    target = tmp_path / "MyExports"
    win.folder_chooser = lambda start: offered.append(start) or str(target)
    opened = []
    win.folder_opener = opened.append
    with qtbot.waitSignal(win.exportFinished, timeout=10000):
        win.export_button.click()
    assert offered == [str(tmp_config.export_dir)]  # default from config the first time
    destination = target / "calc"
    assert (destination / "calc.py").is_file() and not (destination / ".env").exists()
    assert (destination / "README.md").is_file()  # generated with instructions
    card = _cards(win, ExportCard)[-1]
    assert str(destination) in card.path_label.text()
    card.open_button.click()
    assert opened == [str(destination)]
    assert win.store.get_setting(EXPORT_DIR_SETTING) == str(target)


def test_export_zip_flow_remembers_folder(qtbot, project_win, tmp_path):
    win = project_win
    target = tmp_path / "zips"
    offered = []
    win.folder_chooser = lambda start: offered.append(start) or str(target)
    for _ in range(2):
        with qtbot.waitSignal(win.exportFinished, timeout=10000):
            win.export_zip_action.trigger()
    assert offered[1] == str(target)  # the chosen folder is remembered
    assert (target / "calc.zip").is_file() and (target / "calc-2.zip").is_file()
    with zipfile.ZipFile(target / "calc.zip") as archive:
        assert archive.testzip() is None and "calc/calc.py" in archive.namelist()
    assert "ZIP archive created and verified" in _cards(win, ExportCard)[-1].title_label.text()


def test_cancelled_folder_choice_does_nothing(project_win, tmp_path):
    project_win.folder_chooser = lambda start: None
    assert project_win.export_project() is False
    assert _cards(project_win, ExportCard) == []


def test_export_failure_shows_error_and_app_continues(qtbot, project_win, tmp_path):
    blocker = tmp_path / "not-a-folder"
    blocker.write_text("x")
    project_win.folder_chooser = lambda start: str(blocker)
    with qtbot.waitSignal(project_win.exportFinished, timeout=10000):
        project_win.export_project()
    assert "Export failed" in _cards(project_win, ErrorCard)[-1].label.text()
    project_win.folder_chooser = lambda start: str(tmp_path / "ok")
    with qtbot.waitSignal(project_win.exportFinished, timeout=10000):
        project_win.export_project()
    assert (tmp_path / "ok" / "calc" / "calc.py").is_file()


def test_no_project_to_export(make):
    win = make()
    win.folder_chooser = lambda start: pytest.fail("must not ask for a folder")
    assert win.export_project() is False
    assert win.toast.text() == NO_PROJECT_TO_EXPORT


def test_settings_are_saved_and_loaded_on_restart(make, tmp_path):
    win = make()
    seen = []
    win.settings_editor = lambda export_dir, timeout: seen.append((export_dir, timeout)) or (str(tmp_path / "e"), 90)
    win.sidebar.settings_button.click()
    assert seen and seen[0][1] == 60.0
    assert win.config.command_timeout_s == 90
    assert win.store.get_setting(COMMAND_TIMEOUT_SETTING) == "90"
    win.close()
    win.store.close()
    win2 = make()
    assert win2.config.command_timeout_s == 90.0 and win2.export_dir() == str(tmp_path / "e")


def test_settings_dialog_values(themed_app):
    from app.ui.dialogs import SettingsDialog

    dialog = SettingsDialog("C:/Exports", 45)
    assert dialog.values() == ("C:/Exports", 45)
    dialog.timeout_spin.setValue(5000)
    assert dialog.values()[1] == 3600  # clamped to the allowed range
    assert not dialog.theme_combo.model().item(1).isEnabled()
