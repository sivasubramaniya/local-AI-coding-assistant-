# CLAUDE.md — Local AI Assistant

A native Windows 11 desktop coding assistant: Python 3.12 + **PySide6**, fully offline.
Work is planned in phases in `PLAN.md`.

## Hard rules
- **Local Ollama only.** Every answer comes from Ollama on loopback (`app/config.py` rejects other hosts).
  Never call cloud APIs or add network access to non-loopback hosts.
- **Never change the model name** (`qwen2.5-coder-14b:latest`; Fast mode `qwen2.5-coder-7b:latest`)
  and never fall back to another model automatically.
- **Never run model-generated commands directly.** Commands go through `app/agent/tool_runner.py`
  (allowlist, user approval, `shell=False`).
- **No hard-coded user paths.** Paths and settings come from `app/config.py`; UI settings are saved
  with `store.set_setting(...)`.
- No new runtime packages without approval. Runtime pins: `requirements.txt`; test tools:
  `requirements-dev.txt`.

## Code layout
- `app/backend`, `app/agent`, `app/storage`, `app/validation`, `app/export`: logic, no Qt widgets.
- `app/ui`: widgets only. Keep business logic out of UI classes; long-running work goes in Qt
  worker threads (`app/ui/workers.py`).

## Theme
- All design tokens live in `app/ui/theme.py`. Do not hard-code colors elsewhere; use
  `code_colors()`, `item_background()` and `qcolor()` for colors drawn in Python.
- Themes: **Dark** (default) and **Glass**. `COLORS` stays hex-only; Glass rgba values live in `GLASS`.
- **Dark must stay unchanged**: its stylesheet output is locked by sha256 in
  `tests/test_glass_theme.py`. Glass = the Dark sheet + an appended override block.
- Qt QSS has no blur/`backdrop-filter`. Menus, tooltips, dialogs and popups use opaque colors.
  Do not style `QSpinBox`.

## Tests
- Run: `python -m pytest` (integration tests are skipped by default via `pytest.ini`).
- Real-model tests: `python -m pytest -m integration` (needs Ollama and the exact model).
- Mock Ollama in unit tests (`tests/fake_ollama.py`). Mark real-model tests `@pytest.mark.integration`
  and Qt widget tests `@pytest.mark.gui`; register any new marker in `pytest.ini`.
- GUI tests run offscreen (`tests/conftest.py`).

## Workflow
Follow the phase workflow for each phase in `PLAN.md`: inspect, plan, implement, test, report
(`docs/reports/PHASE_N_REPORT.md`), tick `PLAN.md`, add a Changelog row, then stop for approval.
