"""Tool runner: allowlist, bypass attempts, real subprocess capture, timeout tree kill."""

import sys
import textwrap
import threading
import time

import pytest

from app.agent.tool_runner import (
    CommandResult,
    ToolRunner,
    ToolUnavailableError,
    default_test_command,
    parse_command,
    result_markdown,
)
from app.errors import CommandRejectedError


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    (root / "hello.py").write_text("import sys\nprint('out', sys.argv[1:])\nprint('err', file=sys.stderr)\n"
                                   "sys.exit(3)\n", encoding="utf-8")
    (root / "src").mkdir()
    (root / "src" / "Main.java").write_text("class Main {}", encoding="utf-8")
    (root / "test_ok.py").write_text("def test_ok():\n    assert 1 + 1 == 2\n", encoding="utf-8")
    return root


@pytest.fixture
def runner(project):
    return ToolRunner(project, timeout_s=30)


ALLOWED = [
    ["python", "-m", "pytest"],
    ["python", "-m", "pytest", "-q", "--tb=short", "tests", "test_ok.py::test_ok", "-k", "ok"],
    ["python", "hello.py", "Alice", "--count=2"],
    ["python", "-m", "pip", "list"],
    ["javac", "-d", "out", "src/Main.java"],
    ["javac", "-encoding", "UTF-8", "src/Main.java"],
    ["java", "-cp", "out", "Main"],
    ["java", "com.example.App", "arg1"],
    ["git", "status"],
    ["git", "diff", "--stat"],
    ["git", "log", "--oneline", "-n5"],
    ["git", "init"],
    ["git", "add", "-A"],
    ["git", "add", "hello.py"],
    ["git", "commit", "-m", "Initial commit (generated)"],
    ["PYTHON", "-m", "pytest"],
]


@pytest.mark.parametrize("argv", ALLOWED)
def test_allowlisted_commands_pass_the_check(runner, argv):
    assert runner.check(argv)[0] == argv[0].lower()


BYPASS_ATTEMPTS = [
    ["powershell", "-c", "Remove-Item C:\\ -Recurse"],
    ["pwsh", "-Command", "ls"],
    ["cmd", "/c", "del /s /q C:\\"],
    ["cmd.exe", "/c", "dir"],
    ["bash", "-c", "rm -rf /"],
    ["python", "-c", "import os; os.system('calc')"],
    ["python", "-m", "http.server"],
    ["python", "-m", "pip", "install", "evil"],
    ["python", "-m", "pytest", "-p", "evil_plugin"],
    ["python", "-m", "pytest", "--rootdir=C:\\"],
    ["python", "-m", "pytest", "..\\..\\other_project"],
    ["python", "-m", "pytest", "C:\\Windows"],
    ["python", "..\\..\\evil.py"],
    ["python", "C:\\Users\\Public\\evil.py"],
    ["python", "missing.py"],
    ["python", "hello.py", "&&", "calc"],
    ["python", "hello.py", "|", "more"],
    ["python", "hello.py", ";", "calc"],
    ["python", "hello.py", "`calc`"],
    ["python", "hello.py", "$(calc)"],
    ["python", "hello.py", "%PATH%"],
    ["python", "hello.py", "../secret"],
    ["python", "hello.py", "C:\\secret"],
    ["python.exe", "hello.py"],
    ["C:\\Python312\\python.exe", "hello.py"],
    ["..\\python", "hello.py"],
    ["python", "-X", "importtime", "hello.py"],
    ["javac", "C:\\elsewhere\\Evil.java"],
    ["javac", "-d", "..\\..\\out", "src/Main.java"],
    ["javac", "-J-Xmx1g", "src/Main.java"],
    ["java", "-jar", "evil.jar"],
    ["java", "-cp", "C:\\", "Evil"],
    ["java", "-agentlib:jdwp", "Main"],
    ["git", "push"],
    ["git", "remote", "add", "x", "https://example.com"],
    ["git", "config", "core.hooksPath", "C:\\evil"],
    ["git", "-c", "core.pager=calc", "log"],
    ["git", "clone", "https://example.com/x"],
    ["git", "diff", "--output=C:\\x.txt"],
    ["git", "diff", "--no-index", "C:\\a", "C:\\b"],
    ["git", "add", "..\\..\\outside"],
    ["git", "commit", "-am", "x"],
    ["git", "commit", "-m", "x", "--amend"],
    ["curl", "https://example.com"],
    ["ollama", "pull", "other-model"],
    ["del", "hello.py"],
    [],
]


