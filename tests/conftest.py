import os

# GUI tests run headless. Must be set before pytest-qt creates the QApplication.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# The offscreen platform has no fonts of its own (text renders as boxes in screenshots).
if os.name == "nt":
    os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"))

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


def pytest_addoption(parser):
    parser.addoption("--offline-guard", action="store_true",
                     help="block every non-loopback socket for the whole test run (offline verification)")


@pytest.fixture(autouse=True)
def _offline_guard(request):
    """With --offline-guard, every test runs with non-loopback networking blocked (restored after each test)."""
    if not request.config.getoption("--offline-guard"):
        yield None
        return
    from tests.offline_guard import block_network

    with block_network() as attempts:
        yield attempts
    assert not attempts, f"{request.node.nodeid} tried to reach the network: {attempts}"


def pytest_sessionfinish(session, exitstatus):
    """Join any worker threads before Qt and Python shut down (avoids a Qt abort at exit)."""
    import sys

    if "app.ui.workers" in sys.modules:
        sys.modules["app.ui.workers"].shutdown_workers(timeout_ms=5000)
