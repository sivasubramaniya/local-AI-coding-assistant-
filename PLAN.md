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

## Phase 5 — Chat History and SQLite Storage  `[ ]`

- [ ] Schema: `conversations`, `messages`, `projects` (plus a `schema_version` table)
- [ ] Create, reopen, rename and delete chats
- [ ] Restore history into the UI
- [ ] Link chats to generated projects
- [ ] Tests for CRUD, error handling and migrations

**Deliverable:** persistent local chat history.

---

## Phase 6 — Coding Agent and Project Generator  `[ ]`

- [ ] Task classifier (generate, debug, explain, refactor, project, other)
- [ ] Project planning step (file list before contents)
- [ ] Structured file output format from the model (for example JSON or fenced blocks with paths)
- [ ] Parser that rejects malformed or incomplete responses
- [ ] Create and edit files (through the validator once Phase 7 is done)
- [ ] Show planned file changes to the user before writing
- [ ] Progress reporting and failure reporting

**Deliverable:** local multi-file project generator.

---

## Phase 7 — Security and Validation  `[ ]`

- [ ] `path_validator.py`: reject absolute paths, `..`, drive letters, symlink escapes
- [ ] Writes restricted to the approved project directory
- [ ] Overwrite confirmation
- [ ] `project_validator.py`: expected structure checks
- [ ] `tool_runner.py`: executable and argument allowlist, timeouts, captured output and exit codes
- [ ] Approval dialog for risky operations
- [ ] Security-focused tests (traversal attempts, disallowed commands, timeouts)

**Deliverable:** controlled file-generation and command-execution workflow.

---

## Phase 8 — Testing and Debugging Workflow  `[ ]`

- [ ] Unit and integration test coverage across modules
- [ ] Mocks for unavailable services
- [ ] Generate a sample Java calculator project
- [ ] Run approved compilers and tests if installed (`javac`, `java`, `pytest`)
- [ ] Feed errors back to the model for fixes; re-run affected tests
- [ ] Clearly separate mock results from real results

**Deliverable:** observable generate → test → repair loop.

---

## Phase 9 — Project Export  `[ ]`

- [ ] Export to a user-selected folder (Desktop by default)
- [ ] Include source, tests, config and README; exclude caches, secrets and `__pycache__`
- [ ] Create a ZIP archive
- [ ] Verify archive contents after creation
- [ ] Build and run instructions in the README

**Deliverable:** complete project folders and ZIP archives.

---

## Phase 10 — Offline Verification  `[ ]`

- [ ] Disconnect the network and test chat, generation, storage and export
- [ ] Confirm no cloud APIs are called
- [ ] Test missing-model and missing-dependency scenarios
- [ ] Document required local tools

**Deliverable:** honest offline-readiness report.

---

## Phase 11 — Windows Packaging  `[ ]`

- [ ] `LocalAIAssistant.spec` for PyInstaller
- [ ] Bundle the prompt file and assets
- [ ] Correct data-directory initialization in the packaged build (for example `%APPDATA%`)
- [ ] Build and test startup from `dist/`
- [ ] Installation, prerequisites (Ollama and model) and troubleshooting guide

**Deliverable:** working Windows desktop distribution.

---

## Final Deliverables Checklist

- [ ] Native Windows desktop app (PySide6)
- [ ] Fixed local Ollama model integration
- [ ] Coding-only system prompt
- [ ] New Chat and persistent Chat History
- [ ] Code viewer and project preview
- [ ] Coding agent and multi-file generator
- [ ] Safe file operations and command approval
- [ ] Automated tests and validation
- [ ] SQLite storage
- [ ] Desktop export and ZIP
- [ ] README and run instructions
- [ ] Offline verification report
- [ ] PyInstaller build
- [ ] Installation and troubleshooting guide
- [ ] Final test report and known limitations

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