@pytest.mark.parametrize("argv", BYPASS_ATTEMPTS)
def test_bypass_attempts_are_rejected(runner, argv):
    with pytest.raises(CommandRejectedError):
        runner.check(argv)


@pytest.mark.parametrize("text", [
    "python -m pytest && calc", "python hello.py | more", "python hello.py; calc", "python `calc`",
    "python $(calc)", "python hello.py > C:\\x", "powershell -c \"ls\" & calc", "cmd /c dir ^& calc",
    "python hello.py\ncalc", "python 'unclosed", "", "echo %USERPROFILE%",
])
def test_parse_command_refuses_shell_syntax(text):
    with pytest.raises(CommandRejectedError):
        parse_command(text)


def test_parse_command_splits_quotes():
    assert parse_command('git commit -m "Add tests now"') == ["git", "commit", "-m", "Add tests now"]
    assert parse_command("python -m pytest -q") == ["python", "-m", "pytest", "-q"]


def test_runner_needs_existing_project(tmp_path):
    with pytest.raises(CommandRejectedError):
        ToolRunner(tmp_path / "missing")


# --- real subprocesses (python only; always available) ---------------------------------
def test_run_captures_stdout_stderr_and_exit_code(runner, project):
    result = runner.run(["python", "hello.py", "Alice"])
    assert result.exit_code == 3 and not result.ok and not result.timed_out
    assert "out ['Alice']" in result.stdout and "err" in result.stderr
    assert result.cwd == project.resolve()
    markdown = result_markdown(result)
    assert "Exit code 3" in markdown and "out ['Alice']" in markdown


def test_run_pytest_in_project(runner):
    result = runner.run(["python", "-m", "pytest", "-q"])
    assert result.ok, result.stdout + result.stderr
    assert "1 passed" in result.stdout


def test_rejected_command_never_starts_a_process(runner, monkeypatch):
    import subprocess

    started = []
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: started.append(a))
    with pytest.raises(CommandRejectedError):
        runner.run(["cmd", "/c", "dir"])
    assert started == []


def test_timeout_kills_the_whole_process_tree(project):
    marker = project / "child_survived.txt"
    (project / "spawner.py").write_text(textwrap.dedent(f"""
        import subprocess, sys, time
        child = "import time, pathlib; time.sleep(4); pathlib.Path('{marker.as_posix()}').write_text('alive')"
        subprocess.Popen([sys.executable, "-c", child])
        time.sleep(60)
    """), encoding="utf-8")
    runner = ToolRunner(project, timeout_s=1.5)
    started = time.monotonic()
    result = runner.run(["python", "spawner.py"])
    assert result.timed_out and result.exit_code is None and not result.ok
    assert time.monotonic() - started < 15
    assert "did not finish within" in result.stderr
    time.sleep(5)
    assert not marker.exists(), "the child process outlived the timeout kill"


def test_abort_stops_a_running_command(project):
    (project / "slow.py").write_text("import time\ntime.sleep(60)\n", encoding="utf-8")
    runner = ToolRunner(project, timeout_s=60)
    box = {}
    thread = threading.Thread(target=lambda: box.setdefault("r", runner.run(["python", "slow.py"])))
    thread.start()
    time.sleep(1.0)
    runner.abort()
    thread.join(15)
    assert not thread.is_alive()
    assert "Stopped by the user" in box["r"].stderr


def test_huge_output_is_truncated(project):
    (project / "loud.py").write_text("print('x' * 500000)\n", encoding="utf-8")
    result = ToolRunner(project, max_output_chars=1000).run(["python", "loud.py"])
    assert result.truncated and len(result.stdout) < 1200 and "characters truncated" in result.stdout


def test_missing_tool_reports_clearly(runner, monkeypatch):
    import shutil

    monkeypatch.setattr(shutil, "which", lambda name: None)
    with pytest.raises(ToolUnavailableError) as info:
        runner.resolve_executable("javac")
    assert "not installed" in info.value.message


def test_default_test_command(project, tmp_path):
    assert default_test_command(project) == ["python", "-m", "pytest", "-q"]
    empty = tmp_path / "empty"
    empty.mkdir()
    assert default_test_command(empty) is None


def test_result_markdown_for_timeout(tmp_path):
    result = CommandResult(("python", "x.py"), tmp_path, None, "", "", True, 60.2)
    assert "timed out after 60.2 s" in result_markdown(result)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows process groups")
def test_shell_false_means_no_metacharacter_interpretation(project):
    # even if a metacharacter slipped into an argument, no shell would see it
    from app.agent import tool_runner

    assert tool_runner.SHELL_METACHARACTERS >= set("&|;`$<>^%")
