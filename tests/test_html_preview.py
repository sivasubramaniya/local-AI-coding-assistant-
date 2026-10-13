"""HTML project preview: real file URLs, CSS/JS applied, offline, real-file "Open in browser",
missing-asset placeholders and reports, validator reference check. Offscreen; MOCK model."""

import json

import pytest
from PySide6.QtGui import QImage

from app.agent.asset_check import check_references, create_placeholders, scan_references
from app.validation.project_validator import validate_project

INDEX = """<!DOCTYPE html><html><head><link rel="stylesheet" href="styles.css">
<link rel="stylesheet" href="https://cdn.example.com/remote.css"></head>
<body><h1 id="title">Hi</h1>
<img src="assets/logo.png" alt="Logo"><img src="assets/profile.jpg"><img src="icons/star.svg">
<img src="https://example.com/remote.png"><img src="data:image/png;base64,AAAA">
<a href="#about">About</a><a href="mailto:me@example.com">Mail</a>
<script src="script.js"></script><script src="missing.js"></script></body></html>"""
CSS = "body { background-color: rgb(1, 2, 3); }\n.hero { background: url('img/bg.webp'); }\n@import 'theme.css';\n"
JS = "document.getElementById('title').setAttribute('data-js', 'ran');\n"


@pytest.fixture
def site(tmp_path):
    root = tmp_path / "portfolio-website"
    root.mkdir()
    (root / "index.html").write_text(INDEX, encoding="utf-8")
    (root / "styles.css").write_text(CSS, encoding="utf-8")
    (root / "script.js").write_text(JS, encoding="utf-8")
    return root


# --- reference scanning, placeholders, reports ------------------------------------------------
def test_scan_finds_local_references_and_skips_remote_data_and_anchors(site):
    targets = {(ref.source, ref.target) for ref, safe in scan_references(site) if safe}
    assert ("index.html", "styles.css") in targets and ("index.html", "assets/logo.png") in targets
    assert ("styles.css", "img/bg.webp") in targets and ("styles.css", "theme.css") in targets
    raw = " ".join(ref.raw for ref, _ in scan_references(site))
    assert "example.com" not in raw and "data:" not in raw and "#about" not in raw and "mailto" not in raw


def test_missing_images_get_placeholders_and_code_is_only_reported(site):
    report = check_references(site)
    assert sorted(r.target for r in report.missing_images) == ["assets/logo.png", "assets/profile.jpg",
                                                                "icons/star.svg", "img/bg.webp"]
    assert sorted(r.target for r in report.missing_other) == ["missing.js", "theme.css"]
    created = create_placeholders(site, report)
    assert sorted(created) == ["assets/logo.png", "assets/profile.jpg", "icons/star.svg", "img/bg.webp"]
    for raster in ("assets/logo.png", "assets/profile.jpg"):
        assert not QImage(str(site / raster)).isNull(), f"{raster} is not a loadable image"
    assert (site / "icons/star.svg").read_text(encoding="utf-8").startswith("<svg")
    assert not (site / "missing.js").exists() and not (site / "theme.css").exists()  # never invented
    summary = report.summary_markdown()
    assert "`assets/logo.png` (placeholder)" in summary and "`missing.js` (referenced in `index.html`)" in summary


def test_references_leaving_the_project_are_unsafe_and_never_created(tmp_path):
    root = tmp_path / "site"
    root.mkdir()
    (root / "index.html").write_text('<img src="../../evil.png"><img src="C:/Windows/x.png">'
                                     '<img src="/root.png"><img src="\\\\server\\share\\x.png">', encoding="utf-8")
    report = check_references(root)
    assert len(report.unsafe) == 4 and not report.missing_images
    create_placeholders(root, report)
    assert not (tmp_path / "evil.png").exists() and not (tmp_path.parent / "evil.png").exists()


