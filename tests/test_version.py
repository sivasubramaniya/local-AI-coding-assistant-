"""Version 1.0.0 is shown in --check, --version and the Settings/About dialog."""

import re

import pytest

from app.__version__ import __version__
from tests.test_main import UNUSED_LOCAL_URL, _run


def test_version_format():
    assert re.fullmatch(r"\d+\.\d+\.\d+", __version__)
    assert __version__ == "1.2.1"


def test_check_and_version_flag_show_the_version(tmp_path):
    result = _run(tmp_path, "--check", LAA_OLLAMA_URL=UNUSED_LOCAL_URL)
    assert f"Version       : {__version__}" in result.stdout
    assert result.stdout.startswith(f"Local AI Assistant {__version__} - environment check")
    version = _run(tmp_path, "--version")
    assert version.returncode == 0 and version.stdout.strip() == f"Local AI Assistant {__version__}"


@pytest.mark.gui
def test_settings_dialog_shows_about(themed_app):
    from app.ui.dialogs import SettingsDialog

    dialog = SettingsDialog("C:/Exports", 60, model_name="qwen2.5-coder-14b:latest")
    text = dialog.about_label.text()
    assert f"Local AI Assistant {__version__}" in text and "qwen2.5-coder-14b:latest" in text
