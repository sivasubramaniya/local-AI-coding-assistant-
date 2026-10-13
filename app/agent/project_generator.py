"""Two-step project generation: PLAN (strict JSON) then one FILE call per file.

Model output is only ever parsed as data. Nothing in it is executed.

- ``parse_plan`` accepts one JSON object (optionally inside a single ```json fence)
  with the exact keys of ``ProjectPlan``. Paths are checked with the path validator.
- ``parse_file_block`` accepts an answer with exactly one complete fenced block, or several
  blocks of which exactly one is in the file's language (models often add a "run it" snippet).
- A malformed answer is retried once with a corrective message; a second failure is
  reported for that file. Files that succeeded are kept.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from app.errors import AppError, GenerationError, PathValidationError, ResponseFormatError
from app.validation.path_validator import PathValidator, safe_name, validate_relative_path

logger = logging.getLogger(__name__)

MAX_FILES = 15
EARLIER_FILES_CHARS = 12_000  # earlier generated files shown to later file calls (keeps APIs consistent)
PLAN_KEYS = ("project_name", "description", "language", "files", "run_instructions", "test_command")
ChatFn = Callable[[list[dict]], str]


@dataclass(frozen=True)
class PlannedFile:
    path: str
    purpose: str


@dataclass(frozen=True)
class ProjectPlan:
    project_name: str
    description: str
    language: str
    files: tuple[PlannedFile, ...]
    run_instructions: str
    test_command: str
    request: str = ""  # the user's original request (repeated in every file call)

    def to_markdown(self) -> str:
        # blank lines matter: Markdown only starts a list or a new paragraph after one
        lines = [f"**Project plan: {self.project_name}**", "", self.description, "",
                 f"Language: {self.language}", "", "Files:", ""]
        lines += [f"{i}. `{f.path}` — {f.purpose}" for i, f in enumerate(self.files, 1)]
        if self.run_instructions:
            lines += ["", f"Run: {self.run_instructions}"]
        if self.test_command:
            lines += ["", f"Test: `{self.test_command}`"]
        return "\n".join(lines)


@dataclass
class GenerationResult:
    plan: ProjectPlan
    root: Path
    written: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)
    cancelled: bool = False

    @property
    def status(self) -> str:
        if self.cancelled:
            return "cancelled"
        if not self.written:
            return "failed"
        return "partial" if self.failed else "complete"

    def summary_markdown(self) -> str:
        # one Markdown paragraph per entry (single newlines would merge them into one line)
        paragraphs = [f"**{self.plan.project_name}** — {len(self.written)} of {len(self.plan.files)} files written",
                      f"Folder: `{self.root}`"]
        if self.cancelled:
            paragraphs.append("Generation was stopped. Files written so far were kept.")
        if self.failed:
            paragraphs.append("Files that could not be generated:\n\n" + "\n".join(
                f"- `{path}`: {reason}" for path, reason in self.failed.items()))
        if self.plan.run_instructions:
            paragraphs.append(f"Run: {self.plan.run_instructions}")
        if self.plan.test_command:
            paragraphs.append(f"Test: `{self.plan.test_command}`")
        paragraphs.append("Review the code before running it. Nothing was executed.")
        return "\n\n".join(paragraphs)


# --- prompts -----------------------------------------------------------------------
PLAN_INSTRUCTIONS = """Plan a new software project for the request below.

Reply with ONLY one JSON object and no other text, exactly in this shape:
{{"project_name": "short-kebab-case-name", "description": "one or two sentences", "language": "main language",
 "files": [{{"path": "relative/path.ext", "purpose": "what this file contains"}}],
 "run_instructions": "how to run it", "test_command": "command that runs the tests, or empty"}}

Rules:
- At most {max_files} files. Relative paths with forward slashes, no '..', no absolute paths.
- Include a README.md with build, run and test instructions.
- Keep the project small and complete; prefer the standard library.

Request:
{request}"""

FILE_INSTRUCTIONS = """Original request: {request}

