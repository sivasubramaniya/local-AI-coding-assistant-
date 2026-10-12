"""Project generator: strict plan/file parsing, retry, partial failures, writer. MOCK model only."""

import json

import pytest

from app.agent.project_generator import (
    MAX_FILES,
    PlannedFile,
    ProjectGenerator,
    ProjectPlan,
    ProjectWriter,
    fenced_blocks,
    parse_file_block,
    parse_plan,
)
from app.errors import GenerationError, OllamaUnavailableError, PathValidationError, ResponseFormatError

SYSTEM = "system prompt"


def plan_json(**overrides) -> str:
    data = {
        "project_name": "Tiny Calc",
        "description": "A tiny calculator.",
        "language": "Python",
        "files": [
            {"path": "calc.py", "purpose": "functions"},
            {"path": "tests/test_calc.py", "purpose": "tests"},
            {"path": "README.md", "purpose": "docs"},
        ],
        "run_instructions": "python calc.py",
        "test_command": "python -m pytest",
    }
    data.update(overrides)
    return json.dumps(data)


def block(code: str, lang: str = "python", fence: str = "```") -> str:
    return f"{fence}{lang}\n{code}\n{fence}"


# --- plan parsing ----------------------------------------------------------------
def test_parse_valid_plan():
    plan = parse_plan(plan_json())
    assert plan.project_name == "tiny-calc"  # folder-safe
    assert [f.path for f in plan.files] == ["calc.py", "tests/test_calc.py", "README.md"]
    assert plan.test_command == "python -m pytest"
    assert "tests/test_calc.py" in plan.to_markdown()


def test_parse_plan_inside_json_fence():
    assert parse_plan(f"```json\n{plan_json()}\n```").language == "Python"


@pytest.mark.parametrize("text, reason", [
    ("Sure! Here is the plan: {}", "not a JSON object"),
    ('{"project_name": "x", "files": [', "JSON object"),  # partial / cut off
    (plan_json()[:-20], "JSON"),
    ("```json\n" + plan_json(), "cut off"),
    (json.dumps({"project_name": "x"}), "missing keys"),
    (plan_json(files=[]), "non-empty list"),
    (plan_json(files="calc.py"), "non-empty list"),
    (plan_json(files=[{"purpose": "no path"}]), "file entry"),
    (plan_json(project_name="  "), "'project_name' is empty"),
    (plan_json(test_command=5), "must be a string"),
    (plan_json(files=[{"path": f"f{i}.py", "purpose": ""} for i in range(MAX_FILES + 1)]), ">"),
    (plan_json(files=[{"path": "a.py"}, {"path": "A.py"}]), "twice"),
    ("[1, 2]", "not a JSON object"),
    ("```json\n{}\n```\n```json\n{}\n```", "2 code blocks"),
])
def test_malformed_plans_are_rejected(text, reason):
    with pytest.raises(ResponseFormatError) as info:
        parse_plan(text)
    assert reason in f"{info.value.message} {info.value.detail}"


@pytest.mark.parametrize("bad_path", ["../evil.py", "C:/Windows/x.py", "/etc/passwd", "a/../../b.py", "CON.txt",
                                      "\\\\server\\share\\x.py", "dir/aux.py", "x?.py"])
def test_unsafe_plan_paths_are_rejected(bad_path):
    with pytest.raises(ResponseFormatError) as info:
        parse_plan(plan_json(files=[{"path": bad_path, "purpose": "x"}]))
    assert "unsafe" in info.value.message


# --- file block parsing ---------------------------------------------------------------
def test_parse_single_block_with_surrounding_prose():
    text = "Here is the file:\n" + block("def add(a, b):\n    return a + b") + "\nHope this helps."
    assert parse_file_block(text) == "def add(a, b):\n    return a + b\n"


def test_markdown_file_with_nested_fences():
    readme = "# Calc\n\nRun:\n```\npython calc.py\n```\n"
    content = parse_file_block(block(readme.rstrip("\n"), "markdown", "````"))
    assert content == readme


@pytest.mark.parametrize("text, reason", [
    ("def add(a, b): return a + b", "no fenced code block"),
    (block("a = 1") + "\n" + block("b = 2"), "2 blocks"),
    ("```python\nprint('cut off", "unclosed"),
    (block("   \n  "), "empty"),
])
def test_malformed_file_blocks(text, reason):
    with pytest.raises(ResponseFormatError) as info:
        parse_file_block(text)
    assert reason in f"{info.value.message} {info.value.detail}"


def test_fenced_blocks_ignores_inline_backticks():
    blocks, unclosed = fenced_blocks("use ```x``` inline\n```py\nok\n```")
    assert [b.content for b in blocks] == ["ok"] and not unclosed


