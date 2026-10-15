"""Repository hygiene: no broken relative links in the docs, generated files ignored and not tracked."""

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


def test_readme_has_relative_links():
    assert _relative_links(ROOT / "README.md"), "the link check below would pass vacuously"


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: p.relative_to(ROOT).as_posix())
def test_every_relative_link_points_to_an_existing_file(doc):
    missing = [t for t in _relative_links(doc) if not (doc.parent / t).exists()]
    assert not missing, f"broken links in {doc.name}: {missing}"


def test_readme_is_clean_utf8():
    raw = (ROOT / "README.md").read_bytes()
    assert b"\x00" not in raw
    raw.decode("utf-8")


def test_gitignore_covers_generated_files():
    lines = {line.strip() for line in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()}
    for pattern in ("__pycache__/", "*.py[cod]", ".pytest_cache/", "venv/", ".venv/", "build/", "dist/",
                    "*.spec", "logs/", "*.log", "/data/", "*.db", "/*.png"):
        assert pattern in lines, pattern
    assert "!packaging/LocalAIAssistant.spec" in lines  # the real spec stays tracked
    assert (ROOT / "packaging" / "LocalAIAssistant.spec").is_file()


def test_no_compiled_python_is_tracked():
    if not (ROOT / ".git").exists():
        pytest.skip("not a git repository")
    git = shutil.which("git")
    if git is None:
        pytest.skip("git is not installed")
    tracked = subprocess.run([git, "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    bad = [f for f in tracked.splitlines() if "__pycache__/" in f or f.endswith((".pyc", ".pyo"))]
    assert not bad, f"untrack with: git rm -r --cached {' '.join(bad[:5])} ..."
