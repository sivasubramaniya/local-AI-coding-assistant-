## Phase 2 Report — Repo Cleanup

### Summary
Generated files are now covered by `.gitignore`, and the README has no broken relative links. The project
folder is **not a git repository**, so there was nothing to untrack (2.2). The tracked-files test skips
until git is set up. All 10 missing README targets were fixed as agreed. Created: `CHANGELOG.md`,
`LICENSE` (MIT, Sivasubramaniyan T, 2026), `docs/OFFLINE.md`, `docs/TEST_REPORT.md` and two demo-mode
screenshots. Replaced: the `docs/INSTALL.md` link, now pointing to the README's Requirements section.
Removed: the `docs/PERFORMANCE.md` link and the second "Full list" `TEST_REPORT` link. The stray UTF-16
line at the end of the README is gone. No app code changed; nothing was deleted from disk.

### Files Created
- `.gitignore`:
  - `__pycache__/`, `*.py[cod]`, `.pytest_cache/`, `venv/`, `.venv/`, `build/`, `dist/`
  - `*.spec` with `!packaging/LocalAIAssistant.spec`
  - `logs/`, `*.log`
  - an in-repo data dir (`/data/`, `*.db*`)
  - root-level `--screenshot` captures (`/*.png`)
- `LICENSE`: standard MIT text.
- `CHANGELOG.md`: built from the PLAN.md Changelog table.
- `docs/OFFLINE.md`: what the app enforces, the automated offline tests and an 8-step Wi-Fi-off manual check.
- `docs/TEST_REPORT.md`: MOCK results and REAL status (11 tests, not run here), kept separate; how to
  regenerate real-model screenshots.
- `docs/screenshots/demo-dark.png`, `docs/screenshots/demo-glass.png`: `--screenshot` demo captures.
- `tests/test_repo_hygiene.py`: 10 tests (relative links in README, CHANGELOG and docs; README clean
  UTF-8; `.gitignore` patterns; no tracked bytecode, skipped without git).
- `docs/reports/PHASE_2_REPORT.md`

### Files Modified
- `README.md`: Dark/Glass demo image table with a "demo-mode captures" caption linking TEST_REPORT;
  INSTALL / PERFORMANCE / "Full list" links fixed as agreed; stray UTF-16 tail removed (UTF-8, CRLF kept).
- `PLAN.md`: Phase 1 marked approved; Phase 2 added and ticked; Changelog row.

### Broken links found → fix
| Link | Fix |
|---|---|
| `CHANGELOG.md` | created |
| `LICENSE` | created (MIT) |
| `docs/INSTALL.md` | replaced by `#requirements` (packaged-app pointer dropped) |
| `docs/OFFLINE.md` | created |
| `docs/PERFORMANCE.md` | link removed (numbers stay in the README) |
| `docs/TEST_REPORT.md` (×2) | created; the "Full list" link removed |
| `docs/screenshots/03, 05, 06, 07.png` | replaced by `demo-dark.png` / `demo-glass.png` |

### Commands Run
- `git rev-parse --show-toplevel`: not a git repository.
- `python -m pytest -q`: baseline 682 passed, 2 skipped, 11 deselected.
- `python main.py --screenshot docs/screenshots/demo-dark.png --theme dark` and `... demo-glass.png --theme glass`
  (logs went to a temporary data dir, not `%LOCALAPPDATA%`).
- `python -m pytest -v`

### Test Results
`691 passed, 3 skipped, 11 deselected in 69.84s`: 0 failed, no warnings. The new skip is
`test_no_compiled_python_is_tracked` (not a git repository).

### Mock vs Real
- No model involved. The screenshots are demo mode (canned answers). The 11 real-model tests were not run.

### Known Issues / Limitations
- The real-model screenshots (`03-answer.png` etc.) are not in this checkout. Running
  `python -m pytest -m integration tests/test_integration_app.py` writes them to `docs/screenshots/`.
- `__pycache__/` and `.pytest_cache/` still exist on disk. They are ignored, not deleted (as required).
- `scripts/benchmark.py` and `scripts/run_java_sample.py` mention `docs/perf/` and `docs/samples/`, which
  are not in this checkout. They are not README links, so they were left as is.
- CHANGELOG.md and the PLAN.md Changelog table are separate copies; both need a row each phase.

### Blockers
None.

### Next Phase Preview
- Awaiting your direction; no next phase is defined in PLAN.md.
