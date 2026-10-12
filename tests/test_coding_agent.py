"""Edit flow: change parsing, unified diffs, confirmation-gated writes with backups. MOCK only."""

import pytest

from app.agent.coding_agent import (
    EDIT_INSTRUCTIONS,
    FileChange,
    apply_changes,
    apply_unified_diff,
    build_context,
    list_project_files,
    parse_changes,
    prepare_changes,
    read_project_files,
)
from app.errors import PatchError, PathValidationError

ORIGINAL = "def add(a, b):\n    return a - b\n\n\nprint(add(1, 2))\n"
FIXED = "def add(a, b):\n    return a + b\n\n\nprint(add(1, 2))\n"
DIFF = """--- a/calc.py
+++ b/calc.py
@@ -1,2 +1,2 @@
 def add(a, b):
-    return a - b
+    return a + b
"""


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "calc"
    root.mkdir()
    (root / "calc.py").write_text(ORIGINAL, encoding="utf-8")
    (root / "README.md").write_text("# Calc\n", encoding="utf-8")
    (root / "__pycache__").mkdir()
    (root / "__pycache__" / "calc.cpython-312.pyc").write_bytes(b"\0\1")
    (root / "calc.py.bak-20260101-000000").write_text("old", encoding="utf-8")
    return root


def test_parse_full_file_and_diff_blocks():
    answer = ("The bug is the minus sign.\n```python path=calc.py\n" + FIXED + "```\n"
              "And a test:\n```python path=tests/test_calc.py\nfrom calc import add\n```\n"
              "Or as a diff:\n```diff\n" + DIFF + "```\n"
              "```python\nprint('no path: ignored')\n```")
    changes = {c.path: c for c in parse_changes(answer)}
    assert set(changes) == {"calc.py", "tests/test_calc.py"}
    assert changes["calc.py"].diff is not None  # the later diff block wins for calc.py
    assert changes["tests/test_calc.py"].content == "from calc import add\n"


def test_parse_changes_drops_unsafe_paths():
    answer = "```python path=../../evil.py\nx\n```\n```diff\n--- a/C:/x\n+++ b/C:/x\n@@ -1 +1 @@\n-a\n+b\n```"
    assert parse_changes(answer) == []


def test_apply_unified_diff():
    assert apply_unified_diff(ORIGINAL, DIFF) == FIXED


def test_diff_that_does_not_match_is_refused():
    with pytest.raises(PatchError):
        apply_unified_diff("something else\n", DIFF)
    with pytest.raises(PatchError):
        apply_unified_diff(ORIGINAL, "--- a/x\n+++ b/x\n")


def test_prepare_then_apply_with_backup(project):
    pending, problems = prepare_changes(project, [FileChange("calc.py", diff=DIFF),
                                                  FileChange("tests/test_calc.py", content="import calc\n")])
    assert problems == {}
    assert [(c.path, c.is_new) for c in pending] == [("calc.py", False), ("tests/test_calc.py", True)]
    assert "-    return a - b" in pending[0].diff_text() and "+    return a + b" in pending[0].diff_text()
    assert (project / "calc.py").read_text() == ORIGINAL  # nothing written before confirmation

    written = apply_changes(project, pending)
    assert written == ["calc.py", "tests/test_calc.py"]
    assert (project / "calc.py").read_text() == FIXED
    backups = [p for p in project.glob("calc.py.bak-*") if p.name != "calc.py.bak-20260101-000000"]
    assert len(backups) == 1 and backups[0].read_text() == ORIGINAL
    assert (project / "tests" / "test_calc.py").read_text() == "import calc\n"


def test_prepare_reports_problems_and_skips_no_ops(project):
    pending, problems = prepare_changes(project, [
        FileChange("calc.py", content=ORIGINAL),  # unchanged -> skipped
        FileChange("missing.py", diff=DIFF),  # diff for a missing file
        FileChange("README.md", diff=DIFF),  # does not match
    ])
    assert pending == []
    assert set(problems) == {"missing.py", "README.md"}


def test_apply_refuses_when_file_changed_on_disk(project):
    pending, _ = prepare_changes(project, [FileChange("calc.py", content=FIXED)])
    (project / "calc.py").write_text("edited meanwhile\n", encoding="utf-8")
    with pytest.raises(PatchError):
        apply_changes(project, pending)
    assert (project / "calc.py").read_text() == "edited meanwhile\n"


def test_apply_rejects_traversal_even_if_constructed_directly(project):
    from app.agent.coding_agent import PendingChange

    with pytest.raises(PathValidationError):
        apply_changes(project, [PendingChange("../escape.py", None, "x")])
    assert not (project.parent / "escape.py").exists()


def test_project_listing_skips_caches_backups_and_binaries(project):
    assert sorted(list_project_files(project)) == ["README.md", "calc.py"]
    assert set(read_project_files(project)) == {"README.md", "calc.py"}


def test_build_context_puts_mentioned_files_first_and_respects_budget(project):
    files = {"big.py": "x" * 5000, "calc.py": ORIGINAL, "README.md": "# Calc\n"}
    context = build_context("why does calc.py return the wrong value?", "calc", files, [], max_chars=1500)
    assert "This chat is about the project 'calc'" in context
    assert context.index("File calc.py") < context.index("File README.md")
    assert "File big.py" not in context and "Not shown (too large for the context): big.py" in context
    assert EDIT_INSTRUCTIONS in context


def test_build_context_with_attachment_only():
    context = build_context("what does this do?", None, {}, [("app.py", "print(1)")], max_chars=1000)
    assert "Attached file app.py" in context and EDIT_INSTRUCTIONS not in context



# --- path labels (format from the system prompt; found by the REAL Java sample run) ---------
KNOWN = ["src/calculator/Calculator.java", "src/calculator/CalculatorTest.java", "README.md"]


@pytest.mark.parametrize("label", [
    "src/calculator/Calculator.java",
    "**src/calculator/Calculator.java**",
    "`src/calculator/Calculator.java`",
    "### src/calculator/Calculator.java",
    "File: src/calculator/Calculator.java",
    "Calculator.java",  # unique file name -> its known path
    "src\\calculator\\Calculator.java",
])
def test_path_on_the_line_before_the_block(label):
    answer = f"Here is the fix.\n\n{label}\n```java\nclass Calculator {{}}\n```\n"
    changes = parse_changes(answer, KNOWN)
    assert [(c.path, c.content) for c in changes] == [("src/calculator/Calculator.java", "class Calculator {}\n")]


def test_first_line_path_comment():
    answer = "```java\n// src/calculator/CalculatorTest.java\nclass CalculatorTest {}\n```"
    assert [c.path for c in parse_changes(answer, KNOWN)] == ["src/calculator/CalculatorTest.java"]


def test_unlabelled_and_command_blocks_are_ignored():
    answer = ("Compile with:\n```powershell\njavac -d out src/calculator/Calculator.java\n```\n"
              "Example:\n```java\nnew Calculator().add(1, 2);\n```\n"
              "run.ps1\n```powershell\nRemove-Item x\n```")
    assert parse_changes(answer, KNOWN) == []


def test_unsafe_label_is_ignored():
    answer = "../../evil.java\n```java\nclass Evil {}\n```"
    assert parse_changes(answer, KNOWN) == []
