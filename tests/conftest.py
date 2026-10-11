import os

# GUI tests run headless. Must be set before pytest-qt creates the QApplication.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

from app.config import load_config  # noqa: E402


@pytest.fixture
def tmp_config(tmp_path):
    """A config whose folders all live under pytest's tmp_path."""
    return load_config({"LAA_DATA_DIR": str(tmp_path / "data"), "LAA_EXPORT_DIR": str(tmp_path / "export")})


@pytest.fixture
def themed_app(qapp):
    """The QApplication with the real theme applied (also proves the QSS builds)."""
    from app.ui.theme import apply_theme

    apply_theme(qapp)
    return qapp
