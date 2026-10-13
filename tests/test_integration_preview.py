"""REAL (Fast mode, qwen2.5-coder-7b): generate a small portfolio website, then check that every
local reference exists (after the app's placeholder step) and that the preview applies its CSS.

Run with: python -m pytest -m integration tests/test_integration_preview.py -v
Skips with the reason when Ollama or the 7B model is missing.
"""

import json

import pytest

from app.agent.asset_check import check_references, create_placeholders
from app.agent.coding_agent import read_project_files
from app.agent.project_generator import ProjectGenerator, ProjectWriter
from app.backend.ollama_client import OllamaClient, create_command
from app.config import load_config
from app.errors import AppError, ModelNotFoundError
from app.prompts import load_system_prompt

pytestmark = [pytest.mark.integration, pytest.mark.gui]

REQUEST = ("A small static portfolio website: index.html, styles.css and script.js. The page has a header "
           "with a logo and navigation, an About section with a profile picture, a Projects section and a "
           "contact form. Keep it short.")


@pytest.fixture(scope="module")
def fast_client(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("preview-real")
    config = load_config({"LAA_DATA_DIR": str(tmp), "LAA_EXPORT_DIR": str(tmp), "LAA_STREAM_READ_TIMEOUT_S": "900"})
    client = OllamaClient(config, model=config.fast_model_name)
    try:
        client.ensure_ready()
    except ModelNotFoundError:
        client.close()
        pytest.skip(f"fast model missing; run: {create_command(config, config.fast_model_name)}")
    except AppError as exc:
        client.close()
        pytest.skip(f"Ollama not available: {exc.message}")
    yield client
    client.close()


def test_real_portfolio_has_all_local_references_and_styled_preview(qtbot, themed_app, fast_client, tmp_path):
    from app.ui.preview_panel import PreviewPanel, webengine_available

    generator = ProjectGenerator(lambda m: "".join(fast_client.stream_chat(m)), load_system_prompt())
    plan = generator.make_plan(REQUEST)
    writer = ProjectWriter(tmp_path / "projects", plan.project_name)
    result = generator.generate(plan, writer)
    assert "index.html" in result.written, f"no index.html: written={result.written} failed={result.failed}"

    report = check_references(writer.root, result.written)
    placeholders = create_placeholders(writer.root, report)
    print(f"\nwritten={result.written} failed={result.failed} placeholders={placeholders} "
          f"missing_code={[r.target for r in report.missing_other]} unsafe={[r.raw for r in report.unsafe]}")
    after = check_references(writer.root)
    assert not after.missing_images, "every missing image must have a placeholder"
    assert not after.missing_other, f"the page references code that was not generated: {after.problems()}"

    if not webengine_available():
        pytest.skip("QtWebEngine not installed: references verified, styled preview not checked")
    panel = PreviewPanel(use_webengine=True)
    qtbot.addWidget(panel)
    panel.resize(1200, 860)
    panel.show()
    with qtbot.waitSignal(panel.html_preview.view.loadFinished, timeout=30000):
        panel.set_project(plan.project_name, read_project_files(writer.root), writer.root)
        panel.open_file("index.html")
    box = []
    panel.html_preview.page.runJavaScript(
        "JSON.stringify([...document.styleSheets].map(s => { try { return [s.href || '', s.cssRules.length]; }"
        " catch (e) { return [s.href || '', -1]; } }))", 0, box.append)
    qtbot.waitUntil(lambda: bool(box), timeout=10000)
    sheets = json.loads(box[0])
    local = [(href, n) for href, n in sheets if href.startswith("file:")]
    if any(f.endswith(".css") for f in result.written):
        assert local and all(n > 0 for _, n in local), f"local stylesheets not applied: {sheets}"
