"""The pytest setup: markers are registered and real-model tests are skipped by default."""

import configparser
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILTIN_MARKS = {"parametrize", "skip", "skipif", "xfail", "usefixtures", "filterwarnings"}


def _pytest_ini() -> configparser.SectionProxy:
    parser = configparser.ConfigParser()
    parser.read(ROOT / "pytest.ini", encoding="utf-8")
    return parser["pytest"]


def _registered_markers() -> set[str]:
    lines = _pytest_ini()["markers"].strip().splitlines()
    return {line.split(":", 1)[0].strip() for line in lines if line.strip()}


def test_markers_registered_and_integration_skipped_by_default():
    ini = _pytest_ini()
    assert {"gui", "integration"} <= _registered_markers()
    assert '-m "not integration"' in ini["addopts"]
    assert ini["testpaths"].strip() == "tests"


def test_every_marker_used_in_tests_is_registered():
    used = set()
    for path in (ROOT / "tests").glob("*.py"):
        used |= set(re.findall(r"pytest\.mark\.([A-Za-z_]\w*)", path.read_text(encoding="utf-8")))
    unregistered = used - BUILTIN_MARKS - _registered_markers()
    assert not unregistered, f"register these in pytest.ini: {sorted(unregistered)}"
