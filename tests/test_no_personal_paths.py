"""Release hygiene: no tracked text file may contain a real user's home path (C:\\Users\\<name>).

Generic placeholders are allowed: ``C:\\Users\\...``, ``C:\\Users\\<user>``, ``C:\\Users\\Public``,
``C:\\Users\\Default`` and ``C:\\Users\\All Users``.
"""

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
USER_PATH = re.compile(r"[A-Za-z]:[\\/]+Users[\\/]+([^\\/\s`'\"<>|*?:]+)", re.IGNORECASE)
ALLOWED_NAMES = {"...", "<user>", "<name>", "public", "default", "all users", "%username%"}


def offending_lines(text: str) -> list[str]:
    hits = []
    for line in text.splitlines():
        for match in USER_PATH.finditer(line):
            name = match.group(1).strip().lower()
            if name not in ALLOWED_NAMES and not name.startswith("<"):
                hits.append(line.strip()[:160])
    return hits


def tracked_text_files() -> list[Path]:
    try:
        out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("git is not available")
    files = []
    for name in out.decode("utf-8", "replace").split("\0"):
        path = ROOT / name
        if not name or not path.is_file() or path.resolve() == Path(__file__).resolve():
            continue  # this file holds made-up example paths on purpose
        data = path.read_bytes()
        if b"\0" in data[:8192]:
            continue  # binary (images): checked by eye, see docs/TEST_REPORT.md
        files.append(path)
    return files


def test_detector_catches_real_user_paths_and_allows_placeholders():
    assert offending_lines(r"saved to C:\Users\alice\AppData\Local\x")
    assert offending_lines("see C:/Users/bob/Desktop")
    assert not offending_lines(r"hard-coded user paths (for example `C:\Users\...`)")
    assert not offending_lines(r"C:\Users\<user>\AppData and C:\Users\Public\x")


def test_no_tracked_text_file_contains_a_user_home_path():
    problems = {}
    for path in tracked_text_files():
        hits = offending_lines(path.read_text(encoding="utf-8", errors="replace"))
        if hits:
            problems[str(path.relative_to(ROOT))] = hits[:3]
    assert not problems, f"personal paths in tracked files: {problems}"
