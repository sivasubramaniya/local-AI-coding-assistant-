# PLAN.md — Local AI Assistant Implementation Plan

Status legend: `[ ]` not started · `[~]` in progress · `[x]` done and verified · `[!]` blocked

Rule: complete, test and review each phase before starting the next. Claude Code must
stop at every phase boundary and wait for approval.

---

## Phase 1 — Environment Inspection and Model Verification  `[x]`

> Model checks done 2026-10-12: `qwen2.5-coder-14b:latest` created from `ollama/Modelfile`
> (FROM qwen2.5-coder:14b, temperature 0.2, top_p 0.8, num_ctx 8192). Timed request: 40.0 s load,
> 17 tokens at 2.7 tok/s, 75.4 s wall (cold start; slow hardware path).

**Goal:** Know exactly what exists before building anything. Read-only phase.

- [x] Inspect repository structure and git status
- [x] Check Python, pip, Git and Ollama versions
- [x] Check for PySide6, pytest, PyInstaller (report only, do not install)
- [x] Confirm the Ollama service responds on port 11434 (after install in Phase 2: v0.40.2)
- [x] Confirm the exact model `qwen2.5-coder-14b:latest` exists (`ollama list`)
- [x] Inspect model parameters (`ollama show --modelfile`)
- [x] Send one small coding request and time it
- [x] Report RAM and GPU
- [x] Write the Phase 1 report: blockers, warnings, Phase 2 plan

**Restrictions:** no file changes, no installs, no model downloads, no system changes.
**Deliverable:** Phase 1 report.

---

## Phase 2 — Project Foundation  `[x]`

- [x] Create or confirm the package structure (`app/` and its subpackages)
- [x] Central configuration (`app/config.py`): data dir, output dir, model name, Ollama URL, timeouts
- [x] Logging setup (file and console)
- [x] Custom exception classes
- [x] `requirements.txt` with pinned versions (PySide6-Essentials for now; full PySide6/WebEngine pending)
- [x] Minimal `main.py` that starts without errors
- [x] Tests for config and logging

**Deliverable:** clean, testable Python foundation; `pytest` passes.

---

## Phase 3 — Native Desktop UI  `[x]`

- [x] Main PySide6 window titled "Local AI Assistant"
- [x] New Chat button and Chat History sidebar (in-memory until Phase 5)
- [x] Message input with Send and Cancel (Stop)
- [x] Response area with syntax-highlighted code blocks and Copy buttons
- [x] Code viewer and project file tree
- [x] Generate Project (Project mode chip), Export Project, Export ZIP controls (stubs for now)
- [x] Model indicator, Ollama status (stub: Disconnected), progress and error indicators
- [x] Worker-thread pattern (`QThread` + `QObject`) for long tasks; demo FakeStreamWorker

**Deliverable:** app opens in its own window with no browser.

---

## Phase 4 — Ollama Integration and Coding System Prompt  `[x]`

> Verified against the real model 2026-10-12: `python -m pytest -m integration -v` → 3 passed
> (ensure_ready, is_prime parses, off-topic redirect). Manual UI prompt still to be tried by the owner.

- [x] `ollama_client.py`: health check, model check, chat, streaming
- [x] `coding_system_prompt.txt`: coding-only behavior, polite redirection of off-topic requests
- [x] System prompt applied to every model call
- [x] Streaming tokens to the UI through signals
- [x] Timeout, cancellation and clear error messages
- [x] No fallback to other models or cloud services (loopback-only URL, exact model match)
- [x] Unit tests with mocked HTTP responses; integration tests against the real model (3 passed)

**Deliverable:** working local coding chat.

---

## Phase 5 — Chat History and SQLite Storage  `[x]`

