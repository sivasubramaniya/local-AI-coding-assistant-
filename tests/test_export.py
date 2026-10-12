"""Project export: exclusions, name collisions, README instructions, verified ZIPs, failures."""

import zipfile

import pytest

from app.errors import ExportError
from app.export import project_exporter
from app.export.project_exporter import collect_files, export_folder, export_zip, verify_zip


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "src" / "calc"
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    (root / "test_calc.py").write_text("from pkg.calc import add\n\ndef test_add():\n    assert add(1, 2) == 3\n")
    (root / "README.md").write_text("# Calc\n\nA calculator.\n", encoding="utf-8")
    for junk in ("venv/Lib/site.py", ".venv/x.py", "__pycache__/calc.cpython-312.pyc", ".pytest_cache/v/x",
                 "node_modules/a/index.js", "build/lib.txt", "dist/app.exe", ".git/config", "out/Calc.class"):
        path = root / junk
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("junk")
    for secret in (".env", ".env.local", "server.pem", "private.key", "id_rsa", "credentials.json",
                   "secrets.yaml", "pkg/calc.py.bak-20260101-000000", "pkg/calc.pyc", "data.db"):
        (root / secret).write_text("secret")
    return root


INCLUDED = {"README.md", "pkg/calc.py", "test_calc.py"}


def test_collect_files_exclusions(project):
    included, skipped = collect_files(project)
    assert set(included) == INCLUDED
    for name in (".env", ".env.local", "server.pem", "private.key", "id_rsa", "credentials.json", "secrets.yaml",
                 "pkg/calc.py.bak-20260101-000000", "pkg/calc.pyc", "data.db", "venv/Lib/site.py", ".git/config"):
        assert name in skipped, name


def test_git_folder_is_optional(project):
    included, _ = collect_files(project, include_git=True)
    assert ".git/config" in included


def test_export_folder_and_collisions(project, tmp_path):
    out = tmp_path / "Desktop"
    first = export_folder(project, out, "calc")
    second = export_folder(project, out, "calc")
    assert first.destination == out / "calc" and second.destination == out / "calc-2"
    assert first.verified
    exported = {p.relative_to(first.destination).as_posix() for p in first.destination.rglob("*") if p.is_file()}
    assert exported == INCLUDED
    assert (first.destination / "pkg" / "calc.py").read_text() == (project / "pkg" / "calc.py").read_text()


def test_readme_gets_instructions_without_changing_the_original(project, tmp_path):
    result = export_folder(project, tmp_path / "out", "calc")
    readme = (result.destination / "README.md").read_text()
    assert result.readme_added
    assert "A calculator." in readme and "## Build, run and test" in readme and "python -m pytest -q" in readme
    assert (project / "README.md").read_text() == "# Calc\n\nA calculator.\n"


def test_missing_readme_is_generated(project, tmp_path):
    (project / "README.md").unlink()
    result = export_folder(project, tmp_path / "out", "calc")
    assert "README.md" in result.files and (result.destination / "README.md").read_text().startswith("# calc")


def test_complete_readme_is_copied_as_is(project, tmp_path):
    (project / "README.md").write_text("# Calc\n\nRun: python -m calc\nTest: pytest\n")
    result = export_folder(project, tmp_path / "out", "calc")
    assert not result.readme_added
    assert (result.destination / "README.md").read_text() == "# Calc\n\nRun: python -m calc\nTest: pytest\n"


def test_java_readme_instructions(tmp_path):
    root = tmp_path / "j"
    (root / "src").mkdir(parents=True)
    (root / "src" / "AppTest.java").write_text("class AppTest { public static void main(String[] a) {} }")
    result = export_folder(root, tmp_path / "out", "j")
    readme = (result.destination / "README.md").read_text()
    assert "javac -encoding UTF-8 -d out src/AppTest.java" in readme and "java -cp out AppTest" in readme


def test_zip_is_created_and_verified(project, tmp_path):
    out = tmp_path / "out"
    result = export_zip(project, out, "calc")
    again = export_zip(project, out, "calc")
    assert result.destination == out / "calc.zip" and again.destination == out / "calc-2.zip"
    assert result.verified
    with zipfile.ZipFile(result.destination) as archive:
        names = {n for n in archive.namelist()}
        assert names == {f"calc/{p}" for p in INCLUDED}
        assert all(i.compress_type == zipfile.ZIP_DEFLATED for i in archive.infolist())


def test_zip_verification_catches_a_damaged_archive(project, tmp_path):
    result = export_zip(project, tmp_path / "out", "calc")
    expected = {f"calc/{p}": 1 for p in INCLUDED}  # wrong sizes
    with pytest.raises(ExportError) as info:
        verify_zip(result.destination, expected)
    assert "sizes do not match" in info.value.message
    with pytest.raises(ExportError):
        verify_zip(result.destination, {"calc/other.py": 3})
    broken = tmp_path / "broken.zip"
    broken.write_bytes(b"PK\x03\x04 not really a zip")
    with pytest.raises(ExportError):
        verify_zip(broken, {})


def test_failed_zip_check_removes_the_archive(project, tmp_path, monkeypatch):
    def failing_verify(path, expected):
        raise ExportError("ZIP check failed: injected")

    monkeypatch.setattr(project_exporter, "verify_zip", failing_verify)
    with pytest.raises(ExportError):
        export_zip(project, tmp_path / "out", "calc")
    assert not (tmp_path / "out" / "calc.zip").exists()


def test_export_failures_are_reported(project, tmp_path):
    not_a_folder = tmp_path / "file.txt"
    not_a_folder.write_text("x")
    with pytest.raises(ExportError):
        export_folder(project, not_a_folder, "calc")
    with pytest.raises(ExportError):
        export_zip(tmp_path / "missing", tmp_path / "out", "calc")


def test_failed_copy_cleans_up_only_its_own_folder(project, tmp_path, monkeypatch):
    import shutil

    out = tmp_path / "out"
    (out / "keep").mkdir(parents=True)

    def broken_copy(*a, **k):
        raise OSError("disk full (injected)")

    monkeypatch.setattr(shutil, "copy2", broken_copy)
    with pytest.raises(ExportError) as info:
        export_folder(project, out, "calc")
    assert "disk full" in (info.value.detail or "")
    assert not (out / "calc").exists() and (out / "keep").is_dir()