# --- generator with a scripted model ---------------------------------------------------
class ScriptedModel:
    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls: list[list[dict]] = []

    def __call__(self, messages):
        self.calls.append(messages)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


def test_plan_retry_once_with_corrective_message():
    model = ScriptedModel("Sure, here you go!", plan_json())
    plan = ProjectGenerator(model, SYSTEM).make_plan("make a calculator")
    assert plan.project_name == "tiny-calc"
    assert len(model.calls) == 2
    retry = model.calls[1]
    assert retry[0] == {"role": "system", "content": SYSTEM}
    assert retry[-2] == {"role": "assistant", "content": "Sure, here you go!"}
    assert "could not be used" in retry[-1]["content"] and "JSON" in retry[-1]["content"]


def test_plan_fails_after_second_malformed_answer():
    model = ScriptedModel("nope", '{"broken": ')
    with pytest.raises(ResponseFormatError):
        ProjectGenerator(model, SYSTEM).make_plan("x")
    assert len(model.calls) == 2


def _plan(*paths):
    return ProjectPlan("demo", "d", "Python", tuple(PlannedFile(p, "p") for p in paths), "run", "test")


def test_generate_keeps_successes_and_lists_failures(tmp_path):
    model = ScriptedModel(
        block("print('a')"),
        "no code here", "still no code",  # b.py fails twice -> reported
        "oops", block("print('c')"),  # c.py succeeds on the retry
    )
    writer = ProjectWriter(tmp_path / "projects", "demo")
    progress = []
    result = ProjectGenerator(model, SYSTEM).generate(_plan("a.py", "b.py", "pkg/c.py"), writer,
                                                       lambda i, n, p: progress.append((i, n, p)))
    assert result.written == ["a.py", "pkg/c.py"]
    assert list(result.failed) == ["b.py"] and "no code block" in result.failed["b.py"]
    assert result.status == "partial"
    assert (writer.root / "a.py").read_text() == "print('a')\n"
    assert (writer.root / "pkg" / "c.py").is_file() and not (writer.root / "b.py").exists()
    assert progress == [(1, 3, "a.py"), (2, 3, "b.py"), (3, 3, "pkg/c.py")]
    summary = result.summary_markdown()
    assert "2 of 3 files written" in summary and "b.py" in summary and "Nothing was executed" in summary


def test_generate_stops_after_ollama_goes_away(tmp_path):
    model = ScriptedModel(block("x = 1"), OllamaUnavailableError("Ollama is not running."))
    writer = ProjectWriter(tmp_path, "demo")
    result = ProjectGenerator(model, SYSTEM).generate(_plan("a.py", "b.py", "c.py"), writer)
    assert result.written == ["a.py"]
    assert result.failed["b.py"].startswith("Ollama is not running")
    assert result.failed["c.py"] == "skipped after the previous error"


def test_generate_cancel_keeps_written_files(tmp_path):
    model = ScriptedModel(block("x = 1"), block("y = 2"))
    writer = ProjectWriter(tmp_path, "demo")
    stop_after_first = iter([False, False, True, True])
    result = ProjectGenerator(model, SYSTEM).generate(_plan("a.py", "b.py"), writer,
                                                       cancelled=lambda: next(stop_after_first))
    assert result.cancelled and result.status == "cancelled" and result.written == ["a.py"]


def test_file_prompt_contains_plan_and_markdown_hint(tmp_path):
    model = ScriptedModel(block("# Demo", "markdown", "````"))
    plan = _plan("calc.py", "README.md")
    ProjectGenerator(model, SYSTEM).generate_file(plan, plan.files[1])
    prompt = model.calls[0][1]["content"]
    assert "`README.md`" in prompt and "- calc.py: p" in prompt and "four backticks" in prompt


# --- writer ----------------------------------------------------------------------
def test_writer_never_reuses_an_existing_folder(tmp_path):
    first = ProjectWriter(tmp_path, "My App!")
    second = ProjectWriter(tmp_path, "My App!")
    assert first.root.name == "my-app" and second.root.name == "my-app-2"


def test_writer_rejects_escapes_and_overwrites(tmp_path):
    writer = ProjectWriter(tmp_path / "p", "demo")
    with pytest.raises(PathValidationError):
        writer.write("../outside.py", "x")
    assert not (tmp_path / "p" / "outside.py").exists()
    writer.write("a.py", "1")
    with pytest.raises(GenerationError):
        writer.write("a.py", "2")
    assert (writer.root / "a.py").read_text() == "1"
