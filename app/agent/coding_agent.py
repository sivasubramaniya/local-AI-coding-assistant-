"""Debug/refactor support for chats linked to a project, and safe file edits.

- ``build_context`` adds the relevant project files (and attachments) to the request.
- ``parse_changes`` reads file changes from the model's answer: full files in fenced
  blocks whose info string has ``path=<relative path>``, or unified diffs in ```diff blocks.
- ``prepare_changes`` turns them into ``PendingChange`` objects with a diff preview.
  Nothing is written until ``apply_changes`` is called after the user confirms.
- ``apply_changes`` backs up each existing file as ``<file>.bak-<timestamp>`` inside the
  project and writes through the path validator. Model text is never executed.
"""

from __future__ import annotations

import difflib
import logging
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from app.agent.project_generator import backup_name, fenced_blocks
from app.backend.task_classifier import TaskType
from app.errors import AppError, PatchError, PathValidationError
from app.validation.path_validator import PathValidator, validate_relative_path

logger = logging.getLogger(__name__)

MAX_FILE_BYTES = 200_000
MAX_LISTED_FILES = 300
SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", "venv", ".venv", "node_modules", "build", "dist", ".idea",
             ".vscode"}
BINARY_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip", ".exe", ".dll", ".pyc", ".class",
                   ".jar", ".db", ".sqlite", ".bin", ".so", ".woff", ".woff2", ".ttf"}

EDIT_INSTRUCTIONS = """When you change files of this project, give each changed or new file IN FULL in its own fenced
code block whose info string is the language followed by path=<relative path>, for example:
```python path=src/app.py
<whole file>
```
Alternatively give a unified diff in a ```diff block with '--- a/<path>' and '+++ b/<path>' headers.
Only change what is needed. Do not claim you ran anything."""

CONTEXT_TASKS = {TaskType.DEBUG, TaskType.REFACTOR, TaskType.REVIEW, TaskType.EXPLAIN, TaskType.GENERATE}


@dataclass(frozen=True)
class FileChange:
    path: str
    content: str | None = None  # full new content
    diff: str | None = None  # or a unified diff for one file


@dataclass(frozen=True)
class PendingChange:
    path: str
    old: str | None  # None for a new file
    new: str

    @property
    def is_new(self) -> bool:
        return self.old is None

    def diff_text(self) -> str:
        old_lines = (self.old or "").splitlines(keepends=True)
        new_lines = self.new.splitlines(keepends=True)
        before = "/dev/null" if self.is_new else f"a/{self.path}"
        return "".join(difflib.unified_diff(old_lines, new_lines, before, f"b/{self.path}"))


def _is_text_file(path: Path) -> bool:
    if path.suffix.lower() in BINARY_SUFFIXES or ".bak-" in path.name:
        return False
    try:
        return path.stat().st_size <= MAX_FILE_BYTES and b"\0" not in path.read_bytes()[:4096]
    except OSError:
        return False


def list_project_files(root: Path) -> list[str]:
    """Relative text files of a project (skips caches, venvs, backups and binaries)."""
    root = Path(root)
    found: list[str] = []
    if not root.is_dir():
        return found
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if any(part in SKIP_DIRS for part in relative.parts[:-1]) or not path.is_file() or path.is_symlink():
            continue
        if _is_text_file(path):
            found.append(relative.as_posix())
        if len(found) >= MAX_LISTED_FILES:
            break
    return found


def read_project_files(root: Path, max_total_chars: int = 2_000_000) -> dict[str, str]:
    """Text files of a project, stopping once ``max_total_chars`` have been read."""
    files: dict[str, str] = {}
    used = 0
    for relative in list_project_files(root):
        try:
            text = (Path(root) / relative).read_text(encoding="utf-8", errors="replace")
        except OSError:
            logger.warning("Could not read %s", relative)
            continue
        if used + len(text) > max_total_chars:
            break
        files[relative] = text
        used += len(text)
    return files


def read_attachments(paths: list[str], max_chars: int) -> list[tuple[str, str]]:
    """(name, text) for readable text attachments, within ``max_chars`` in total."""
    out: list[tuple[str, str]] = []
    used = 0
    for raw in paths:
        path = Path(raw)
        if not path.is_file() or not _is_text_file(path):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if used + len(text) > max_chars:
            break
        out.append((path.name, text))
        used += len(text)
    return out


def _mentioned_first(files: dict[str, str], text: str) -> list[str]:
    lower = text.lower()

    def score(path: str) -> tuple[int, int]:
        name = Path(path).name.lower()
        mentioned = path.lower() in lower or name in lower or Path(path).stem.lower() in re.findall(r"\w+", lower)
        return (0 if mentioned else 1, len(files[path]))

    return sorted(files, key=score)


def build_context(
    user_text: str,
    project_name: str | None,
    project_files: dict[str, str],
    attachments: list[tuple[str, str]],
    max_chars: int,
) -> str:
    """Extra request text: attachments, then project files (mentioned files first) within budget."""
    parts: list[str] = []
    used = 0
    for name, text in attachments:
        block = f"Attached file {name}:\n```\n{text}\n```"
        if used + len(block) > max_chars:
            break
        parts.append(block)
        used += len(block)
    if project_name is not None:
        listing = "\n".join(f"- {p}" for p in project_files)
        header = f"This chat is about the project '{project_name}'. Its files:\n{listing}"
        parts.append(header)
        used += len(header)
        omitted = []
        for path in _mentioned_first(project_files, user_text):
            block = f"File {path}:\n```\n{project_files[path]}\n```"
            if used + len(block) > max_chars:
                omitted.append(path)
                continue
            parts.append(block)
            used += len(block)
        if omitted:
            parts.append("Not shown (too large for the context): " + ", ".join(omitted))
        parts.append(EDIT_INSTRUCTIONS)
    return "\n\n".join(parts)


