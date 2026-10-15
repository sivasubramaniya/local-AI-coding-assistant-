"""Repository hygiene: relative doc links resolve, README is clean UTF-8, generated files are ignored
and no compiled Python is tracked."""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
LINK = re.compile(r"\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")  # [text](target) and ![alt](target "title")
EXTERNAL = ("http://", "https://", "mailto:")
DOCS = [ROOT / "README.md", ROOT / "CHANGELOG.md", *sorted((ROOT / "docs").rglob("*.md"))]


def _relative_links(path: Path) -> list[str]:
    targets = LINK.findall(path.read_text(encoding="utf-8"))
    return [t.split("#", 1)[0] for t in targets if not t.startswith(EXTERNAL) and not t.startswith("#")]


def _git() -> str:
    git = shutil.which("git")
    if git is None or not (ROOT / ".git").exists():
        pytest.skip("not a git checkout")
    return git


def test_readme_has_relative_links():
    assert _relative_links(ROOT / "README.md"), "the link check below would pass vacuously"


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: p.relative_to(ROOT).as_posix())
def test_every_relative_link_points_to_an_existing_file(doc):
    missing = [t for t in _relative_links(doc) if t and not (doc.parent / t).exists()]
    assert not missing, f"broken links in {doc.name}: {missing}"


def test_readme_is_clean_utf8():
    raw = (ROOT / "README.md").read_bytes()
    assert b"\x00" not in raw  # a PowerShell UTF-16 append once made it binary
    raw.decode("utf-8")


def test_generated_files_are_ignored():
    git = _git()
    generated = ["app/__pycache__/theme.cpython-312.pyc", "x.pyc", ".pytest_cache/v/cache", "venv/pyvenv.cfg",
                 "build/LocalAIAssistant/x", "dist/LocalAIAssistant/x.exe", "logs/app.log", "app.log",
                 "assistant.db", "data/assistant.db"]
    result = subprocess.run([git, "check-ignore", "--no-index", *generated], cwd=ROOT, capture_output=True, text=True)
    ignored = set(result.stdout.split())
    assert ignored == set(generated), f"not ignored: {sorted(set(generated) - ignored)}"
    kept = subprocess.run([git, "check-ignore", "--no-index", "packaging/LocalAIAssistant.spec", "data/.gitkeep"],
                          cwd=ROOT, capture_output=True, text=True)
    assert kept.stdout.strip() == ""  # the real spec and the data placeholder stay tracked


def test_no_compiled_python_is_tracked():
    git = _git()
    tracked = subprocess.run([git, "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    bad = [f for f in tracked.splitlines() if "__pycache__/" in f or f.endswith((".pyc", ".pyo"))]
    assert not bad, f"compiled files are tracked: {bad[:5]}"
