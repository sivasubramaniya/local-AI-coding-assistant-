"""Capture Light and Dark screenshots of the main views (offscreen, demo data, no model).

Usage:  .\\venv\\Scripts\\python.exe scripts\\theme_screenshots.py
Writes docs/screenshots/theme-{light,dark}-{chat,preview,settings,plan}.png
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"))

from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app.agent.project_generator import PlannedFile, ProjectPlan  # noqa: E402
from app.config import load_config  # noqa: E402
from app.ui import theme  # noqa: E402
from app.ui.agent_widgets import PlanCard  # noqa: E402
from app.ui.dialogs import SettingsDialog  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402

OUT = ROOT / "docs" / "screenshots"
PLAN = ProjectPlan("todo-cli", "A simple command-line to-do app with tests.", "Python",
                   (PlannedFile("todo.py", "Main application logic"), PlannedFile("tests/test_todo.py", "Unit tests"),
                    PlannedFile("README.md", "Build, run and test instructions")),
                   "python todo.py", "python -m pytest -q")


def settle() -> None:
    QTest.qWait(400)


def main() -> int:
    app = QApplication(sys.argv[:1])
    theme.apply_theme(app)
    tmp = Path(tempfile.mkdtemp(prefix="laa-theme-"))
    # a neutral export folder, so no user name can appear in the Settings screenshot
    config = load_config({"LAA_DATA_DIR": str(tmp / "data"), "LAA_EXPORT_DIR": r"D:\laa-demo\export"})
    OUT.mkdir(parents=True, exist_ok=True)
    for mode in ("dark", "light"):
        win = MainWindow(config, demo_mode=True, health_checks=False, use_webengine=False)
        win.resize(1600, 900)
        win.show()
        win.apply_theme_mode(mode)
        win.close_preview()
        settle()
        win.chat_view.scroll_to_bottom()
        settle()
        win.grab().save(str(OUT / f"theme-{mode}-chat.png"))

        win.open_file("server.py")
        win.preview.show_tab("code")
        settle()
        win.grab().save(str(OUT / f"theme-{mode}-preview.png"))
        win.close_preview()

        card = PlanCard(PLAN, fast_mode=True)
        win.chat_view.add_card(card)
        settle()
        win.chat_view.scroll_to_bottom()
        settle()
        win.grab().save(str(OUT / f"theme-{mode}-plan.png"))

        dialog = SettingsDialog(str(config.export_dir), 60, win, model_name=config.model_name,
                                fast_model_name=config.fast_model_name, theme_mode=mode)
        dialog.resize(620, dialog.sizeHint().height())
        dialog.show()
        settle()
        dialog.grab().save(str(OUT / f"theme-{mode}-settings.png"))
        dialog.close()
        win.close()
        print(f"saved theme-{mode}-*.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
