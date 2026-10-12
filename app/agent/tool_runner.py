"""Run approved developer tools inside a project folder.

Security model (enforced here, not by the prompt):
- Commands are argument lists. ``shell=False`` always; there is no shell to interpret
  ``&&``, ``|``, ``;``, backticks, redirection or variables. Command strings are split
  by ``parse_command``, which refuses shell metacharacters outright.
- Only allowlisted programs with allowlisted argument shapes run:
    python -m pytest [flags] [paths in project]
    python <script.py in project> [plain args]
    python -m pip list
    javac [-d dir] [-cp dir] <.java files in project>
    java [-cp dir] <ClassName> [plain args]
    git status | diff | log | init | add <paths> | commit -m <message>   (inside the project)
  Anything else raises CommandRejectedError, even if the user approved it.
- The working directory is always the project root. Path arguments must resolve inside it.
- Every run has a timeout. On timeout the whole process tree is killed.
- stdout, stderr and the exit code are captured; huge output is truncated.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from app.errors import AppError, CommandRejectedError, PathValidationError
from app.validation.path_validator import PathValidator

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_S = 60.0
MAX_OUTPUT_CHARS = 100_000
SHELL_METACHARACTERS = set("&|;`$<>^%!\n\r(){}")
_FLAG = re.compile(r"^--?[A-Za-z][A-Za-z0-9_-]*(=[A-Za-z0-9_.,:/=+-]*)?$")
_PLAIN_ARG = re.compile(r"^[A-Za-z0-9_.,:=+@/-]{1,200}$")
_CLASS_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")
_COMMIT_MESSAGE = re.compile(r"^[^\x00-\x1f`$|;&<>]{1,200}$")
GIT_READ_ONLY = {"status", "diff", "log"}
PYTEST_BLOCKED_FLAGS = {"-p", "--pyargs", "--rootdir", "--confcutdir", "--basetemp", "-c", "--override-ini", "-o"}
WINDOWS_KILL = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "taskkill.exe"


class ToolUnavailableError(AppError):
    default_message = "The required tool is not installed."


@dataclass(frozen=True)
class CommandResult:
    argv: tuple[str, ...]
    cwd: Path
    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool
    duration_s: float
    truncated: bool = False

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out

    def display(self) -> str:
        return display_command(self.argv)


def display_command(argv: Sequence[str]) -> str:
    return " ".join(f'"{a}"' if (" " in a or not a) else a for a in argv)


def parse_command(text: str) -> list[str]:
    """Split a command line into arguments. Refuses anything a shell would interpret."""
    if not text.strip():
        raise CommandRejectedError("The command is empty and was not run.")
    bad = sorted(set(text) & SHELL_METACHARACTERS)
    if bad:
        raise CommandRejectedError(
            f"The command contains shell characters ({' '.join(bad)}) and was not run. "
            "Only single, allowlisted commands can run.",
            detail=text[:200],
        )
    argv: list[str] = []
    current = ""
    quote = ""
    started = False
    for ch in text.strip():
        if quote:
            if ch == quote:
                quote = ""
            else:
                current += ch
        elif ch in "\"'":
            quote = ch
            started = True
        elif ch.isspace():
            if started:
                argv.append(current)
                current, started = "", False
        else:
            current += ch
            started = True
    if quote:
        raise CommandRejectedError("The command has an unclosed quote and was not run.", detail=text[:200])
    if started:
        argv.append(current)
    return argv


def _reject(argv: Sequence[str], reason: str) -> CommandRejectedError:
    return CommandRejectedError(
        f"The command is not on the approved list and was not run: {reason}.",
        detail=display_command(argv)[:300],
    )


class ToolRunner:
    def __init__(self, project_root: Path, timeout_s: float = DEFAULT_TIMEOUT_S,
                 max_output_chars: int = MAX_OUTPUT_CHARS) -> None:
        self.root = Path(project_root).resolve()
        if not self.root.is_dir():
            raise CommandRejectedError(f"The project folder does not exist: {self.root}")
        self.validator = PathValidator(self.root)
        self.timeout_s = timeout_s
        self.max_output_chars = max_output_chars
        self._process: subprocess.Popen | None = None
        self._aborted = False

    # --- validation ----------------------------------------------------------------
    def _inside(self, argv: Sequence[str], value: str, must_exist: bool = False) -> str:
        try:
            resolved = self.validator.resolve(value)
        except PathValidationError as exc:
            raise _reject(argv, f"'{value}' is not a path inside the project ({exc.detail})") from None
        if must_exist and not resolved.exists():
            raise _reject(argv, f"'{value}' does not exist in the project")
        return value

    def _check_plain(self, argv: Sequence[str], args: Sequence[str]) -> None:
        for arg in args:
            if not _PLAIN_ARG.match(arg) or ".." in arg or re.match(r"^[A-Za-z]:", arg) or arg.startswith("/"):
                raise _reject(argv, f"argument '{arg}' is not allowed")

    def _check_python(self, argv: list[str]) -> None:
        args = argv[1:]
        if not args:
            raise _reject(argv, "python needs a script or module")
        if args[:2] == ["-m", "pytest"]:
            for arg in args[2:]:
                name = arg.split("=", 1)[0]
                if name in PYTEST_BLOCKED_FLAGS:
                    raise _reject(argv, f"pytest option '{name}' is not allowed")
                if _FLAG.match(arg):
                    continue
                self._inside(argv, arg.split("::", 1)[0])
            return
        if args == ["-m", "pip", "list"]:
            return
        if args[0].startswith("-"):
            raise _reject(argv, f"python option '{args[0]}' is not allowed")
        if not args[0].lower().endswith(".py"):
            raise _reject(argv, "python may only run a .py file of the project")
        self._inside(argv, args[0], must_exist=True)
        self._check_plain(argv, args[1:])

    def _check_javac(self, argv: list[str]) -> None:
        args = argv[1:]
        sources = 0
        i = 0
        while i < len(args):
            arg = args[i]
            if arg in ("-d", "-cp", "-classpath", "-sourcepath"):
                if i + 1 >= len(args):
                    raise _reject(argv, f"'{arg}' needs a folder")
                for part in args[i + 1].split(";"):
                    self._inside(argv, part)
                i += 2
                continue
            if arg in ("-g", "-nowarn", "-Xlint", "-Xlint:all", "-encoding"):
                if arg == "-encoding":
                    if i + 1 >= len(args) or not re.match(r"^[A-Za-z0-9-]{2,20}$", args[i + 1]):
                        raise _reject(argv, "bad -encoding value")
                    i += 2
                    continue
                i += 1
                continue
            if not arg.endswith(".java"):
                raise _reject(argv, f"javac argument '{arg}' is not allowed")
            self._inside(argv, arg, must_exist=True)
            sources += 1
            i += 1
        if sources == 0:
            raise _reject(argv, "javac needs at least one .java file of the project")

    def _check_java(self, argv: list[str]) -> None:
        args = argv[1:]
        if args[:1] in (["-cp"], ["-classpath"]):
            if len(args) < 3:
                raise _reject(argv, "java -cp needs a folder and a class")
            for part in args[1].split(";"):
                self._inside(argv, part)
            args = args[2:]
        if not args or not _CLASS_NAME.match(args[0]):
            raise _reject(argv, "java may only run a class name from the project")
        self._check_plain(argv, args[1:])

    def _check_git(self, argv: list[str]) -> None:
        args = argv[1:]
        if not args:
            raise _reject(argv, "git needs a subcommand")
        sub, rest = args[0], args[1:]
        if sub in GIT_READ_ONLY:
            for arg in rest:
                if arg.startswith("--output") or arg in ("--ext-diff", "--no-index"):
                    raise _reject(argv, f"git option '{arg}' is not allowed")
                if _FLAG.match(arg) or re.match(r"^-n?\d{1,4}$", arg):
                    continue
                self._inside(argv, arg)
            return
        if sub == "init":
            if rest:
                raise _reject(argv, "git init takes no arguments here")
            return
        if sub == "add":
            if not rest:
                raise _reject(argv, "git add needs paths")
            for arg in rest:
                if arg in ("-A", "--all", "."):
                    continue
                self._inside(argv, arg)
            return
        if sub == "commit":
            if len(rest) != 2 or rest[0] != "-m" or not _COMMIT_MESSAGE.match(rest[1]):
                raise _reject(argv, "only 'git commit -m <message>' is allowed")
            return
        raise _reject(argv, f"git {sub} is not allowed")

    def check(self, argv: Sequence[str]) -> list[str]:
        """Validate ``argv`` against the allowlist. Returns it (normalised) or raises."""
        argv = [str(a) for a in argv]
        if not argv:
            raise CommandRejectedError("The command is empty and was not run.")
        for arg in argv:
            if any(ch in SHELL_METACHARACTERS for ch in arg) and not (argv[:2] == ["git", "commit"]):
                raise _reject(argv, f"argument '{arg[:40]}' contains shell characters")
            if "\x00" in arg:
                raise _reject(argv, "an argument contains a NUL byte")
        program = argv[0]
        if program != Path(program).name or program.lower().endswith((".exe", ".bat", ".cmd", ".ps1")):
            raise _reject(argv, f"programs must be named without a path or extension (got '{program}')")
        checks = {"python": self._check_python, "javac": self._check_javac, "java": self._check_java,
                  "git": self._check_git}
        check = checks.get(program.lower())
        if check is None:
            raise _reject(argv, f"'{program}' is not an approved program")
        argv[0] = program.lower()
        check(argv)
        return argv

    # --- execution -------------------------------------------------------------------
    @staticmethod
    def resolve_executable(program: str) -> str:
        if program == "python" and not getattr(sys, "frozen", False):
            return sys.executable  # the app's own interpreter (the venv during development)
        found = shutil.which(program)
        if not found:
            raise ToolUnavailableError(f"'{program}' is not installed or not on PATH, so the command was not run.")
        return found

    def _truncate(self, text: str) -> tuple[str, bool]:
        if len(text) <= self.max_output_chars:
            return text, False
        half = self.max_output_chars // 2
        cut = len(text) - self.max_output_chars
        return f"{text[:half]}\n[... {cut} characters truncated ...]\n{text[-half:]}", True

    def _environment(self) -> dict[str, str]:
        env = {k: v for k, v in os.environ.items() if not k.upper().startswith(("LAA_", "PYTHONSTARTUP"))}
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        env.pop("PYTHONPATH", None)
        return env

    def _kill_tree(self, process: subprocess.Popen) -> None:
        if sys.platform == "win32":
            subprocess.run([str(WINDOWS_KILL), "/F", "/T", "/PID", str(process.pid)],
                           capture_output=True, timeout=15, shell=False,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        else:  # pragma: no cover - the app targets Windows
            import signal

            os.killpg(process.pid, signal.SIGKILL)
        try:
            process.kill()
        except OSError:
            pass

    def abort(self) -> None:
        """Stop the running command and its children (thread-safe; used by the Stop button)."""
        self._aborted = True
        process = self._process
        if process is not None and process.poll() is None:
            self._kill_tree(process)

    def run(self, argv: Sequence[str]) -> CommandResult:
        """Check, then run. Raises CommandRejectedError / ToolUnavailableError before starting anything."""
        checked = self.check(argv)
        executable = self.resolve_executable(checked[0])
        real_argv = [executable, *checked[1:]]
        logger.info("Running approved command in %s: %s", self.root, display_command(checked))
        flags = 0
        if sys.platform == "win32":
            flags = subprocess.CREATE_NEW_PROCESS_GROUP | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        started = time.monotonic()
        process = subprocess.Popen(
            real_argv, cwd=self.root, shell=False, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, env=self._environment(), creationflags=flags,
            start_new_session=sys.platform != "win32",
        )
        self._process = process
        timed_out = False
        try:
            out, err = process.communicate(timeout=self.timeout_s)
        except subprocess.TimeoutExpired:
            timed_out = True
            logger.warning("Command timed out after %.0f s; killing the process tree", self.timeout_s)
            self._kill_tree(process)
            try:
                out, err = process.communicate(timeout=15)
            except subprocess.TimeoutExpired:  # a stray grandchild still holds the pipes
                out, err = b"", b"[output unavailable: the process tree could not be fully stopped]"

        duration = time.monotonic() - started
        stdout, cut_out = self._truncate(out.decode("utf-8", errors="replace"))
        stderr, cut_err = self._truncate(err.decode("utf-8", errors="replace"))
        self._process = None
        if timed_out:
            stderr += f"\n[Stopped: the command did not finish within {self.timeout_s:.0f} s.]"
        elif self._aborted:
            stderr += "\n[Stopped by the user.]"
        return CommandResult(tuple(checked), self.root, None if timed_out else process.returncode, stdout, stderr,
                             timed_out, duration, cut_out or cut_err)


def default_test_command(root: Path) -> list[str] | None:
    """The test command for a project, judged from its files (None when unknown)."""
    root = Path(root)
    python_tests = [p for p in root.rglob("*.py") if p.name.startswith("test_") or p.name.endswith("_test.py")]
    if python_tests:
        return ["python", "-m", "pytest", "-q"]
    return None


def result_markdown(result: CommandResult) -> str:
    """Chat text for a finished command (output in fenced blocks; never re-executed)."""
    if result.timed_out:
        head = f"Command timed out after {result.duration_s:.1f} s"
    else:
        head = f"Exit code {result.exit_code} · {result.duration_s:.1f} s"
    lines = [f"`{result.display()}` in `{result.cwd}`", "", head]
    if result.stdout.strip():
        lines += ["", "Output:", "````text", result.stdout.rstrip(), "````"]
    if result.stderr.strip():
        lines += ["", "Errors:", "````text", result.stderr.rstrip(), "````"]
    if result.truncated:
        lines += ["", "(Long output was shortened.)"]
    return "\n".join(lines)
