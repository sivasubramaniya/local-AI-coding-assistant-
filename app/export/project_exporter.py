"""Export a project to a folder or a verified ZIP archive.

- The destination is ``<export_dir>/<project-name>`` (``-2``, ``-3``… if it exists); nothing
  is ever overwritten. ZIPs are named the same way.
- Caches, virtual environments, build output, backups, ``.git`` (unless asked for), and
  secret-like files (``.env``, keys, credentials) are left out.
- README.md in the export always has build/run/test instructions (added to the exported
  copy when missing; the original project is not changed).
- A ZIP is reported as created only after it has been reopened, checked with
  ``testzip()``, its file list and sizes compared, and extracted to a temporary folder.
"""

from __future__ import annotations

import fnmatch
import logging
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from app.agent.tool_runner import default_test_commands
from app.errors import ExportError, PathValidationError
from app.validation.path_validator import PathValidator, safe_name, validate_relative_path

logger = logging.getLogger(__name__)

EXCLUDED_DIRS = {"venv", ".venv", "env", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
                 "node_modules", "build", "dist", "out", "target", ".idea", ".vscode", ".git"}
EXCLUDED_FILES = ["*.pyc", "*.pyo", "*.class", "*.bak-*", ".env", ".env.*", "*.pem", "*.key", "*.p12", "*.pfx",
                  "*.keystore", "*.jks", "id_rsa*", "id_ed25519*", "credentials*", "secrets.*", "secret.*",
                  "*.kdbx", ".npmrc", ".pypirc", ".netrc", "*.sqlite", "*.db", "Thumbs.db", ".DS_Store"]
INSTRUCTION_WORDS = ("run", "test")


@dataclass
class ExportResult:
    destination: Path
    files: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    readme_added: bool = False
    verified: bool = False


def _excluded(relative: Path, include_git: bool) -> bool:
    dirs = set(relative.parts[:-1])
    blocked = EXCLUDED_DIRS - ({".git"} if include_git else set())
    if dirs & blocked:
        return True
    name = relative.name
    if name in blocked:
        return True
    return any(fnmatch.fnmatch(name.lower(), pattern.lower()) for pattern in EXCLUDED_FILES)


def collect_files(root: Path, include_git: bool = False) -> tuple[list[str], list[str]]:
    """(included, skipped) relative POSIX paths. Symlinks are never followed."""
    root = Path(root)
    if not root.is_dir():
        raise ExportError(f"The project folder does not exist: {root}")
    included: list[str] = []
    skipped: list[str] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if path.is_symlink() or path.is_junction():
            skipped.append(relative.as_posix())
            continue
        if not path.is_file():
            continue
        if _excluded(relative, include_git):
            skipped.append(relative.as_posix())
            continue
        try:
            validate_relative_path(relative.as_posix())
        except PathValidationError:
            skipped.append(relative.as_posix())
            continue
        included.append(relative.as_posix())
    return included, skipped


def instructions_section(root: Path, name: str) -> str:
    """Build/run/test instructions judged from the project's files."""
    commands = default_test_commands(root) or []
    lines = ["## Build, run and test", ""]
    if any(c[0] == "javac" for c in commands):
        lines += ["Requires a JDK (for example Microsoft OpenJDK 21).", "", "```powershell",
                  " ".join(commands[0]), *(" ".join(c) for c in commands[1:]), "```", "",
                  "Run the app with `java -cp out <MainClass>`."]
    elif any(root.rglob("*.py")):
        lines += ["Requires Python 3.10 or newer.", "", "```powershell", "python -m venv venv",
                  ".\\venv\\Scripts\\Activate.ps1"]
        if (root / "requirements.txt").is_file():
            lines.append("pip install -r requirements.txt")
        mains = [p for p in ("main.py", "app.py", f"{name}.py") if (root / p).is_file()]
        lines.append(f"python {mains[0]}" if mains else "python <main script>.py")
        if commands:
            lines.append(" ".join(commands[0]))
        lines.append("```")
    elif (root / "index.html").is_file():
        lines += ["Open `index.html` in a web browser. No build step is needed."]
    else:
        lines += ["See the source files for how to build and run this project."]
    return "\n".join(lines) + "\n"


def _readme_text(root: Path, name: str) -> tuple[str | None, bool]:
    """(content to write for README.md, whether instructions were added). None = copy as-is."""
    readme = root / "README.md"
    if not readme.is_file():
        return f"# {name}\n\n{instructions_section(root, name)}", True
    text = readme.read_text(encoding="utf-8", errors="replace")
    lower = text.lower()
    if all(word in lower for word in INSTRUCTION_WORDS):
        return None, False
    return text.rstrip("\n") + "\n\n" + instructions_section(root, name), True


def unique_path(parent: Path, stem: str, suffix: str = "") -> Path:
    candidate = parent / f"{stem}{suffix}"
    counter = 2
    while candidate.exists():
        candidate = parent / f"{stem}-{counter}{suffix}"
        counter += 1
    return candidate


def _prepare_export_dir(export_dir: Path) -> Path:
    export_dir = Path(export_dir)
    try:
        export_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ExportError(f"Cannot use the export folder '{export_dir}'.", detail=str(exc)) from None
    if not export_dir.is_dir():
        raise ExportError(f"The export location is not a folder: '{export_dir}'.")
    return export_dir


