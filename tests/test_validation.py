"""Path validation attack suite and project structure checks."""

import os
import sys

import pytest

from app.errors import PathValidationError
from app.validation.path_validator import PathValidator, safe_name, validate_relative_path
from app.validation.project_validator import validate_project

MALICIOUS = [
    "../evil.py",
    "..\\evil.py",
    "a/../../evil.py",
    "a\\..\\..\\evil.py",
    "src/../../../Windows/System32/x.dll",
    "..",
    ".",
    "./a.py",
    "a/./b.py",
    "/etc/passwd",
    "\\Windows\\win.ini",
    "C:\\Windows\\win.ini",
    "C:/Windows/win.ini",
    "c:evil.py",
    "D:relative.py",
    "\\\\server\\share\\x.py",
    "//server/share/x.py",
    "\\\\?\\C:\\x.py",
    "\\\\.\\PhysicalDrive0",
    "CON",
    "con.txt",
    "src/NUL.py",
    "aux.c",
    "COM1",
    "lpt9.log",
    "PRN.md",
    "CONIN$",
    "file.txt:hidden_stream",
    "what?.py",
    "star*.py",
    "pipe|name.py",
    'quote".py',
    "less<than.py",
    "trailing-dot.",
    "dir /x.py",
    "dir./x.py",
    "a//b.py",
    "a\\\\b.py",
    "nul\x00byte.py",
    "line\nbreak.py",
    "tab\there.py",
    "",
    "   ",
    "x" * 121 + ".py",
    "/".join(["d"] * 120),
]


@pytest.mark.parametrize("path", MALICIOUS)
def test_malicious_relative_paths_are_rejected(path):
    with pytest.raises(PathValidationError):
        validate_relative_path(path)


@pytest.mark.parametrize("path", MALICIOUS)
def test_validator_never_resolves_outside_root(tmp_path, path):
    with pytest.raises(PathValidationError):
        PathValidator(tmp_path).resolve(path)


def test_attack_suite_is_big_enough():
    assert len(MALICIOUS) >= 25


@pytest.mark.parametrize("path, expected", [
    ("main.py", "main.py"),
    ("src\\pkg\\mod.py", "src/pkg/mod.py"),
    ("tests/test_app.py", "tests/test_app.py"),
    (".gitignore", ".gitignore"),
    ("docs/con-tributing.md", "docs/con-tributing.md"),
    ("console.py", "console.py"),
    ("a.b.c.txt", "a.b.c.txt"),
])
def test_safe_paths_are_accepted(tmp_path, path, expected):
    assert validate_relative_path(path) == expected
    resolved = PathValidator(tmp_path).resolve(path)
    assert resolved.is_relative_to(tmp_path.resolve())


def test_overlong_absolute_path_rejected(tmp_path):
    deep = tmp_path / ("d" * 100) / ("e" * 100)
    deep.mkdir(parents=True)
    with pytest.raises(PathValidationError):
        PathValidator(deep).resolve("f" * 100 + ".py")


@pytest.mark.skipif(sys.platform != "win32", reason="junctions are Windows-only")
def test_junction_escape_is_rejected(tmp_path):
    import _winapi

    root = tmp_path / "project"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    _winapi.CreateJunction(str(outside), str(root / "link"))
    with pytest.raises(PathValidationError) as info:
        PathValidator(root).resolve("link/stolen.py")
    assert "symbolic link or junction" in info.value.message


def test_symlink_escape_is_rejected(tmp_path):
    root = tmp_path / "project"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    try:
        os.symlink(outside, root / "link", target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("creating symlinks needs Developer Mode or admin rights on this machine")
    with pytest.raises(PathValidationError):
        PathValidator(root).resolve("link/x.py")


def test_relative_of_outside_path_rejected(tmp_path):
    validator = PathValidator(tmp_path / "p")
    with pytest.raises(PathValidationError):
        validator.relative(tmp_path / "other.py")


@pytest.mark.parametrize("name, expected", [
    ("My App!", "my-app"),
    ("../../etc", "etc"),
    ("CON", "project"),
    ("", "project"),
    ("Ünïcödé Tool", "unicode-tool"),
    ("a" * 100, "a" * 60),
    ("C:\\Windows", "c-windows"),
])
def test_safe_name(name, expected):
    assert safe_name(name) == expected


# --- project validator --------------------------------------------------------------
def test_project_validator_reports_missing_empty_and_readme(tmp_path):
    (tmp_path / "app.py").write_text("print(1)\n")
    (tmp_path / "empty.py").write_text("   \n")
    report = validate_project(tmp_path, ["app.py", "empty.py", "missing.py", "../x.py"])
    assert report.missing == ["missing.py"] and report.empty == ["empty.py"] and report.unsafe == ["../x.py"]
    assert not report.has_readme and not report.ok
    assert "no README file" in report.summary()


def test_project_validator_passes(tmp_path):
    (tmp_path / "app.py").write_text("print(1)\n")
    (tmp_path / "README.md").write_text("# App\n")
    report = validate_project(tmp_path, ["app.py", "README.md"])
    assert report.ok and report.summary() == "Project check passed."


def test_project_validator_missing_root(tmp_path):
    assert not validate_project(tmp_path / "nope").ok