Project: {name} ({language})
Description: {description}
All files in the project:
{file_list}
{earlier}
Write the complete content of the file `{path}` (purpose: {purpose}).
It must work with the files already written above: use exactly their class, function and method names.
Follow the original request exactly (for example, do not add libraries it rules out).
Reply with exactly ONE fenced code block that contains the whole file and nothing else.
{fence_hint}Do not use placeholders; the file must be complete."""

MARKDOWN_FENCE_HINT = "Because this is a Markdown file, open and close the block with ```` (four backticks).\n"


def plan_messages(request: str, system_prompt: str) -> list[dict]:
    return [{"role": "system", "content": system_prompt},
            {"role": "user", "content": PLAN_INSTRUCTIONS.format(max_files=MAX_FILES, request=request.strip())}]


def _is_markdown(path: str) -> bool:
    return PurePosixPath(path).suffix.lower() in (".md", ".markdown")


def earlier_files_text(earlier: dict[str, str], max_chars: int = EARLIER_FILES_CHARS) -> str:
    """Already generated files (newest last), as many as fit in ``max_chars``."""
    parts: list[str] = []
    used = 0
    for path, content in earlier.items():
        if _is_markdown(path):
            continue
        block = f"\nAlready written `{path}`:\n````\n{content.rstrip()}\n````\n"
        if used + len(block) > max_chars:
            parts.append(f"\n(`{path}` was written too but is not shown here.)\n")
            continue
        parts.append(block)
        used += len(block)
    return "".join(parts)


def file_messages(plan: ProjectPlan, planned: PlannedFile, system_prompt: str,
                  earlier: dict[str, str] | None = None) -> list[dict]:
    content = FILE_INSTRUCTIONS.format(
        request=plan.request or plan.description, name=plan.project_name, language=plan.language,
        description=plan.description, file_list="\n".join(f"- {f.path}: {f.purpose}" for f in plan.files),
        earlier=earlier_files_text(earlier or {}), path=planned.path, purpose=planned.purpose,
        fence_hint=MARKDOWN_FENCE_HINT if _is_markdown(planned.path) else "",
    )
    return [{"role": "system", "content": system_prompt}, {"role": "user", "content": content}]


def corrective_messages(messages: list[dict], bad_answer: str, problem: str, expected: str) -> list[dict]:
    return [*messages, {"role": "assistant", "content": bad_answer},
            {"role": "user", "content": f"Your answer could not be used: {problem}. Reply again with {expected}."}]


# --- parsing -----------------------------------------------------------------------
_FENCE_OPEN = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")


@dataclass(frozen=True)
class FencedBlock:
    info: str
    content: str


def fenced_blocks(text: str) -> tuple[list[FencedBlock], bool]:
    """CommonMark-style fenced blocks. Returns (blocks, last_block_unclosed)."""
    blocks: list[FencedBlock] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        match = _FENCE_OPEN.match(lines[i])
        if not match or (match.group(1)[0] == "`" and "`" in match.group(2)):
            i += 1
            continue
        fence, info = match.group(1), match.group(2).strip()
        closing = re.compile(rf"^ {{0,3}}{re.escape(fence[0])}{{{len(fence)},}}\s*$")
        body: list[str] = []
        i += 1
        while i < len(lines) and not closing.match(lines[i]):
            body.append(lines[i])
            i += 1
        if i >= len(lines):
            return blocks, True
        blocks.append(FencedBlock(info, "\n".join(body)))
        i += 1
    return blocks, False


def parse_plan(text: str) -> ProjectPlan:
    """Strictly parse the PLAN answer. Raises ResponseFormatError with the reason."""
    raw = text.strip()
    blocks, unclosed = fenced_blocks(raw)
    if unclosed:
        raise ResponseFormatError("The plan was cut off.", detail="unclosed code fence")
    if blocks:
        if len(blocks) != 1:
            raise ResponseFormatError("The plan must be one JSON object.", detail=f"{len(blocks)} code blocks")
        raw = blocks[0].content.strip()
    if not (raw.startswith("{") and raw.endswith("}")):
        raise ResponseFormatError("The plan must be one JSON object.", detail="answer is not a JSON object")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ResponseFormatError("The plan is not valid JSON.", detail=str(exc)) from None
    if not isinstance(data, dict):
        raise ResponseFormatError("The plan must be one JSON object.", detail=type(data).__name__)
    missing = [k for k in PLAN_KEYS if k not in data]
    if missing:
        raise ResponseFormatError("The plan is incomplete.", detail=f"missing keys: {', '.join(missing)}")
    for key in ("project_name", "description", "language", "run_instructions", "test_command"):
        if not isinstance(data[key], str):
            raise ResponseFormatError("The plan has a wrong value.", detail=f"'{key}' must be a string")
    for key in ("project_name", "description", "language"):
        if not data[key].strip():
            raise ResponseFormatError("The plan is incomplete.", detail=f"'{key}' is empty")
    files = data["files"]
    if not isinstance(files, list) or not files:
        raise ResponseFormatError("The plan has no files.", detail="'files' must be a non-empty list")
    if len(files) > MAX_FILES:
        raise ResponseFormatError("The plan has too many files.", detail=f"{len(files)} > {MAX_FILES}")
    planned: list[PlannedFile] = []
    seen: set[str] = set()
    for entry in files:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise ResponseFormatError("The plan has a wrong file entry.", detail=repr(entry)[:120])
        try:
            path = validate_relative_path(entry["path"])
        except PathValidationError as exc:
            raise ResponseFormatError("The plan contains an unsafe file path.", detail=exc.message) from None
        if path.lower() in seen:
            raise ResponseFormatError("The plan lists a file twice.", detail=path)
        seen.add(path.lower())
        purpose = entry.get("purpose", "")
        planned.append(PlannedFile(path, purpose.strip() if isinstance(purpose, str) else ""))
    return ProjectPlan(safe_name(data["project_name"]), data["description"].strip(), data["language"].strip(),
                       tuple(planned), data["run_instructions"].strip(), data["test_command"].strip())


LANGUAGES_BY_SUFFIX = {
    ".py": {"python", "py", "python3"}, ".java": {"java"}, ".js": {"javascript", "js"},
    ".ts": {"typescript", "ts"}, ".html": {"html"}, ".htm": {"html"}, ".css": {"css"},
    ".json": {"json"}, ".sql": {"sql"}, ".ps1": {"powershell", "ps1"}, ".sh": {"bash", "sh", "shell"},
    ".go": {"go", "golang"}, ".rs": {"rust", "rs"}, ".cs": {"csharp", "cs", "c#"}, ".cpp": {"cpp", "c++"},
    ".c": {"c"}, ".yaml": {"yaml", "yml"}, ".yml": {"yaml", "yml"}, ".toml": {"toml"}, ".xml": {"xml"},
    ".txt": {"text", "txt", "plaintext", ""}, ".cfg": {"ini", "cfg", "text"}, ".ini": {"ini"},
}


def _block_language(block: FencedBlock) -> str:
    return (block.info.split() or [""])[0].lower()


def parse_file_block(text: str, path: str | None = None) -> str:
    """Strictly parse a FILE answer: exactly one complete, non-empty fenced block.

    With ``path``, an answer with several blocks is accepted only if exactly one of them is in
    the file's language (for example the .py file plus a ```bash "how to run it" snippet).
    """
    blocks, unclosed = fenced_blocks(text)
    if unclosed:
        raise ResponseFormatError("The file was cut off.", detail="unclosed code fence")
    if not blocks:
        raise ResponseFormatError("The answer has no code block.", detail="no fenced code block")
    if len(blocks) > 1:
        languages = LANGUAGES_BY_SUFFIX.get(PurePosixPath(path).suffix.lower()) if path else None
        matching = [b for b in blocks if languages is not None and _block_language(b) in languages]
        if len(matching) != 1:
            raise ResponseFormatError("The answer must contain exactly one code block.",
                                      detail=f"{len(blocks)} blocks")
        blocks = matching
    content = blocks[0].content
    if not content.strip():
        raise ResponseFormatError("The code block is empty.", detail="empty block")
    return content.rstrip("\n") + "\n"


_FENCE_LINE = re.compile(r"^ {0,3}(`{3,}|~{3,})")


def parse_markdown_file(text: str) -> str:
    """Markdown files (documentation) are parsed strictly first, then leniently.

    Models often nest ``` fences inside a Markdown block or use a shorter outer fence.
    The lenient path drops one outer fence line at the start and end and keeps the rest.
    """
    try:
        return parse_file_block(text)
    except ResponseFormatError:
        lines = text.strip().splitlines()
        if lines and _FENCE_LINE.match(lines[0]):
            lines = lines[1:]
        if lines and _FENCE_LINE.match(lines[-1]) and not lines[-1].strip().strip("`~"):
            lines = lines[:-1]
        content = "\n".join(lines).strip("\n")
        if not content.strip():
            raise
        return content + "\n"


