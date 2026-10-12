from app.ui.markdown_render import CodeBlock, render_markdown, split_fenced


def test_split_closed_block():
    parts = split_fenced("Intro\n```python\nprint(1)\n```\nOutro")
    assert parts[0] == "Intro"
    assert parts[1] == CodeBlock("python", "print(1)", closed=True)
    assert parts[2] == "Outro"


def test_split_unclosed_block_while_streaming():
    parts = split_fenced("Text\n```js\nconst a = 1;")
    assert parts[-1] == CodeBlock("js", "const a = 1;", closed=False)


def test_markdown_inside_code_is_not_rendered():
    rendered = render_markdown("```\n**not bold**\n```")
    assert "<strong>" not in rendered.html
    assert rendered.code_blocks == ["**not bold**"]


def test_render_features():
    md = "### Title\n\n1. one\n2. two\n\nUse `pip` and **bold** and [link](https://example.com).\n\n```python\nx = 1\n```"
    rendered = render_markdown(md, code_font="Consolas")
    html = rendered.html
    assert "<h3>" in html and "<ol>" in html and "<strong>bold</strong>" in html
    assert "<code>pip</code>" in html
    assert 'href="https://example.com"' in html
    assert 'href="copy:0"' in html and ">python<" in html
    assert "Consolas" in html
    assert rendered.code_blocks == ["x = 1"]


def test_unknown_language_falls_back_to_plain_text():
    rendered = render_markdown("```nosuchlang\nabc\n```")
    assert "abc" in rendered.html



def test_longer_fences_keep_a_clean_language_label():
    """Regression (REAL app screenshot): command output in ````text fences showed '`text'."""
    from app.ui.markdown_render import render_markdown, split_fenced

    parts = split_fenced("Output:\n````text\n6 passed\n````\nDone")
    block = [p for p in parts if not isinstance(p, str)][0]
    assert block.language == "text" and block.code == "6 passed"
    assert "`text" not in render_markdown("````text\nok\n````").html


def test_plan_markdown_renders_files_as_a_list():
    """Regression (REAL app screenshot): the plan's file list rendered as one paragraph."""
    from app.agent.project_generator import PlannedFile, ProjectPlan
    from app.ui.markdown_render import render_markdown

    plan = ProjectPlan("todo", "A to-do app.", "Python", (PlannedFile("todo.py", "main"),
                                                         PlannedFile("test_todo.py", "tests")),
                       "python todo.py", "python -m pytest")
    html = render_markdown(plan.to_markdown()).html
    assert html.count("<li") == 2
    assert "Run: python todo.py" in html and "Test:" in html



def test_generation_summary_keeps_separate_paragraphs(tmp_path):
    """Regression (REAL app screenshot): 'Folder:' and 'Run/Test' merged into the title line."""
    from app.agent.project_generator import GenerationResult, PlannedFile, ProjectPlan
    from app.ui.markdown_render import render_markdown

    plan = ProjectPlan("todo", "d", "Python", (PlannedFile("a.py", "x"), PlannedFile("b.py", "y")),
                       "python a.py", "python -m pytest")
    result = GenerationResult(plan, tmp_path, written=["a.py"], failed={"b.py": "no block"})
    html = render_markdown(result.summary_markdown()).html
    assert html.count("<p") >= 6 and html.count("<li") == 1
