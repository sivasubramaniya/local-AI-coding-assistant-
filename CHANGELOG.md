# Changelog

All notable changes to Local AI Assistant. Summarised from the `PLAN.md` changelog; dates are 2026.

## [1.2.1] — 2026-10-13

### Fixed
- **HTML project preview showed pages unstyled.** The preview loaded the HTML text with no base URL, so
  `styles.css`, `script.js` and images could not resolve; "Open in browser" opened a temporary copy of only
  the HTML. Now the preview loads the real file (`QWebEngineView.load(file URL)`; local file access on,
  remote access off, JavaScript on for local files) and "Open in browser" opens the real project file
  (disabled with a tooltip when there is no saved project). The path goes through the path validator.
- The preview reloads the open file when the project is re-shown after an edit or repair.

### Added
- Missing-asset check after generation: missing images get grey placeholder images (listed as
  "placeholder"); missing CSS/JS are reported in the result card, never invented. References that leave
  the project (`../`, drive letters, root-relative, UNC) are reported as unsafe and never created.
- The project validator checks that every local `src`/`href`/`url()` reference exists.
- Generation prompts tell the model to reference only planned files and use inline SVG/CSS for pictures.
- `main.py --screenshot PATH --preview PROJECT_DIR` and `scripts/preview_screenshot.py`.

## [1.2.0] — 2026-10-13

### Added
- **Working Light, Dark and System themes** (Settings → Theme). Two complete palettes with identical
  tokens (Dark unchanged); System follows Windows via Qt's color scheme and reacts to changes live.
- Switching applies immediately without a restart: stylesheet, all icons, already-rendered messages and
  code blocks (Pygments `default` in Light, `github-dark` in Dark), the code viewer, file tree, status card,
  dialogs and the preview panel. The choice is saved and restored before the window shows.
- Tests: identical tokens and valid hex in both palettes, a WCAG AA contrast check (text 4.5:1, UI parts 3:1),
  live Dark → Light → Dark switching, System mode with Qt's change signal, persistence, and a scan that fails
  on hex colors in `app/ui/` outside `theme.py`.
- `scripts/theme_screenshots.py` and `docs/screenshots/theme-{light,dark}-*.png`.

### Fixed
- Code-view line numbers did not meet AA contrast (found by the new test).
- Settings: "Browse…" and "Cancel" used the red reject style; the command timeout is limited to 10–600 s.
- README.md had been made binary by a UTF-16 line appended in PowerShell; restored as UTF-8.

## [1.1.1] — 2026-10-13

Pre-publish cleanup.

### Fixed
- Restored test/command runs showed the model name, and failed runs came back as red error cards with
  raw Markdown. Messages now record their kind (database schema v4: `messages.kind`, existing tool-run
  rows are backfilled) and restore as "Checks passed" / "Checks failed".

### Changed
- Screenshots 06–09 retaken in a neutral folder (`D:\laa-demo`), so no Windows user name is visible.
- Personal paths removed from sample reports and from the git history; old screenshots that showed them were
  stripped from history. A test now fails if a tracked text file contains a `C:\Users\<name>` path.

## [1.1.0] — 2026-10-12

### Added
- **Fast mode** (owner decision): an optional second model, `qwen2.5-coder-7b:latest`
  (`ollama/Modelfile.fast`, same settings as the default). Chosen per chat with the **Quality (14B) /
  Fast (7B)** toggle in the composer; the default for new chats is set in Settings. The default model is
  still `qwen2.5-coder-14b:latest`, and the app never switches models by itself.
- The chosen model is saved on the chat and on every answer (database schema v3: `messages.model_name`);
  status lines show which model answered.
- Health checks look at both models; the status card shows the selected one. A missing selected model gives
  the amber "Model missing" state with the exact `ollama create` command — no fallback in either direction.
- `--check` reports both models (present/missing) and which one is the default.
- The Plan card notes "Fast mode: quicker, may need more repair rounds" when Fast mode is on.
- REAL measurements: 7B is about 2× faster (6.40 vs 3.19 tok/s); a 7B to-do project passed its tests after
  2 repair rounds (`docs/PERFORMANCE.md`).

### Fixed
- File answers with an extra snippet in another language (for example a `bash` "run it" block) were
  rejected; now accepted only when exactly one block is in the file's language (found by the 7B run).
- `new_chat()` did not show the chat's model in the composer and status card.

## [1.0.0] — 2026-10-12

First release.

### Added
- **Desktop app** (PySide6, dark theme, three-column layout): chat, sidebar with Recents and Projects,
  syntax-highlighted code blocks with Copy, code viewer, project preview panel with an offline HTML preview.
- **Local model only**: Ollama on `localhost` with the exact model `qwen2.5-coder-14b:latest`
  (`ollama/Modelfile`: temperature 0.2, top_p 0.8, num_ctx 8192); no fallback model, no cloud API.
- **Streaming chat** with Stop, Regenerate, Retry, clear error cards and a live Ollama status card.
- **Chat history** in SQLite (schema v2 with migrations, WAL, corrupt-file backup, newer-schema protection).
- **Project mode**: strict JSON plan → Plan card → one call per file, retry once, partial failures listed;
  projects saved under `%LOCALAPPDATA%\LocalAIAssistant\projects` and linked to the chat.
- **Edits and repair loop**: suggested changes shown as diffs and applied only after confirmation (with
  backups); failing tests go back to the model for at most 3 repair rounds.
- **Security**: path validator (traversal, drive/UNC paths, reserved names, symlink/junction escapes),
  allowlisted command runner (`shell=False`, project-root cwd, timeouts, process-tree kill), approval dialog.
- **Export** to a folder or a verified ZIP, with exclusions for caches, venvs, backups and secrets.
- **Offline verification**: code audit, socket guard test mode (`--offline-guard`), documented manual checklist.
- **Packaging**: PyInstaller onedir build (322 MB), `--check` and `--version`, version 1.0.0 in Settings/About.
- **Docs**: README, INSTALL, OFFLINE, PERFORMANCE, TEST_REPORT; MIT license.

### Changed during development
- Generator quality fixes found by REAL model runs: file prompts repeat the request and include files
  already written; Markdown files parsed leniently; edits recognised when the path is on the line before the block.
- Package size reduced from 567 MB to 322 MB by bundling only the Qt modules the app loads.

### Fixed during development
- A late "cancelled" signal from a stopped worker could end the next answer.
- Export results were handled on the worker thread.
- Worker threads are joined before exit (Qt aborted the process when a running QThread was destroyed).
- Offscreen screenshots had no fonts (tests now point Qt at the Windows fonts folder).

### Performance
- Tuning trials (num_ctx 4096, flash attention + q8_0 KV cache) were not reliably faster on a 4 GB-VRAM
  laptop, so the defaults were kept. See `docs/PERFORMANCE.md`.

## Development milestones

| Phase | Summary |
|---|---|
| 1 | Environment inspection; model created from the Modelfile and verified |
| 2 | Project foundation: config, logging, errors, tests |
| 3 | Native PySide6 UI |
| 4 | Ollama integration and coding system prompt |
| 5 | SQLite chat history |
| 6 | Coding agent and project generator |
| 7 | Security and validation |
| 8 | Testing and debugging workflow (REAL Java sample + repair) |
| 9 | Project export |
| 10 | Offline verification (automated part) |
| 11 | Windows packaging |
| 12 | Polish and release: performance trials, real-app test, smaller build, v1.0.0 |
| 13 | Fast mode: optional, user-selected 7B model per chat; v1.1.0 |