- [x] Schema v1: `conversations`, `messages`, `projects`, `app_settings` plus `schema_version`; WAL, foreign keys, busy_timeout
- [x] Migrations (ordered, one transaction each); newer schema refused untouched; corrupt file backed up, never deleted
- [x] `ChatStore` protocol shared by `InMemoryChatStore` and `SqliteChatRepository`
- [x] Create, reopen (last chat on start), rename (1–80 chars) and delete (confirm, cascade) chats
- [x] Restore history into the UI and into the model context; stopped/error replies saved with status
- [x] Thumbs-down feedback persists; Projects section reads the `projects` table
- [x] Link chats to generated projects (FK `ON DELETE SET NULL`; rows are written in Phase 6)
- [x] Tests for CRUD, rollback, migrations, corruption, restart persistence and storage errors in the UI

**Deliverable:** persistent local chat history.

---

## Phase 6 — Coding Agent and Project Generator  `[x]`

- [x] Task classifier, rules only (generate, debug, explain, refactor, review, project, off_topic)
- [x] Project planning step: strict JSON plan (file list before contents), one corrective retry
- [x] Structured file output: one call per file, exactly one fenced block (four backticks for Markdown)
- [x] Parser that rejects malformed, partial or unsafe responses; partial failures listed, successes kept
- [x] Create files through the path validator (created early in `app/validation/path_validator.py`)
- [x] Edit files: full-file or unified-diff suggestions shown as a diff; Apply writes with `.bak-<ts>` backups
- [x] Plan card (Apply/Cancel) before writing; progress per file; Stop keeps written files
- [x] Projects saved under `projects_dir/<safe-name>[-N]`, linked to the chat (DB v2 `message_files`)
- [x] Model text is never executed (test asserts no subprocess is started)

**Deliverable:** local multi-file project generator.

---

## Phase 7 — Security and Validation  `[x]`

- [x] `path_validator.py`: rejects absolute, drive, UNC, `..`, reserved names, illegal chars, long paths, symlink/junction escapes
- [x] Writes restricted to the approved project directory (generator writer, edit apply, backups)
- [x] Overwrite confirmation (edits only after Apply on the Changes card; generator never overwrites)
- [x] `project_validator.py`: expected files exist, no empty files, README present (shown after generation)
- [x] `tool_runner.py`: program + argument allowlist, `shell=False`, cwd = project root, timeout with process-tree kill, captured stdout/stderr/exit code, truncation, Stop
- [x] Approval dialog shows the exact command and working directory; refused commands never reach it
- [x] Security tests: 45 malicious paths (x2), junction escape, 47 allowlist bypass attempts, 12 shell-syntax strings, timeout tree kill, UI reject flow

**Deliverable:** controlled file-generation and command-execution workflow.

---

## Phase 8 — Testing and Debugging Workflow  `[x]`

- [x] Unit and integration test coverage across modules (`pytest --cov`: 88% of app code; QThread code is not traced)
- [x] Mocks for unavailable services (scripted FakeOllama, loopback fake server, JDK-less skips)
- [x] Generate a sample Java calculator project through the app's own generator (REAL model, `scripts/run_java_sample.py`)
- [x] Run approved compilers and tests (`javac`, `java`, `python -m pytest`) via the allowlisted runner; JDK 21 installed with winget
- [x] Feed errors back to the model for fixes; diff shown; apply after confirmation; re-run (max 3 rounds, each in the chat)
- [x] Clearly separate mock results from real results (REAL/MOCK labels in reports, `integration` marker)

---

## Phase 9 — Project Export  `[x]`

- [x] Export to a user-selected folder (default from settings, initially the Desktop); `-2`, `-3` on name collisions
- [x] Include source, tests, config and README; exclude caches, venvs, build output, backups, `.git` (optional), secrets
- [x] Create a ZIP archive (ZIP_DEFLATED)
- [x] Verify archive contents after creation (testzip, names, sizes, extraction) before reporting success
- [x] Build/run/test instructions in the exported README (added to the copy when missing)
- [x] Export / Export ZIP buttons, success card with Open folder, Settings dialog (export folder, command timeout, theme placeholder)

---

## Phase 10 — Offline Verification  `[~]`

> Automated part done. The Wi-Fi-off manual checklist in `docs/OFFLINE.md` must be run by the owner.

