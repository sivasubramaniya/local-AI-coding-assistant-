## Phase 0 Report — Glass Theme

### Summary
Added a selectable **Glass** theme next to Dark (still the default). Glass draws translucent rgba
panels with 1px light borders and brighter top edges over a navy→purple gradient with two radial glows.
Qt has no blur, so the panels are tinted rather than frosted. The Glass stylesheet is the Dark sheet with an
override block appended. Dark output is byte-identical to before; this was checked with sha256 hashes taken
before any change and is locked in by tests. Menus, tooltips, dialogs and combo popups use opaque colors.
Code blocks, inline code and the code-view gutter stay solid and darker than the panels. Switching in
Settings → Theme applies live: QSS, palette, existing answers re-rendered, the Markdown preview and the
gutter. The choice is saved with the other settings (key `theme`) and restored at startup. On Windows 11,
Glass also turns on a dark title bar and Mica frame through `DwmSetWindowAttribute` (ctypes).

### Files Created
- `app/ui/window_effects.py`: dark title bar + Mica via ctypes. Returns False and never raises off Windows
  or on the offscreen platform. A window that never had Glass is left untouched.
- `tests/test_glass_theme.py`: 46 tests.
- `PLAN.md`, `docs/reports/PHASE_0_REPORT.md`

### Files Modified
- `app/ui/theme.py`: `THEMES`, `DEFAULT_THEME`, `GLASS`, `current_theme()`, `normalize_theme()`, `qcolor()`,
  `item_background()`, `code_colors()`; `build_stylesheet(..., theme_name)`, `apply_theme(app, theme_name)`;
  Dark sheet moved unchanged into `_dark_stylesheet()`; `_glass_overrides()`; per-theme palette.
- `app/ui/sidebar.py`: delegate row colors come from `item_background()` / `qcolor()`.
- `app/ui/markdown_render.py`: code block and header colors come from `code_colors()`.
- `app/ui/code_view.py`: gutter colors come from `code_colors()` when painting.
- `app/ui/message_widgets.py`: `MarkdownBrowser` remembers its text; new `refresh_theme()`.
- `app/ui/preview_panel.py`: new `refresh_theme()` for the Markdown preview CSS.
- `app/ui/dialogs.py`: Theme combo is "Dark" / "Glass"; `theme_name` param + `theme_name()` getter.
- `app/ui/main_window.py`: `THEME_SETTING`; central widget named `glassBackdrop`; `set_theme()` /
  `theme_name()`; theme loaded in `_load_saved_settings`, saved + applied in `open_settings`
  (2-, 3- and 4-value editor tuples).
- `main.py`: `--theme dark|glass` for normal runs (not saved) and `--screenshot`.
- `tests/test_ui_export.py`: the old "Light is disabled" assertion now checks Dark/Glass.
- `tests/test_main.py`: Glass screenshot test; an unknown `--theme` is rejected.
- `README.md`: `--theme` in Run; the limitations line now lists the themes.

### Commands Run
- `python -m pip install pytest pytest-qt` (test-only tools; approved, not app dependencies)
- `python -m pytest -q -m "not integration"`: baseline before changes, 632 passed / 2 skipped / 11 deselected
- `python main.py --screenshot glass.png --theme glass` and `--theme dark` (real Windows platform)
- `python -m pytest -v -m "not integration"`

### Test Results
`680 passed, 2 skipped, 11 deselected in 83.68s` (0 failed). The 11 deselected are the `integration` tests.

### Mock vs Real
- All new tests are offline UI/unit tests; Ollama is mocked (`FakeOllama`) or not involved.
- Screenshots were captured on the real Windows platform in demo mode. Real-model integration tests were
  not run: this phase does not touch model code.

### Known Issues / Limitations
- No real blur (Qt limitation): the panels are tinted translucent fills.
- Mica only shows in the window frame/title bar because the client area is painted. It needs
  Windows 11 22H2+; older builds still get the dark title bar.
- `docs/glass-refs/`, `CLAUDE.md`, `requirements-dev.txt` and the pytest config (marker registration,
  default `-m "not integration"`) are missing from this checkout, so the suite was run with
  `-m "not integration"` explicitly.

### Blockers
None.

### Next Phase Preview
- Awaiting your direction; no next phase is defined in PLAN.md.