# --- parsing changes ---------------------------------------------------------------
_PATH_INFO = re.compile(r"(?:^|\s)(?:path|file|filename|title)=[\"']?([^\s\"']+)[\"']?", re.IGNORECASE)
_DIFF_HEADER = re.compile(r"^\+\+\+ (?:b/)?(\S+)", re.MULTILINE)


def parse_changes(answer: str) -> list[FileChange]:
    """File changes proposed in an answer (later blocks for the same path win)."""
    blocks, _unclosed = fenced_blocks(answer)
    changes: dict[str, FileChange] = {}
    for block in blocks:
        info = block.info
        match = _PATH_INFO.search(info)
        if match:
            try:
                path = validate_relative_path(match.group(1))
            except PathValidationError as exc:
                logger.warning("Ignoring change with unsafe path: %s", exc.message)
                continue
            changes[path] = FileChange(path, content=block.content.rstrip("\n") + "\n")
        elif info.split()[:1] in (["diff"], ["patch"]):
            for path, diff in _split_diff(block.content):
                changes[path] = FileChange(path, diff=diff)
    return list(changes.values())


def _split_diff(text: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    starts = [m.start() for m in re.finditer(r"^--- ", text, re.MULTILINE)]
    for i, start in enumerate(starts):
        chunk = text[start: starts[i + 1] if i + 1 < len(starts) else len(text)]
        header = _DIFF_HEADER.search(chunk)
        if not header:
            continue
        try:
            out.append((validate_relative_path(header.group(1)), chunk))
        except PathValidationError as exc:
            logger.warning("Ignoring diff with unsafe path: %s", exc.message)
    return out


_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def apply_unified_diff(original: str, diff: str) -> str:
    """Apply a single-file unified diff. Context must match exactly, else PatchError."""
    old_lines = original.splitlines()
    result: list[str] = []
    position = 0
    lines = diff.splitlines()
    i = 0
    hunks = 0
    while i < len(lines):
        match = _HUNK.match(lines[i])
        if not match:
            i += 1
            continue
        hunks += 1
        start = max(int(match.group(1)) - 1, 0)
        if int(match.group(2) or "1") == 0:
            start = int(match.group(1))  # pure insertion after line N
        if start < position:
            raise PatchError("The suggested change has overlapping parts.")
        result.extend(old_lines[position:start])
        position = start
        i += 1
        while i < len(lines) and not lines[i].startswith("@@"):
            line = lines[i]
            if line.startswith("\\"):
                i += 1
                continue
            tag, body = (line[:1], line[1:]) if line else (" ", "")
            if tag in (" ", "-"):
                if position >= len(old_lines) or old_lines[position] != body:
                    raise PatchError("The suggested change does not match the current file.",
                                     detail=f"line {position + 1}: expected {body!r}")
                if tag == " ":
                    result.append(body)
                position += 1
            elif tag == "+":
                result.append(body)
            elif line.startswith(("---", "+++")):
                break
            i += 1
    if hunks == 0:
        raise PatchError("The suggested change contains no edits.")
    result.extend(old_lines[position:])
    trailing = "\n" if original.endswith("\n") or not original else ""
    return "\n".join(result) + trailing


def prepare_changes(root: Path, changes: list[FileChange]) -> tuple[list[PendingChange], dict[str, str]]:
    """Resolve proposed changes against the project. Returns (pending, problems by path)."""
    validator = PathValidator(root)
    pending: list[PendingChange] = []
    problems: dict[str, str] = {}
    for change in changes:
        try:
            target = validator.resolve(change.path)
            old = target.read_text(encoding="utf-8") if target.is_file() else None
            if change.content is not None:
                new = change.content
            else:
                if old is None:
                    raise PatchError("A diff was given for a file that does not exist.")
                new = apply_unified_diff(old, change.diff or "")
            if old is not None and old == new:
                continue
            pending.append(PendingChange(change.path, old, new))
        except (AppError, OSError) as exc:
            problems[change.path] = exc.message if isinstance(exc, AppError) else str(exc)
    return pending, problems


def apply_changes(root: Path, pending: list[PendingChange]) -> list[str]:
    """Write confirmed changes. Existing files are backed up first. Returns the written paths."""
    validator = PathValidator(root)
    written: list[str] = []
    for change in pending:
        target = validator.resolve(change.path)
        if target.exists():
            current = target.read_text(encoding="utf-8")
            if change.old is not None and current != change.old:
                raise PatchError(f"'{change.path}' changed on disk since the suggestion was made. Nothing more was written.")
            shutil.copy2(target, backup_name(target))  # byte-exact backup inside the project
        elif change.old is not None:
            raise PatchError(f"'{change.path}' no longer exists.")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(change.new, encoding="utf-8", newline="\n")
        written.append(change.path)
    return written
