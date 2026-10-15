# PLAN

## Phase 0 — Glass Theme  `[x]`

### Goal
Add a selectable "Glass" theme (frosted translucent panels over a dark
navy→purple gradient with soft glows) next to the existing Dark theme.
Dark stays the default and must look exactly as it does today.

### Visual reference
- `docs/glass-refs/` — frosted panels, 1px light borders (rgba white ~12–22%),
  brighter top edge, rounded corners, faint blue/purple glows behind.
  (Folder not present in this checkout; the description above was used.)

### Restrictions
- Theme only: do not change layout, sizes, fonts, behavior or business logic.
- Qt QSS has NO backdrop-filter/blur. Do not write CSS blur rules.
- Keep `COLORS` in `theme.py` hex-only (tests/test_theme.py checks it);
  rgba glass values go in a separate `GLASS` dict.
- Dark stylesheet output must stay byte-identical: build Glass as the Dark
  sheet + an override block appended after it.
- No new pip packages. Windows API access only through `ctypes`.
- No hard-coded user paths. Save the theme with the other settings
  (store.set_setting, key "theme").
- Code blocks stay solid and darker than glass panels, for readability.

### Tasks
- [x] 0.1  `app/ui/theme.py`: `THEMES`, `DEFAULT_THEME`, `current_theme()`,
          `normalize_theme()`; `build_stylesheet(..., theme_name)` and
          `apply_theme(app, theme_name="dark")`, callable again to switch live.
- [x] 0.2  `GLASS` tokens: gradient stops, glow colors, panel / hover /
          selected fills, border, highlight, code colors, opaque popup colors.
- [x] 0.3  Glass overrides: sidebar, top bar, composer pill, user bubble,
          file/agent cards, preview panel + header, file tree, menus,
          tooltips, scrollbars, dialogs, QLineEdit/QComboBox.
          Do NOT style QSpinBox (it loses its arrow buttons).
- [x] 0.4  Backdrop: QMainWindow linear gradient; central widget gets
          objectName "glassBackdrop" with a radial glow; #chatPanel gets a
          second glow; chatInner / chatView transparent.
- [x] 0.5  Popups and dialogs are separate windows: use opaque colors there,
          not rgba.
- [x] 0.6  Colors drawn directly in Python must follow the theme:
          sidebar.py delegate (hover/selected rows), markdown_render.py
          (code block + header), message_document_css (inline code),
          code_view.py (line-number gutter). Add helpers
          `item_background()`, `code_colors()`, `qcolor()` (parses rgba).
- [x] 0.7  New `app/ui/window_effects.py`: Windows 11 dark title bar + Mica
          frame via DwmSetWindowAttribute; returns False, never raises, on
          other platforms.
- [x] 0.8  `app/ui/dialogs.py`: Theme combo = "Dark", "Glass" (replace
          "Light (coming later)"); `theme_name` param + `theme_name()` getter.
- [x] 0.9  `app/ui/main_window.py`: THEME_SETTING; load + apply at startup
          in `_load_saved_settings`; save + apply live in `open_settings`;
          keep old 2- and 3-value settings_editor tuples working.
- [x] 0.10 `main.py`: `--theme dark|glass` option (also for --screenshot).

### Tests
- [x] Every GLASS token is valid rgba()/hex; COLORS has no rgba.
- [x] Glass stylesheet: braces balanced, starts with the Dark sheet, contains
      #sidebar, #composerPill, #userBubble, #fileCard, #previewHeader,
      #glassBackdrop, #chatPanel; no "backdrop-filter".
- [x] Dark output unchanged; unknown theme name falls back to Dark.
- [x] qcolor() parses rgba and hex.
- [x] apply_theme switches Dark → Glass → Dark live (styleSheet, code_colors).
- [x] Settings: theme saved, applied live, restored on restart.
- [x] Update the old test that asserted "Light" is disabled.
- [x] window_effects: no-op off Windows, never raises.
- [x] Full suite: `python -m pytest -v`.

### Done when
- Settings → Theme switches Dark ↔ Glass live; choice survives restart.
- `python main.py --screenshot glass.png --theme glass` renders correctly.
- All text readable on glass; Dark theme unchanged.
- All tests pass; Phase Report written; Changelog row added.

Report: [docs/reports/PHASE_0_REPORT.md](docs/reports/PHASE_0_REPORT.md) · Approved 2026-10-14

## Phase 1 — Test & Dev Setup  `[x]`

### Goal
Make the test setup reproducible so `python -m pytest` works with no extra flags.

### Restrictions
- No changes to app code or app dependencies.
- No new runtime packages; dev-only packages go in requirements-dev.txt.

### Tasks
- [x] 1.1 Add pytest config (pytest.ini or pyproject.toml [tool.pytest.ini_options]):
          register `gui` and `integration` markers; skip `integration` by default
          (addopts = -m "not integration"); testpaths = tests.
- [x] 1.2 Add requirements-dev.txt (pytest, pytest-qt) with pinned versions
          matching what is installed in the venv.