def test_validator_reports_broken_references(site):
    report = validate_project(site, ["index.html", "styles.css", "script.js"])
    assert not report.ok
    problems = " ".join(report.problems())
    assert "missing image: assets/logo.png" in problems and "missing file: missing.js" in problems
    create_placeholders(site, check_references(site))
    (site / "missing.js").write_text("// ok\n")
    (site / "theme.css").write_text("/* ok */\n")
    (site / "README.md").write_text("# Site\n")
    assert validate_project(site, ["index.html"]).ok


# --- the preview widget ------------------------------------------------------------------------
@pytest.fixture
def panel(qtbot, themed_app):
    from app.ui.preview_panel import PreviewPanel, webengine_available

    if not webengine_available():
        pytest.skip("QtWebEngine not installed")
    widget = PreviewPanel(use_webengine=True)
    qtbot.addWidget(widget)
    widget.resize(900, 700)
    widget.show()
    return widget


def _files(root):
    return {p.relative_to(root).as_posix(): p.read_text(encoding="utf-8") for p in root.rglob("*") if p.is_file()}


def _run_js(qtbot, page, script):
    box = []
    page.runJavaScript(script, 0, box.append)
    qtbot.waitUntil(lambda: bool(box), timeout=10000)
    return box[0]


def test_preview_loads_the_real_file_and_applies_css_and_js(qtbot, panel, site):
    preview = panel.html_preview
    with qtbot.waitSignal(preview.view.loadFinished, timeout=20000):
        panel.set_project("portfolio-website", _files(site), site)
        panel.open_file("index.html")
    assert preview.loaded_url.toLocalFile() == (site / "index.html").resolve().as_posix()
    assert _run_js(qtbot, preview.page, "getComputedStyle(document.body).backgroundColor") == "rgb(1, 2, 3)"
    assert _run_js(qtbot, preview.page, "document.getElementById('title').getAttribute('data-js')") == "ran"


def test_preview_never_fetches_remote_urls(qtbot, panel, site):
    preview = panel.html_preview
    with qtbot.waitSignal(preview.view.loadFinished, timeout=20000):
        panel.set_project("p", _files(site), site)
        panel.open_file("index.html")
    # Chromium refuses remote loads from a file:// page (LocalContentCanAccessRemoteUrls off) before
    # they reach the interceptor; the interceptor is a second guard. Check the observable result.
    images = json.loads(_run_js(qtbot, preview.page, "JSON.stringify([...document.images].map("
                                "i => [i.src, i.complete, i.naturalWidth]))"))
    remote = [img for img in images if img[0].startswith("https://example.com")]
    assert remote == [["https://example.com/remote.png", True, 0]]  # never loaded
    sheets = json.loads(_run_js(qtbot, preview.page, "JSON.stringify([...document.styleSheets].map(s => {"
                                "let n; try { n = s.cssRules.length; } catch (e) { n = -1; } return [s.href || '', n];"
                                " }))"))
    assert any(href.endswith("styles.css") and n > 0 for href, n in sheets)  # local CSS loaded
    assert all(n <= 0 for href, n in sheets if "cdn.example.com" in href)  # remote CSS never loaded
    assert not [u for u in preview.page.offline_interceptor.blocked if not u.startswith(("http", "ws", "ftp"))]
    from PySide6.QtWebEngineCore import QWebEngineSettings

    attribute = QWebEngineSettings.WebAttribute
    assert preview.page.settings().testAttribute(attribute.LocalContentCanAccessFileUrls)
    assert not preview.page.settings().testAttribute(attribute.LocalContentCanAccessRemoteUrls)


def test_live_refresh_after_an_edit(qtbot, panel, site):
    preview = panel.html_preview
    with qtbot.waitSignal(preview.view.loadFinished, timeout=20000):
        panel.set_project("p", _files(site), site)
        panel.open_file("index.html")
    (site / "styles.css").write_text("body { background-color: rgb(9, 8, 7); }\n", encoding="utf-8")
    with qtbot.waitSignal(preview.view.loadFinished, timeout=20000):
        panel.set_project("p", _files(site), site)  # what the window does after a repair/edit
    assert panel.current_path() == "index.html"
    assert _run_js(qtbot, preview.page, "getComputedStyle(document.body).backgroundColor") == "rgb(9, 8, 7)"


