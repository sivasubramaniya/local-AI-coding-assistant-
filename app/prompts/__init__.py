"""System prompt loading."""

from __future__ import annotations

import sys
from pathlib import Path

from app.errors import ConfigError

PROMPT_FILE_NAME = "coding_system_prompt.txt"


def prompts_dir() -> Path:
    """Folder holding prompt files, in source runs and PyInstaller builds."""
    bundle_root = getattr(sys, "_MEIPASS", None)
    if getattr(sys, "frozen", False) and bundle_root:
        return Path(bundle_root) / "app" / "prompts"
    return Path(__file__).resolve().parent


def load_system_prompt(path: Path | None = None) -> str:
    """Return the coding system prompt text. Raises ConfigError if missing or empty."""
    prompt_path = path or prompts_dir() / PROMPT_FILE_NAME
    try:
        text = prompt_path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        raise ConfigError(f"System prompt file not found: '{prompt_path}'.") from None
    except OSError as exc:
        raise ConfigError(f"Cannot read system prompt file '{prompt_path}'.", detail=str(exc)) from exc
    if not text:
        raise ConfigError(f"System prompt file is empty: '{prompt_path}'.")
    return text
