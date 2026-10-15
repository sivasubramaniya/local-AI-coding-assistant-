"""Windows 11 window-frame effects for the Glass theme: dark title bar and Mica frame.

Uses DwmSetWindowAttribute through ctypes (no extra packages). On other platforms, the
offscreen test platform or older Windows builds, the functions return False and never raise.
"""

from __future__ import annotations

import ctypes
import logging
import sys

logger = logging.getLogger(__name__)

DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_SYSTEMBACKDROP_TYPE = 38  # Windows 11 22H2 and later
DWMSBT_AUTO = 0
DWMSBT_MAINWINDOW = 2  # Mica
GLASS_FRAME_PROPERTY = "glassFrame"


def supported() -> bool:
    """True only for real windows on Windows (not the offscreen/minimal Qt platforms)."""
    if sys.platform != "win32":
        return False
    try:
        from PySide6.QtGui import QGuiApplication

        return QGuiApplication.platformName() == "windows"
    except Exception:  # noqa: BLE001 - never raise from a cosmetic feature
        return False


def _set_attribute(hwnd: int, attribute: int, value: int) -> bool:
    data = ctypes.c_int(value)
    result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
        ctypes.c_void_p(hwnd), ctypes.c_uint(attribute), ctypes.byref(data), ctypes.sizeof(data)
    )
    return result == 0  # S_OK


def _system_is_dark() -> bool:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication

    return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark


def apply_window_effects(window, enabled: bool = True) -> bool:
    """Turn the dark title bar + Mica frame on (Glass) or back to the system default.

    Returns True when Windows accepted the dark-title-bar attribute. A window that never
    had the effect is left untouched when ``enabled`` is False, so Dark looks as before.
    """
    if not supported():
        return False
    try:
        if not enabled and not window.property(GLASS_FRAME_PROPERTY):
            return False
        hwnd = int(window.winId())
        dark, backdrop = (1, DWMSBT_MAINWINDOW) if enabled else (int(_system_is_dark()), DWMSBT_AUTO)
        dark_ok = _set_attribute(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, dark)
        if not _set_attribute(hwnd, DWMWA_SYSTEMBACKDROP_TYPE, backdrop):
            logger.debug("Mica backdrop not available on this Windows build")
        window.setProperty(GLASS_FRAME_PROPERTY, enabled)
        return dark_ok
    except Exception as exc:  # noqa: BLE001 - never raise from a cosmetic feature
        logger.debug("Window effects unavailable: %s", exc)
        return False