def test_open_in_browser_uses_the_real_project_file(qtbot, panel, site, monkeypatch):
    import app.ui.preview_panel as preview_module

    opened = []
    monkeypatch.setattr(preview_module.QDesktopServices, "openUrl", lambda url: opened.append(url))
    panel.set_project("p", _files(site), site)
    panel.open_file("index.html")
    assert panel.html_preview.open_button.isEnabled()
    panel.html_preview.open_button.click()
    assert [u.toLocalFile() for u in opened] == [(site / "index.html").resolve().as_posix()]


def test_paths_outside_the_project_are_refused(qtbot, panel, site):
    panel.set_project("p", {"../outside.html": "<p>x</p>", "index.html": INDEX}, site)
    assert panel.file_path("../outside.html") is None
    assert panel.file_path("C:/Windows/win.ini") is None
    panel.open_file("../outside.html")
    assert panel.html_preview.file_path() is None  # shown from memory only, never loaded from disk
    assert not panel.html_preview.open_button.isEnabled()


def test_demo_content_without_a_project_cannot_be_opened(qtbot, panel):
    panel.set_project("demo", {"welcome.html": "<h1>Hi</h1>"})
    panel.open_file("welcome.html")
    assert panel.html_preview.file_path() is None and not panel.html_preview.open_button.isEnabled()
    assert "saved in the project folder" in panel.html_preview.open_button.toolTip()


# --- generation flow (MOCK model) ---------------------------------------------------------------
@pytest.mark.gui
def test_generation_creates_placeholders_and_reports_missing_code(qtbot, themed_app, tmp_config, tmp_path):
    from app.backend.ollama_client import OllamaClient
    from app.backend.status import ConnectionState
    from app.storage.chat_repository import SqliteChatRepository
    from app.ui.agent_widgets import PlanCard
    from app.ui.main_window import MainWindow
    from app.ui.message_widgets import AssistantMessage
    from tests.fake_ollama import FakeOllama

    fake = FakeOllama()
    plan = json.dumps({"project_name": "portfolio-website", "description": "A site", "language": "HTML",
                       "files": [{"path": "index.html", "purpose": "page"}, {"path": "README.md", "purpose": "docs"}],
                       "run_instructions": "open index.html", "test_command": ""})
    page = '<html><body><img src="assets/logo.png"><script src="script.js"></script></body></html>'
    repo = SqliteChatRepository.open(tmp_path / "db" / "assistant.db")
    win = MainWindow(tmp_config, store=repo, use_webengine=False,
                     client_factory=lambda: OllamaClient(tmp_config, transport=fake.transport()))
    qtbot.addWidget(win)
    win.show()
    qtbot.waitUntil(lambda: win.health().state is ConnectionState.CONNECTED, timeout=5000)
    fake.replies = [plan]
    with qtbot.waitSignal(win.streamFinished, timeout=10000):
        win.submit_prompt("make a portfolio website", project_mode=True)
    fake.replies = [f"```html\n{page}\n```", "````markdown\n# Portfolio\n````"]
    with qtbot.waitSignal(win.streamFinished, timeout=10000):
        [w for w in win.chat_view.items if isinstance(w, PlanCard)][-1].apply_button.click()
    root = tmp_config.projects_dir / "portfolio-website"
    assert not QImage(str(root / "assets" / "logo.png")).isNull()  # placeholder created
    assert not (root / "script.js").exists()  # missing code is reported, not invented
    summary = [w for w in win.chat_view.items if isinstance(w, AssistantMessage)][-1].text()
    assert "`assets/logo.png` (placeholder)" in summary
    assert "`script.js` (referenced in `index.html`)" in summary
    assert "missing file: script.js" in summary  # the project check lists it too
    plan_prompt = fake.chat_bodies()[0]["messages"][1]["content"]
    assert "inline SVG or CSS" in plan_prompt
    win.close()
    repo.close()
