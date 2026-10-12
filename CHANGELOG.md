# Changelog

All notable changes to Local AI Assistant. Summarised from the `PLAN.md` changelog; dates are 2026.

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
