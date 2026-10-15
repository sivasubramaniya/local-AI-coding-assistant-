# Final Test Report — Local AI Assistant 1.3.0

Date: 2026-10-12 · Windows 11 Home 10.0.26300 · Python 3.12.10 · Ollama 0.40.2 ·
model `qwen2.5-coder-14b:latest` (from `qwen2.5-coder:14b`, runs about 79% CPU / 21% GPU, ~3 tok/s) ·
JDK: Microsoft OpenJDK 21.0.12

Labels: **MOCK** = Ollama replaced by a scripted fake (in-process transport or a loopback socket
server). **REAL** = the real local model and/or real compilers and processes.

## Summary

| Suite | Command | Result | Kind |
|---|---|---|---|
| Unit + GUI (offscreen) | `python -m pytest -v` | **628 passed, 1 skipped**, 11 deselected (integration) | MOCK model; real SQLite, files, subprocesses (python, javac, java) |
| Same, network blocked | `python -m pytest --offline-guard` | **601 passed, 1 skipped** | MOCK model, loopback sockets only |
| Manual offline check (owner, 2026-10-13) | packaged exe 1.2.1 with Wi-Fi off | chat, project generation, preview and ZIP export **all worked** | REAL model, REAL app, run by the owner |
| Integration | `python -m pytest -m integration -v` | **11 passed** (10 in the full run + 1 re-run after a sleep-related Ollama timeout) | REAL models (14B + 7B) |
| Coverage | `python -m pytest --cov=app --cov=main` | **88%** of app code | — |
| Compile | `python -m compileall -q app main.py scripts` | exit 0 | — |
| Java sample (generate → compile → test) | `scripts/run_java_sample.py` | run 2: 4/4 files, `javac` + plain test class **PASSED** (9.0 min) | REAL model + REAL JDK |
| Java repair demo | `scripts/run_java_sample.py --repair-demo` | injected bug fixed in **1 repair round**, tests PASSED (1.7 min) | REAL model + REAL JDK (bug injected by the script) |
| Packaged app | `dist\LocalAIAssistant\LocalAIAssistant.exe --check` | exit 0, model present; window opens titled "Local AI Assistant", closes cleanly | REAL |

The one skip: `tests/test_validation.py::test_symlink_escape_is_rejected` — creating a symlink needs
Developer Mode or admin rights on this machine. The junction-escape test (no privilege needed) ran and passed.

## Release 1.3.0 (Phase 17, 2026-10-15)

| Check | Result | Kind |
|---|---|---|
| `python -m pytest -v` | **717 passed, 1 skipped**, 12 deselected (the same symlink skip) | MOCK model; real SQLite, files, Qt (offscreen) |
| Glass tests (`tests/test_glass_theme.py`) | Light/Dark output hashes unchanged; Glass tokens, WCAG AA, text contrast over translucent panels on every backdrop color; live Dark → Glass → Dark; saved and restored; window effects no-op offscreen and off Windows | — |
| Repository checks (`tests/test_repo_hygiene.py`) | doc links resolve, README clean UTF-8, build files ignored, no tracked bytecode | git |
| Window effects on Windows 11 | manual check (a real window on the `windows` platform; the automated tests run offscreen and only cover the no-op paths): `DwmSetWindowAttribute` returned S_OK for the dark title bar and for Mica | REAL, manual (this machine) |

The pytest process again exited with 0xC0000409 after printing the result (Qt shutdown, see Known issues);
unmodified `main` does the same. Integration tests were not re-run: this release changes no model code.

## Releases 1.2.0 and 1.2.1 (Phases 15–16, 2026-10-13)

| Check | Result | Kind |
|---|---|---|
| `python -m pytest -v` | **663 passed, 1 skipped**, 12 deselected | MOCK model; real SQLite, files, QtWebEngine (offscreen) |
| Theme tests (`tests/test_theme_switching.py`) | tokens, hex, WCAG AA contrast both palettes, live switch, System signal, persistence | — |
| HTML preview tests (`tests/test_html_preview.py`) | CSS applied (`getComputedStyle` = `rgb(1, 2, 3)`), JS ran, remote image/CSS never loaded, live refresh, real-file Open, path refusal, placeholders, reports | real Chromium, offscreen |
| REAL 7B portfolio (`tests/test_integration_preview.py`) | **passed**: 3/3 files, no missing references (the model used inline SVG), local stylesheet applied | REAL model |
| Owner's existing `portfolio-website` | 2 missing images → placeholders; preview styled (CSS 18 rules, images 320 px) in source and in the packaged exe | REAL |
| Exe `--check` | version 1.2.1, both models present | REAL |