def export_folder(root: Path, export_dir: Path, name: str, include_git: bool = False) -> ExportResult:
    """Copy the project into a new folder under ``export_dir``."""
    root = Path(root)
    export_dir = _prepare_export_dir(export_dir)
    included, skipped = collect_files(root, include_git)
    readme, added = _readme_text(root, name)
    destination = unique_path(export_dir, safe_name(name))
    try:
        destination.mkdir()
        validator = PathValidator(destination)
        for relative in included:
            target = validator.resolve(relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            if relative == "README.md" and readme is not None:
                target.write_text(readme, encoding="utf-8", newline="\n")
            else:
                shutil.copy2(root / relative, target)
        if readme is not None and "README.md" not in included:
            (destination / "README.md").write_text(readme, encoding="utf-8", newline="\n")
            included.append("README.md")
    except (OSError, PathValidationError) as exc:
        shutil.rmtree(destination, ignore_errors=True)  # only the folder this export just created
        raise ExportError(f"The project could not be exported to '{destination}'.", detail=str(exc)) from None
    result = ExportResult(destination, included, skipped, added)
    verify_folder(root, destination, included, readme)
    result.verified = True
    logger.info("Exported %d files to %s (%d skipped)", len(included), destination, len(skipped))
    return result


def verify_folder(root: Path, destination: Path, files: list[str], readme: str | None) -> None:
    for relative in files:
        target = destination / relative
        if not target.is_file():
            raise ExportError(f"Export check failed: '{relative}' is missing in '{destination}'.")
        if relative == "README.md" and readme is not None:
            continue
        if target.stat().st_size != (root / relative).stat().st_size:
            raise ExportError(f"Export check failed: '{relative}' has the wrong size.")


def export_zip(root: Path, export_dir: Path, name: str, include_git: bool = False) -> ExportResult:
    """Write ``<export_dir>/<name>.zip`` (ZIP_DEFLATED) and verify it before reporting success."""
    root = Path(root)
    export_dir = _prepare_export_dir(export_dir)
    included, skipped = collect_files(root, include_git)
    readme, added = _readme_text(root, name)
    folder = safe_name(name)
    zip_path = unique_path(export_dir, folder, ".zip")
    expected: dict[str, bytes | int] = {}
    try:
        with zipfile.ZipFile(zip_path, "x", compression=zipfile.ZIP_DEFLATED) as archive:
            for relative in included:
                arcname = f"{folder}/{relative}"
                if relative == "README.md" and readme is not None:
                    data = readme.encode("utf-8")
                    archive.writestr(arcname, data)
                    expected[arcname] = len(data)
                else:
                    archive.write(root / relative, arcname)
                    expected[arcname] = (root / relative).stat().st_size
            if readme is not None and "README.md" not in included:
                data = readme.encode("utf-8")
                archive.writestr(f"{folder}/README.md", data)
                expected[f"{folder}/README.md"] = len(data)
                included.append("README.md")
    except OSError as exc:
        zip_path.unlink(missing_ok=True)
        raise ExportError(f"The ZIP archive could not be written: '{zip_path}'.", detail=str(exc)) from None
    try:
        verify_zip(zip_path, {k: int(v) for k, v in expected.items()})
    except ExportError:
        zip_path.unlink(missing_ok=True)  # never leave an archive that failed its check
        raise
    logger.info("ZIP %s created and verified (%d files)", zip_path, len(included))
    return ExportResult(zip_path, included, skipped, added, verified=True)


def verify_zip(zip_path: Path, expected_sizes: dict[str, int]) -> None:
    """Reopen, testzip(), compare names and sizes, and extract to a temp folder."""
    try:
        with zipfile.ZipFile(zip_path) as archive:
            bad = archive.testzip()
            if bad is not None:
                raise ExportError(f"ZIP check failed: '{bad}' is damaged.")
            infos = {i.filename: i.file_size for i in archive.infolist() if not i.is_dir()}
            if set(infos) != set(expected_sizes):
                missing = sorted(set(expected_sizes) - set(infos))
                extra = sorted(set(infos) - set(expected_sizes))
                raise ExportError("ZIP check failed: the file list does not match.",
                                  detail=f"missing={missing[:5]} extra={extra[:5]}")
            wrong = [n for n, size in expected_sizes.items() if infos[n] != size]
            if wrong:
                raise ExportError("ZIP check failed: some file sizes do not match.", detail=", ".join(wrong[:5]))
            with tempfile.TemporaryDirectory(prefix="laa-zipcheck-") as tmp:
                for info in archive.infolist():
                    validate_relative_path(info.filename.rstrip("/"))  # no traversal inside our own archive
                archive.extractall(tmp)
                for name, size in expected_sizes.items():
                    extracted = Path(tmp) / name
                    if not extracted.is_file() or extracted.stat().st_size != size:
                        raise ExportError(f"ZIP check failed: '{name}' did not extract correctly.")
    except (zipfile.BadZipFile, OSError, PathValidationError) as exc:
        raise ExportError("ZIP check failed: the archive cannot be read.", detail=str(exc)) from None
