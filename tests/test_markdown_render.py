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