# --- generation --------------------------------------------------------------------
class ProjectWriter:
    """Creates ``<projects_dir>/<safe-name>[-N]`` and writes files through the path validator."""

    def __init__(self, projects_dir: Path, name: str) -> None:
        base = Path(projects_dir)
        base.mkdir(parents=True, exist_ok=True)
        folder = safe_name(name)
        root = base / folder
        counter = 2
        while root.exists():  # never write into an existing project
            root = base / f"{folder}-{counter}"
            counter += 1
        root.mkdir()
        self.root = root.resolve()
        self.validator = PathValidator(self.root)

    def write(self, relative: str, content: str) -> Path:
        target = self.validator.resolve(relative)
        if target.exists():
            raise GenerationError(f"'{relative}' already exists and was not overwritten.")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", newline="\n")
        return target


class ProjectGenerator:
    """Runs the PLAN and FILE calls through ``chat`` (messages -> answer text)."""

    def __init__(self, chat: ChatFn, system_prompt: str) -> None:
        self._chat = chat
        self._system_prompt = system_prompt

    def _ask(self, messages: list[dict], parse: Callable[[str], object], expected: str) -> object:
        answer = self._chat(messages)
        try:
            return parse(answer)
        except ResponseFormatError as first:
            logger.info("Malformed answer (%s); retrying once", first.detail or first.message)
            retry = corrective_messages(messages, answer, first.detail or first.message, expected)
            return parse(self._chat(retry))

    def make_plan(self, request: str) -> ProjectPlan:
        plan = self._ask(plan_messages(request, self._system_prompt), parse_plan, "ONLY the JSON object")
        assert isinstance(plan, ProjectPlan)
        return replace(plan, request=request.strip())

    def generate_file(self, plan: ProjectPlan, planned: PlannedFile, earlier: dict[str, str] | None = None) -> str:
        if _is_markdown(planned.path):
            parse = parse_markdown_file
        else:
            def parse(answer: str) -> str:
                return parse_file_block(answer, planned.path)
        content = self._ask(file_messages(plan, planned, self._system_prompt, earlier), parse,
                            "exactly one complete fenced code block")
        assert isinstance(content, str)
        return content

    def generate(
        self,
        plan: ProjectPlan,
        writer: ProjectWriter,
        progress: Callable[[int, int, str], None] = lambda i, n, p: None,
        cancelled: Callable[[], bool] = lambda: False,
    ) -> GenerationResult:
        result = GenerationResult(plan, writer.root)
        earlier: dict[str, str] = {}
        total = len(plan.files)
        for index, planned in enumerate(plan.files, 1):
            if cancelled():
                result.cancelled = True
                break
            progress(index, total, planned.path)
            try:
                content = self.generate_file(plan, planned, earlier)
                if cancelled():
                    result.cancelled = True
                    break
                writer.write(planned.path, content)
                result.written.append(planned.path)
                earlier[planned.path] = content
            except AppError as exc:
                if cancelled():
                    result.cancelled = True
                    break
                reason = exc.message if not exc.detail else f"{exc.message} ({exc.detail})"
                logger.warning("File %s failed: %s", planned.path, reason)
                result.failed[planned.path] = reason
                if not isinstance(exc, (ResponseFormatError, PathValidationError, GenerationError)):
                    # Ollama unreachable or similar: the remaining files would fail the same way
                    for rest in plan.files[index:]:
                        result.failed[rest.path] = "skipped after the previous error"
                    break
        return result


def backup_name(path: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    candidate = path.with_name(f"{path.name}.bak-{stamp}")
    counter = 2
    while candidate.exists():
        candidate = path.with_name(f"{path.name}.bak-{stamp}-{counter}")
        counter += 1
    return candidate
