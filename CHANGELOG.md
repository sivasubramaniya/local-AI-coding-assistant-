# Changelog

Built from the Changelog table in [PLAN.md](PLAN.md). Each phase has a full report in
[docs/reports/](docs/reports/PHASE_0_REPORT.md).

| Date | Phase | Change | Tests |
|---|---|---|---|
| 2026-10-14 | 0 — Glass Theme | Selectable Glass theme (Settings → Theme, `--theme`), live switching, saved setting, Windows 11 dark title bar + Mica; Dark output byte-identical | 680 passed, 2 skipped, 11 deselected (integration) |
| 2026-10-14 | 1 — Test & Dev Setup | pytest.ini (markers, integration skipped by default), requirements.txt + requirements-dev.txt pinned to the venv, CLAUDE.md, README "Running tests" | 682 passed, 2 skipped, 11 deselected (integration), 0 warnings |
| 2026-10-14 | 2 — Repo Cleanup | .gitignore for generated files; README links fixed (CHANGELOG.md, MIT LICENSE, docs/OFFLINE.md, docs/TEST_REPORT.md, Dark/Glass demo screenshots); stray UTF-16 line removed; not a git repo, nothing to untrack | 691 passed, 3 skipped, 11 deselected (integration), 0 warnings |
