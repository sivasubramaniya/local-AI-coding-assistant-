## Phase 1 Report — Test & Dev Setup

### Summary
`python -m pytest` now works with no extra flags. `pytest.ini` registers the `gui` and
`integration` markers, sets `testpaths = tests` and skips the real-model `integration` tests by
default. Passing `-m integration` overrides that default. Runtime and test dependencies are written down
with pinned versions that match the venv. Nothing was installed or upgraded. `CLAUDE.md` records the
project rules, and the README has a "Running tests" section. No app code was changed.

### Files Created
- `pytest.ini`: testpaths, `addopts = -m "not integration"`, `gui` / `integration` markers.
- `requirements.txt`: the 4 runtime packages `main.py --check` verifies, pinned as installed:
  PySide6 6.12.0, httpx 0.28.1, Pygments 2.21.0, Markdown 3.11. PySide6 6.12.0 itself requires
  PySide6_WebEngine / PySide6_Pdf, so the preview's WebEngine comes with it.
- `requirements-dev.txt`: `-r requirements.txt`, pytest 9.1.1, pytest-qt 4.5.0.
- `CLAUDE.md`: the project rules: local Ollama only, no cloud APIs, fixed model name, theme tokens in
  `app/ui/theme.py`, Dark must stay unchanged, how to run tests, the phase workflow.
- `tests/test_dev_setup.py`: 2 tests. One checks that the markers are registered and integration is
  skipped by default; the other checks that every marker used in `tests/` is registered.
- `docs/reports/PHASE_1_REPORT.md`

### Files Modified
- `README.md`: `## Tests` became `## Running tests`, with the `requirements-dev.txt` install line, plain
  `python -m pytest` and `-m integration`. The `--cov=app` line was removed, as agreed.
- `PLAN.md`: Phase 0 marked approved; Phase 1 added and ticked; Changelog row.

### Commands Run
- `python -m pytest -q --collect-only` / `-m "not integration"`: baseline 693 collected;
  680 passed, 2 skipped, 11 deselected, 40 warnings (mostly unknown `gui` mark).
- `python -m pytest -v` (no flags)
- `python -m pytest -m integration --collect-only -q`

### Test Results
- `python -m pytest -v`: `682 passed, 2 skipped, 11 deselected in 68.94s`. 0 failed, no warnings
  summary, 0 "Unknown pytest.mark" lines. Header shows `configfile: pytest.ini`, `testpaths: tests`.
- `python -m pytest -m integration --collect-only -q`: `11/695 tests collected (684 deselected)`.
  The 11: test_integration_app (5), test_integration_fast (2), test_integration_generator (1),
  test_integration_ollama (3).

### Mock vs Real
- All tests that ran use mocks (`FakeOllama`) or no model. The 11 real-model tests were only collected,
  not run.

### Known Issues / Limitations
- A plain `python -m pytest` now creates `.pytest_cache/` in the project folder (pytest's normal
  behavior). The project has no `.gitignore` because it is not a git repository.
- The README still links `CHANGELOG.md`, `LICENSE` and `docs/*.md` files that are not in this checkout
  (not changed; outside this phase).

### Blockers
None.

### Next Phase Preview
- Awaiting your direction; no next phase is defined in PLAN.md.