Notes: the System-theme test mocks the Windows scheme read (offscreen has none) but uses Qt's real
`colorSchemeChanged` signal. Chromium prints "context lost" GPU warnings offscreen; assertions are unaffected.

## Release 1.1.1 (Phase 14 — pre-publish cleanup, 2026-10-13)

- New test `tests/test_no_personal_paths.py` fails if a tracked text file contains `C:\Users\<name>`.
- Screenshots 06–09 retaken with `--basetemp D:\laa-demo\run` (REAL app test: 5/5 passed); all nine
  checked by eye for user names.
- Regression test: restored tool runs show "Checks passed"/"Checks failed" (schema v4 `messages.kind`).
- History rewritten with `git filter-repo` after a full backup; verification in the Phase 14 report.
- Known issue, re-measured: the pytest process can crash with 0xC0000409 during Qt teardown *after* all
  tests passed — 5 of 10 full runs on 2026-10-13 (normal mode, not only `--offline-guard`). Test results
  are unaffected; it has not been seen in the app or the packaged exe. Flushing Qt deletes at session end
  did not help and was reverted (third fix attempt).

## Release 1.1.0 verification (Phase 13 — Fast mode, 2026-10-12/13)

| Check | Result | Kind |
|---|---|---|
| `python -m compileall -q app main.py scripts` | exit 0 | — |
| `python -m pytest -v` | **628 passed, 1 skipped**, 11 deselected (integration) | MOCK model |
| `python -m pytest -m integration -v` | **10 passed, 1 failed** in the full run; the failure was Ollama's "timed out waiting for llama-server to start" while Windows slept (Kernel-Power 42 at 04:29, resume 06:50); that test **passed** when re-run alone (2.3 min) | REAL models |
| — new: `test_fast_is_prime_is_valid_python`, `test_fast_off_topic_question_is_redirected` on `qwen2.5-coder-7b:latest` | passed | REAL 7B |
| 14B vs 7B speed (3 cold runs each, `scripts/benchmark.py`) | 3.19 vs **6.40 tok/s**; cold load 15.9 vs 9.8 s; avg wall 101.5 vs 53.1 s | REAL |
| 7B to-do project (`scripts/run_java_sample.py --todo --model fast`) | run 1: test file rejected (2 blocks twice) → parser fix; run 2: 3/3 files, tests **passed after 2 repair rounds** (6.6 min) | REAL 7B |
| `python main.py --check` | version 1.1.0; both models listed, present; default = 14B | REAL |
| Rebuilt exe `--check` | exit 0, 322 MB, `Modelfile.fast` bundled; missing fast model shows the bundled create command | REAL |

Fast mode MOCK tests (`tests/test_fast_mode.py`): default is 14B; the toggle sends the 7B name and the stats
show it; the choice persists per chat across restart; v2→v3 migration keeps data; a missing 7B gives the amber
state with the exact command and sends **no** request (no fallback to 14B); a missing 14B while Fast is selected
still works with 7B; health checks cover both models with `/api/version` + `/api/tags` only; the Settings default
applies to new chats only; the plan card shows the Fast-mode note.

## Release 1.0.0 verification (Phase 12, 2026-10-12)

| Check | Result | Kind |
|---|---|---|
| `python -m compileall -q app main.py scripts` | exit 0 | — |
| `python -m pytest -v` | **611 passed, 1 skipped**, 9 deselected (integration) | MOCK model |
| `python -m pytest -m integration -v` | **9 passed** in 25.3 min | REAL model |
| Real-app end-to-end test (`tests/test_integration_app.py`, 5 steps) | 5/5 passed (3 consecutive clean runs after fixes) | REAL model, real UI (offscreen), real files/processes |
| — chat | streamed answer, highlighted code block that parses with `ast` | REAL |
| — stop | partial answer kept, marked stopped, Send restored | REAL |
| — project mode | plan card → generated to-do CLI → preview → "Project check passed" → pytest; the repair loop fixed a failing generated test in **1 round** | REAL |
| — export | ZIP created and verified | REAL |
| — restart | chats, project, file cards and preview restored | REAL |
| Packaged exe (`dist\LocalAIAssistant\LocalAIAssistant.exe --check`) | exit 0, version 1.0.0, model present; window opens; WebEngine preview renders; missing-model hint correct | REAL |
| Package size | 567 MB / 3,109 files → **322 MB / 137 files** | — |

