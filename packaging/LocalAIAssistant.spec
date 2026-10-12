# PyInstaller spec for Local AI Assistant (onedir, windowed).
# Build from the project folder:
#     .\venv\Scripts\pyinstaller packaging\LocalAIAssistant.spec --noconfirm
# Output: dist\LocalAIAssistant\LocalAIAssistant.exe
#
# Bundled: the coding system prompt, the SVG icons, the Ollama Modelfile and the docs.
# Not bundled: tests, the model (install it with Ollama), user data
# (chats live in %LOCALAPPDATA%\LocalAIAssistant).

from pathlib import Path

ROOT = Path(SPECPATH).parent  # noqa: F821 - SPECPATH is provided by PyInstaller

datas = [
    (str(ROOT / "app" / "prompts" / "coding_system_prompt.txt"), "app/prompts"),
    (str(ROOT / "app" / "ui" / "icons"), "app/ui/icons"),
    (str(ROOT / "ollama" / "Modelfile"), "docs"),
    (str(ROOT / "docs" / "INSTALL.md"), "docs"),
    (str(ROOT / "docs" / "OFFLINE.md"), "docs"),
    (str(ROOT / "README.md"), "docs"),
]

a = Analysis(  # noqa: F821
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=["PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineCore"],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tests", "pytest", "pytestqt", "_pytest", "coverage", "pytest_cov", "tkinter", "unittest.mock"],
    noarchive=False,
)
pyz = PYZ(a.pure)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LocalAIAssistant",
    debug=False,
    strip=False,
    upx=False,  # UPX-packed files trigger more antivirus false positives
    console=False,  # windowed; --check attaches to the calling terminal and writes logs\check.txt
)

coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="LocalAIAssistant",
)