- [x] 1.3 Create CLAUDE.md with project rules: PySide6 desktop app, local Ollama only,
          no cloud APIs, theme tokens live in app/ui/theme.py, Dark must stay
          unchanged, run tests with `python -m pytest`.
- [x] 1.4 README: add a "Running tests" section (normal run + how to run
          integration tests with -m integration).

### Tests
- [x] `python -m pytest` with no flags: 0 failed, no "Unknown pytest.mark" warnings.
- [x] `python -m pytest -m integration --collect-only` lists the 11 integration tests.

### Done when
- Plain `python -m pytest` passes, the markers give no warnings, Phase Report is written.

Report: [docs/reports/PHASE_1_REPORT.md](docs/reports/PHASE_1_REPORT.md) · Approved 2026-10-14

## Phase 2 — Repo Cleanup  `[x]`

### Goal
Clean repository: no generated files tracked, no broken links in README.

### Restrictions
- No app code changes. No new packages.
- Never delete user data, chat history, or anything outside the repo folder.

### Tasks
- [x] 2.1 Add .gitignore: __pycache__/, *.pyc, .pytest_cache/, venv/ and .venv/,
          build/, dist/, *.spec outputs from PyInstaller (keep packaging/LocalAIAssistant.spec),
          logs, local data dir, screenshots generated by --screenshot.
- [x] 2.2 (Not a git repo: nothing to untrack.) If this is a git repo, untrack already-committed __pycache__/ and *.pyc
          with `git rm -r --cached` (files stay on disk). Show me the list first.
- [x] 2.3 README broken links (CHANGELOG.md, LICENSE, docs/*.md): list each one,
          then for each either create a short real file or remove/replace the link.
          Ask me before creating LICENSE (I choose the license).
- [x] 2.4 Add a CHANGELOG.md built from the PLAN.md Changelog table, if 2.3 keeps the link.

### Tests
- [x] Test: every relative link in README.md points to a file that exists.
- [x] Test: no .pyc / __pycache__ is tracked (skip if not a git repo).
- [x] `python -m pytest`: 0 failed, no warnings.

### Done when
- README has no broken links, generated files are ignored, Phase Report written.

Report: [docs/reports/PHASE_2_REPORT.md](docs/reports/PHASE_2_REPORT.md) · Approved 2026-10-14

## Phase 3 — Git & GitHub Sync  `[ ]`

### Goal
Put Phases 0–2 under git and onto GitHub without losing anything on GitHub
or on this PC.

### Repo
<YOUR-GITHUB-URL>

### Restrictions
- NEVER force-push. NEVER rewrite or delete GitHub history.
- Never delete files in this folder. No app code changes. No new packages.
- Ask me before every push.

### Tasks
- [ ] 3.1 Clone the GitHub repo into a NEW sibling folder (do not touch this one).
- [ ] 3.2 Compare: list files that differ between GitHub main and this folder,
          and any files on GitHub that are missing here. Show me before copying.
- [ ] 3.3 Create branch `phase-0-2-glass-theme-cleanup` in the clone, copy this
          folder's files in (respecting .gitignore), commit in logical commits:
          (a) Glass theme, (b) test & dev setup, (c) repo cleanup + docs.
- [ ] 3.4 Single changelog: CHANGELOG.md is the only source of truth. Replace
          PLAN.md's Changelog table with a link to CHANGELOG.md, and update the
          phase-workflow step "add a Changelog row" wording in CLAUDE.md.
- [ ] 3.5 Run `python -m pytest` in the clone; the git-tracking test must now run
          and pass (no bytecode tracked).
- [ ] 3.6 After my OK: push the branch and open a Pull Request into main
          (use `gh` if installed and logged in; otherwise give me the PR link).

### Tests
- [ ] Test that PLAN.md links to CHANGELOG.md and has no separate changelog table.
- [ ] `python -m pytest`: 0 failed, 0 skipped git test, no warnings.

### Done when
- Branch pushed, PR open, tests pass in the clone, Phase Report written.
- From then on I work in the cloned folder, not this one.

## Changelog

| Date | Phase | Change | Tests |
|---|---|---|---|
| 2026-10-14 | 0 — Glass Theme | Selectable Glass theme (Settings → Theme, `--theme`), live switching, saved setting, Windows 11 dark title bar + Mica; Dark output byte-identical | 680 passed, 2 skipped, 11 deselected (integration) |
| 2026-10-14 | 1 — Test & Dev Setup | pytest.ini (markers, integration skipped by default), requirements.txt + requirements-dev.txt pinned to the venv, CLAUDE.md, README "Running tests" | 682 passed, 2 skipped, 11 deselected (integration), 0 warnings |
| 2026-10-14 | 2 — Repo Cleanup | .gitignore for generated files; README links fixed (CHANGELOG.md, MIT LICENSE, docs/OFFLINE.md, docs/TEST_REPORT.md, Dark/Glass demo screenshots); stray UTF-16 line removed; not a git repo, nothing to untrack | 691 passed, 3 skipped, 11 deselected (integration), 0 warnings |