Bugs found by the REAL app test and fixed, each with a regression test: replies replaced earlier
replies (test results deleted the generation summary and its file cards); the action row was painted
over the last lines of a finished answer; the plan file list and generation summary rendered as
run-on paragraphs; 4-backtick fences showed a stray backtick label; the export toast stayed visible.

## REAL model results

| Test | Result |
|---|---|
| `test_ensure_ready` — only `/api/version` + `/api/tags`, exact model match | PASSED |
| `test_is_prime_is_valid_python` — answer parses with `ast` and defines `is_prime` | PASSED |
| `test_off_topic_question_is_redirected` — cake recipe is redirected (tolerant check) | PASSED |
| `test_real_model_generates_small_python_project` — plan + 3 files, Python files parse | PASSED |
| Phase 1 timed request (cold) | 40.0 s load, 17 tokens at 2.7 tok/s, 75.4 s wall |
| Java sample run 1 (before the generator fixes) | FAILED, kept as evidence in `docs/samples/java-calculator-REPORT-run1.md`: JUnit used despite the request, GUI called methods `Calculator` lacked, README fence cut off, repair answer not parsed |
| Java sample run 2 (after the fixes) | PASSED — `docs/samples/java-calculator-REPORT.md`, project in `docs/samples/java-calculator/` |
| Repair demo | PASSED — `docs/samples/java-repair-REPORT.md` |

Fixes made because of run 1: file prompts now repeat the original request and include the
files already written; Markdown files are parsed leniently; edits written as "path on the line
before the block" (the format the system prompt asks for) are recognised.

## Areas covered (MOCK unless stated)

- **Ollama client**: streaming, NDJSON split across chunks, timeouts, abort over a real socket,
  404/model-missing, exact-name matching, no fallback, loopback-only URLs, health checks never call `/api/chat`.
- **Chat + UI**: streaming into widgets, Stop, Regenerate, error cards with Retry, UI stays responsive,
  stale worker signals cannot end a newer stream.
- **Storage (real SQLite)**: schema v1→v2 migration, newer-schema refusal (file hash unchanged),
  corrupt-file backup, rollback on injected failures, restart persistence, feedback, settings.
- **Agent**: strict plan/file parsing (valid, malformed, partial, unsafe), retry once, partial failures,
  plan/changes cards, backups, model text never executed (asserted).
- **Security**: 45 malicious paths ×2, junction escape, 47 allowlist bypass attempts, 12 shell-syntax
  strings, timeout kills the process tree (REAL processes), output truncation, UI reject flow.
- **Repair loop**: one-round fix, 3-round limit, cancel, rejected re-run, no usable fix.
- **Export**: exclusions (venv, caches, `.git`, backups, `.env`, keys, credentials…), `-2` collisions,
  README instructions, ZIP verification incl. damaged archives, failure cleanup, UI flow, settings persistence.
- **Offline**: socket guard, chat/generation/storage/export over loopback sockets with the internet blocked,
  remote Ollama URLs refused, HTML preview blocks remote requests.

## Known limitations and issues

1. **Speed**: ~3 tokens/s on this machine (model mostly on CPU). A 4-file project takes ~9 minutes.
2. **Intermittent exit crash in the guarded test mode**: `pytest --offline-guard` occasionally ends with
   exit code 0xC0000409 *after* all tests have passed (Qt abort during interpreter shutdown, no Python
   frame). Joining worker threads at exit (`shutdown_workers`) removed it from normal runs (5/5 clean);
   guarded runs were clean 4 times out of 6 afterwards. Not seen in the app or the packaged exe.
   Treat a guarded run as passed only when the summary line shows no failures.
3. ~~Phase 10 manual check pending~~ — **done** 2026-10-13: the owner ran the packaged exe with Wi-Fi off;
   chat, project generation, preview and ZIP export all worked.
4. ~~Manual UI prompt with the real model~~ — **done** as part of the owner's offline run above (chat in the
   windowed packaged app with the real model).
5. `main.py` and `app/ui/workers.py` show low coverage because they run in subprocesses / QThreads, which
   coverage does not trace; both are exercised by tests.
6. The packaged app is ~322 MB (QtWebEngine; it was 567 MB before the Phase 12 size reduction) and not code-signed (SmartScreen warning; see `docs/INSTALL.md`).
7. Running Python projects from the packaged app uses the `python` found on PATH (the app has no
   separate interpreter for user projects).
8. Error replies that had partial text are restored after a restart as the error card only.
9. The regenerate of a project request re-plans; plans that were never applied are not re-shown after restart
   (the plan text stays in the chat).
