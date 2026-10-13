# PyInstaller spec for Local AI Assistant (onedir, windowed).
# Build from the project folder:
#     .\venv\Scripts\pyinstaller packaging\LocalAIAssistant.spec --noconfirm
# Output: dist\LocalAIAssistant\LocalAIAssistant.exe
#
# Bundled: the coding system prompt, the SVG icons, the Ollama Modelfile and the docs.
# Not bundled: tests, the model (install it with Ollama), user data
# (chats live in %LOCALAPPDATA%\LocalAIAssistant).
#
# Size: PySide6 ships all of Qt. The app only uses QtCore, QtGui, QtWidgets, QtSvg and
# QtWebEngine (the HTML file preview). QT_DLLS below is the DLL import closure of those
# modules (computed with PyInstaller's bindepend); everything else is filtered out.

from pathlib import Path

ROOT = Path(SPECPATH).parent  # noqa: F821 - SPECPATH is provided by PyInstaller

PYSIDE_MODULES = {"QtCore", "QtGui", "QtWidgets", "QtSvg", "QtWebEngineCore", "QtWebEngineWidgets",
                  "QtNetwork", "QtPrintSupport", "QtWebChannel"}
QT_DLLS = {"Qt6Core", "Qt6Gui", "Qt6Network", "Qt6OpenGL", "Qt6Positioning", "Qt6PrintSupport", "Qt6Qml",
           "Qt6QmlMeta", "Qt6QmlModels", "Qt6QmlWorkerScript", "Qt6Quick", "Qt6QuickWidgets", "Qt6Svg",
           "Qt6WebChannel", "Qt6WebEngineCore", "Qt6WebEngineWidgets", "Qt6Widgets"}
KEEP_PLUGINS = {"platforms", "styles", "imageformats", "iconengines", "tls", "networkinformation", "generic",
                "platforminputcontexts", "printsupport"}
KEEP_LOCALES = {"en-US.pak"}

datas = [
    (str(ROOT / "app" / "prompts" / "coding_system_prompt.txt"), "app/prompts"),
    (str(ROOT / "app" / "ui" / "icons"), "app/ui/icons"),
    (str(ROOT / "ollama" / "Modelfile"), "docs"),
    (str(ROOT / "ollama" / "Modelfile.fast"), "docs"),
    (str(ROOT / "docs" / "INSTALL.md"), "docs"),
    (str(ROOT / "docs" / "OFFLINE.md"), "docs"),
    (str(ROOT / "README.md"), "docs"),
]


def keep(dest: str) -> bool:
    """False for Qt files the app never loads."""
    parts = dest.replace("\\", "/").split("/")
    if parts[0] != "PySide6" or len(parts) < 2:
        return True
    name = parts[-1]
    if len(parts) == 2:
        if name.startswith("Qt6") and name.endswith(".dll"):
            return name[:-4] in QT_DLLS
        if name.startswith("Qt") and name.endswith(".pyd"):
            return name[:-4] in PYSIDE_MODULES
        if name.startswith("Qt") and name.endswith(".pyi"):
            return False
        return True
    folder = parts[1]
    if folder == "qml":
        return False  # the app has no QML
    if folder == "translations":
        return len(parts) == 4 and parts[2] == "qtwebengine_locales" and name in KEEP_LOCALES
    if folder == "resources":
        return "devtools" not in name
    if folder == "plugins":
        return parts[2] in KEEP_PLUGINS
    return True


a = Analysis(  # noqa: F821
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=["PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineCore"],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tests", "pytest", "pytestqt", "_pytest", "pytest_cov", "coverage", "PyInstaller", "tkinter",
              "unittest", "pydoc", "doctest", "lib2to3", "idlelib",
              "PySide6.QtQml", "PySide6.QtQuick", "PySide6.Qt3DCore", "PySide6.QtCharts", "PySide6.QtMultimedia",
              "PySide6.QtPdf", "PySide6.QtOpenGL", "PySide6.QtTest", "PySide6.QtSql", "PySide6.QtDesigner"],
    noarchive=False,
)
before = len(a.binaries) + len(a.datas)
a.binaries = [entry for entry in a.binaries if keep(entry[0])]
a.datas = [entry for entry in a.datas if keep(entry[0])]
print(f"[LocalAIAssistant.spec] Qt filter: {before} -> {len(a.binaries) + len(a.datas)} files")
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
