"""Load the bundled SVG line icons, recolored at load time.

The SVG files use ``currentColor``; it is replaced with the requested color
before rendering, so one file serves every color and hover state.
"""

from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QByteArray, QRectF, QSize, Qt
from PySide6.QtGui import QGuiApplication, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from app.ui import theme


def icons_dir() -> Path:
    bundle_root = getattr(sys, "_MEIPASS", None)
    if getattr(sys, "frozen", False) and bundle_root:
        return Path(bundle_root) / "app" / "ui" / "icons"
    return Path(__file__).resolve().parent / "icons"


def available_icons() -> list[str]:
    return sorted(p.stem for p in icons_dir().glob("*.svg"))


@lru_cache(maxsize=None)
def _svg_source(name: str) -> str:
    path = icons_dir() / f"{name}.svg"
    if not path.is_file():
        raise KeyError(f"Unknown icon '{name}' (no file {path.name} in {path.parent})")
    return path.read_text(encoding="utf-8")


def _device_pixel_ratio() -> float:
    screen = QGuiApplication.primaryScreen() if QGuiApplication.instance() else None
    return screen.devicePixelRatio() if screen else 1.0


def render_pixmap(name: str, color: str, size: int) -> QPixmap:
    svg = _svg_source(name).replace("currentColor", color)
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    dpr = _device_pixel_ratio()
    pixmap = QPixmap(int(size * dpr), int(size * dpr))
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, size * dpr, size * dpr))
    painter.end()
    pixmap.setDevicePixelRatio(dpr)
    return pixmap


_icon_cache: dict[tuple[str, str, int, str | None], QIcon] = {}


def load_icon(
    name: str,
    color: str = theme.TEXT_PRIMARY,
    size: int = 20,
    hover_color: str | None = None,
) -> QIcon:
    """Return a QIcon for ``name`` drawn in ``color``. ``hover_color`` sets the Active mode."""
    key = (name, color, size, hover_color)
    if key not in _icon_cache:
        icon = QIcon()
        icon.addPixmap(render_pixmap(name, color, size), QIcon.Mode.Normal)
        if hover_color:
            icon.addPixmap(render_pixmap(name, hover_color, size), QIcon.Mode.Active)
        _icon_cache[key] = icon
    return _icon_cache[key]


def icon_size(size: int) -> QSize:
    return QSize(size, size)
