import sys

import pytest

from app.errors import ConfigError
from app.prompts import PROMPT_FILE_NAME, load_system_prompt, prompts_dir


def test_prompt_loads_and_is_not_empty():
    text = load_system_prompt()
    assert len(text) > 200


def test_prompt_mentions_coding_focus():
    text = load_system_prompt().lower()
    for phrase in ("software", "code", "debug", "refactor", "never claim"):
        assert phrase in text
    assert "coding assistant" in text  # redirection of off-topic requests


def test_missing_file_raises_config_error(tmp_path):
    with pytest.raises(ConfigError) as info:
        load_system_prompt(tmp_path / "nope.txt")
    assert "not found" in str(info.value)


def test_empty_file_raises_config_error(tmp_path):
    empty = tmp_path / "empty.txt"
    empty.write_text("   \n", encoding="utf-8")
    with pytest.raises(ConfigError) as info:
        load_system_prompt(empty)
    assert "empty" in str(info.value)


def test_prompts_dir_under_pyinstaller(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert prompts_dir() == tmp_path / "app" / "prompts"


def test_prompt_file_is_in_package():
    assert (prompts_dir() / PROMPT_FILE_NAME).is_file()
