"""Screenshot of the app's HTML preview panel showing a project's index.html (real Windows display).

Usage:
    .\\venv\\Scripts\\python.exe scripts\\preview_screenshot.py PROJECT_DIR OUT.png [--fix-assets]

--fix-assets runs the same step the app runs after generation: missing images become grey
placeholders (missing CSS/JS are only reported). The preview loads the real file, offline.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("project", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--fix-assets", action="store_true")
    args = parser.parse_args()

    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication

    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app = QApplication(sys.argv[:1])
    from app.agent.asset_check import check_references, create_placeholders
    from app.agent.coding_agent import read_project_files
    from app.ui.preview_panel import PreviewPanel
    from app.ui.theme import apply_theme

    apply_theme(app)
    root = args.project.resolve()
    if args.fix_assets:
        report = check_references(root)
        created = create_placeholders(root, report)
        print("placeholders:", created, "| still missing:", [r.target for r in report.missing_other])
    panel = PreviewPanel(use_webengine=True)
    panel.resize(1200, 860)
    panel.show()
    panel.set_project(root.name, read_project_files(root), root)
    panel.open_file("index.html")
    QTest.qWait(4000)  # load, styles, scripts, paint
    result = []
    panel.html_preview.page.runJavaScript(
        "JSON.stringify({bg: getComputedStyle(document.body).backgroundColor,"
        " font: getComputedStyle(document.body).fontFamily,"
        " sheets: [...document.styleSheets].map(s => { try { return [s.href, s.cssRules.length]; }"
        " catch (e) { return [s.href, -1]; } }),"
        " images: [...document.images].map(i => [i.getAttribute('src'), i.naturalWidth])})", 0, result.append)
    QTest.qWait(1000)
    print("page:", json.loads(result[0]) if result and result[0] else result)
    panel.html_preview.page.runJavaScript("window.scrollTo(0, 0)")
    QTest.qWait(800)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    ok = panel.grab().save(str(args.out))
    print("saved" if ok else "FAILED to save", args.out)
    panel.close()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