- [~] Disconnect the network and test chat, generation, storage and export (automated with a socket guard; manual run pending)
- [x] Confirm no cloud APIs are called (code audit documented; whole suite passes with `--offline-guard`)
- [x] Test missing-model and missing-dependency scenarios
- [x] Document required local tools (`docs/OFFLINE.md`)
- [x] HTML preview blocks remote resources (off-the-record WebEngine profile + interceptor)

---

## Phase 11 — Windows Packaging  `[x]`

- [x] `packaging/LocalAIAssistant.spec` (onedir, windowed, no UPX): prompt, icons, Modelfile and docs bundled; tests excluded
- [x] Bundle the prompt file and assets (loaded through `sys._MEIPASS` in the packaged build)
- [x] Data directory stays `%LOCALAPPDATA%\LocalAIAssistant` in the packaged build
- [x] Build (`pyinstaller packaging\LocalAIAssistant.spec --noconfirm`, 2.8 min, 567 MB) and test from `dist\`: `--check` exit 0 (attaches to the terminal, writes `logs\check.txt`), window title "Local AI Assistant", clean close, missing-model message points at the bundled Modelfile
- [x] `docs/INSTALL.md`: prerequisites, Ollama + model setup, first run, troubleshooting (Ollama not running, model missing, slow responses, antivirus, SmartScreen)
- [x] `docs/TEST_REPORT.md` with all counts, MOCK vs REAL and known limitations
- [x] Worker threads are joined before the app exits (`shutdown_workers`)

---

## Phase 12 — Polish and Release  `[x]`

- [x] Performance trials (REAL): num_ctx 4096 and flash attention + q8_0 KV cache vs the 8192 baseline; none reliably faster, defaults kept (`docs/PERFORMANCE.md`)
- [x] REAL end-to-end app test (`tests/test_integration_app.py`): chat, stop, project mode with tests/repair, ZIP export, restart; screenshots in `docs/screenshots/`
- [x] Fixed the bugs it found (reply replacement, action-row overlap, Markdown paragraphs, fence labels, export toast, offscreen fonts) with regression tests
- [x] Smaller build: only the Qt modules the app loads (567 MB → 322 MB), WebEngine preview verified in the exe
- [x] Release prep: `.gitignore` proven with `git check-ignore`, tracked files scanned (no secrets, no files > 5 MB, personal paths removed from sample reports)
- [x] Version 1.0.0 in `--check`, `--version` and Settings/About; README, CHANGELOG, MIT LICENSE

---

## Phase 13 — Fast Mode  `[x]`

> Owner decision 2026-10-12: the default stays `qwen2.5-coder-14b:latest`; ONE optional model,
> `qwen2.5-coder-7b:latest`, may be selected by the user per chat. No silent fallback.

- [x] `ollama/Modelfile.fast` (FROM qwen2.5-coder:7b, same settings); `qwen2.5-coder-7b:latest` created
- [x] Config `fast_model_name` (validated; `LAA_FAST_MODEL_NAME` override logs a warning)
- [x] Quality (14B) / Fast (7B) toggle in the composer; default for new chats in Settings (`app_settings`)
- [x] Model saved on the chat and on each answer (DB migration v3: `messages.model_name`); status lines show the model
- [x] Health check covers both models; status card shows the selected one; missing model → amber + exact command, never a fallback
- [x] Project generation uses the chat's model; Plan card note in Fast mode
- [x] `--check` reports both models and the default
- [x] MOCK tests (10) + REAL tests (7B is_prime, 7B off-topic) + REAL 14B-vs-7B benchmark + REAL 7B project run

---

## Phase 14 — Pre-publish Cleanup  `[x]`

- [x] Found every tracked file and commit containing the Windows user name, `C:\Users\` or "OneDrive" (text and images)
- [x] Current files clean; screenshots 06–09 retaken under `D:\laa-demo` (REAL app test 5/5)
- [x] `tests/test_no_personal_paths.py` fails on any `C:\Users\<name>` path in tracked text files
- [x] Backup at `D:\coder slm-backup`; history rewritten with git filter-repo (paths replaced, old screenshots stripped); tags re-created
- [x] Restored tool runs show "Checks passed"/"Checks failed" (schema v4 `messages.kind`, backfilled) + regression test
- [x] Version 1.1.1; pytest, exe rebuild and `--check` verified

---

## Phase 15 — Working Theme Switching  `[x]`

- [x] DARK (unchanged) and LIGHT palettes with identical tokens; every hard-coded color moved into `theme.py`
- [x] Dark / Light / System (follows Windows via `styleHints().colorScheme()` + `colorSchemeChanged`); default Dark
- [x] Live switching without restart: stylesheet, icons (themed registry), messages + code highlighting, code viewer, tree, status card, dialogs, preview
- [x] Choice saved in `app_settings` and restored before the window shows
- [x] Settings: command timeout 10–600 s; neutral Browse/Cancel buttons
- [x] Tests: tokens, hex, WCAG AA contrast, live switch, System signal, persistence, no hex outside theme.py
- [x] Screenshots `docs/screenshots/theme-{light,dark}-*.png` reviewed (2 fix rounds)

---

## Phase 16 — Fix HTML Project Preview  `[x]`

- [x] Diagnosed: preview used `setHtml()` without a base URL; "Open in browser" opened a temp copy of only the HTML; the portfolio referenced `assets/logo.png` and `assets/profile.jpg` that were never generated
- [x] Preview loads the real file (WebEngine file URL; local files on, remote off); fallback states its limits
- [x] "Open in browser" opens the real project file; disabled without a saved project; path validated
- [x] Live refresh when the project is re-shown after edits/repairs
- [x] Missing images → placeholders; missing CSS/JS reported; unsafe references refused; prompts updated
- [x] Validator: all local HTML/CSS references must exist
- [x] Tests (MOCK + REAL 7B portfolio) and screenshots (source and packaged exe)

---

## Final Deliverables Checklist

- [x] Native Windows desktop app (PySide6)
- [x] Fixed local Ollama model integration
- [x] Coding-only system prompt
- [x] New Chat and persistent Chat History
- [x] Code viewer and project preview
- [x] Coding agent and multi-file generator
- [x] Safe file operations and command approval
- [x] Automated tests and validation
- [x] SQLite storage
- [x] Desktop export and ZIP
- [x] README and run instructions
- [~] Offline verification report (automated part done; manual Wi-Fi-off checklist pending)
- [x] PyInstaller build
- [x] Installation and troubleshooting guide
- [x] Final test report and known limitations

---

## Changelog

| Date | Phase | Summary | Tests |
|---|---|---|---|
| 2026-10-11 | — | Plan created | — |
| 2026-10-11 | 1 | Environment inspected (read-only). Blocked: no Ollama, no model, no Git, only Python 3.15 | none |
| 2026-10-11 | 2 | Installed Python 3.12.10, Git, Ollama 0.40.2; venv + packages. Added config, errors, logging, system prompt, main.py, tests, git init | 54 passed |
| 2026-10-11 | 3 | Native PySide6 UI: theme/QSS, SVG icons, sidebar, chat view, composer, preview panel (QTextBrowser HTML fallback), worker pattern, demo stream, `--screenshot` | 135 passed |
| 2026-10-11 | 4 | Ollama client (httpx, streaming, abort), chat service (system prompt + trimming), health checks, real worker, `--demo`, loopback-only URL, Modelfile; fixed worker lifetime crash; QtWebEngine installed | 193 passed, 3 integration skipped (model missing) |
| 2026-10-12 | 1+4 | Real-model verification: `ollama create qwen2.5-coder-14b -f .\ollama\Modelfile`, modelfile inspected, timed request (2.7 tok/s), integration tests | 3 integration passed (REAL) |
| 2026-10-12 | 5 | SQLite chat history (stdlib sqlite3): schema v1, migrations, corrupt/newer DB handling, ChatStore protocol, restart restore, feedback, `--check` DB report; fixed stale worker signal ending the next stream | 252 passed (MOCK), 3 integration deselected |
| 2026-10-12 | 6 | Coding agent: task classifier, two-step project generator (plan JSON + per-file blocks, retry), plan/changes cards, edit flow with diffs and backups, project context for debug/refactor, path validator, DB migration v2 (message_files) | 333 passed (MOCK); real generator test: see Phase 7 row |
| 2026-10-12 | 7 | Security: path validator hardening + attack suite, project validator, allowlisted tool runner (shell=False, timeouts, tree kill), approval flow + Run project tests; config `command_timeout_s`. Phase 6 real generator integration test passed (4.1 min) | 536 passed, 1 skipped (symlink privilege) (MOCK); 1 integration passed (REAL) |
| 2026-10-12 | 8 | Debug workflow: Java/Python test detection, command sequences, JDK discovery, repair loop (max 3 rounds, diff + confirm + re-run), pytest-cov; generator fixes found by REAL runs (request + earlier files in file prompts, lenient Markdown, path-before-block edits). REAL: Java sample generated and passed (run 2), REAL repair fixed an injected bug in 1 round; run 1 (before fixes) failed and is kept as evidence | 601 passed, 1 skipped (MOCK); coverage 88%; REAL: Java sample PASS, repair demo PASS |
| 2026-10-12 | 9 | Project export: folder export with exclusions and -N collisions, README instructions, verified ZIP (testzip, names, sizes, extraction), Export/ZIP buttons with success card, Settings dialog (export folder, command timeout) | 601 passed, 1 skipped (MOCK) |
| 2026-10-12 | 10 | Offline verification (automated): code audit, socket guard (--offline-guard), loopback end-to-end test of chat/generation/storage/export, missing-model/Ollama-stopped checks, HTML preview blocks remote requests, docs/OFFLINE.md with the manual Wi-Fi-off checklist | 601 passed, 1 skipped; guarded suite passes (intermittent exit crash, see known issues) |
| 2026-10-12 | 11 | Windows packaging: PyInstaller spec (onedir, windowed), bundled prompt/icons/Modelfile/docs, --check console attach + logs\check.txt, bundled-Modelfile hint, worker shutdown at exit, INSTALL.md, TEST_REPORT.md, README | 601 passed, 1 skipped (MOCK); 4 integration passed (REAL); packaged exe --check and window launch OK (REAL) |
| 2026-10-12 | 12 | Polish and release 1.0.0: performance trials (nothing kept), REAL end-to-end app test + 6 fixes, build 567 → 322 MB, gitignore/secret scan, version 1.0.0, README/CHANGELOG/LICENSE | 611 passed, 1 skipped (MOCK); 9 integration passed (REAL); exe --check OK |
| 2026-10-13 | 13 | Fast mode: optional user-selected `qwen2.5-coder-7b:latest` per chat (no fallback), DB v3, both-model health and --check, plan-card note, parser fix found by the REAL 7B run; v1.1.0 | 628 passed, 1 skipped (MOCK); 11 integration passed incl. 1 re-run after a sleep-related Ollama timeout (REAL); 7B 6.40 vs 14B 3.19 tok/s |
| 2026-10-13 | 14 | Pre-publish cleanup: personal paths removed from files and history (filter-repo, backup kept), neutral screenshots, personal-path test, tool-run restore fix (DB v4), v1.1.1 | 633 passed, 1 skipped (MOCK); REAL app test 5/5; exe --check OK |
| 2026-10-13 | 15 | Working Light/Dark/System theme with live switching and persistence, WCAG AA contrast test, no hard-coded colors outside theme.py, Settings timeout range; v1.2.0 | 652 passed, 1 skipped (MOCK) |
| 2026-10-13 | 16 | HTML preview fixed: real file URLs (CSS/JS/images work, offline), Open in browser uses the real file, live refresh, missing-image placeholders and missing-code reports, validator reference check; v1.2.1 | 663 passed, 1 skipped (MOCK); REAL 7B portfolio test passed; exe preview screenshot OK |
