---
name: phase-workflow
description: Use when implementing, continuing or reporting on any numbered phase of the Local AI Assistant project (PLAN.md). Enforces inspect → implement → test → report → stop.
---

# Phase Workflow — Local AI Assistant

Follow these steps exactly whenever you work on a phase from `PLAN.md`.

## 1. Orient

1. Read `CLAUDE.md` and `PLAN.md`.
2. Confirm which phase is active. If the user did not name one, ask.
3. Confirm all earlier phases are marked `[x]`. If not, stop and report.
4. Restate the phase goal and its restrictions in 2–3 lines.

## 2. Inspect

1. List the files this phase will touch or create.
2. Read every existing file before modifying it.
3. Run `python -m pytest -q` to record the baseline test state.
4. Note anything that is already broken. Do not fix unrelated problems silently.

## 3. Plan

Present a short plan before writing code:

- Files to create
- Files to modify (and why)
- New tests to add
- Commands you will run
- Any packages needed (ask for permission. Never install without approval)

Wait for approval if the plan installs packages, changes structure, or deletes anything.

## 4. Implement

- Make small, focused changes. Preserve working code.
- Keep business logic out of UI classes.
- Long-running work goes in Qt worker threads.
- Read paths and settings from `app/config.py`. Never hard-code user paths.
- Never call cloud APIs. Never change the model name.
- Never run model-generated commands directly.

## 5. Test

1. Add or update tests in `tests/` for every new module.
2. Mock Ollama in unit tests. Mark real-model tests `@pytest.mark.integration`.
3. Run `python -m pytest -v` and capture the full output.
4. If tests fail, fix them and re-run. Do not hide failures.

## 6. Report

Use this format:

```
## Phase N Report — <name>
### Summary
### Files Created
### Files Modified
### Commands Run
### Test Results (paste real pytest summary: passed / failed / skipped)
### Mock vs Real (what was tested against real Ollama vs mocks)
### Known Issues / Limitations
### Blockers
### Next Phase Preview (bullets only)
```

## 7. Update and Stop

1. In `PLAN.md`, tick completed items and set the phase status (`[x]` only if tests pass).
2. Add one row to the Changelog table.
3. **Stop.** Do not start the next phase. Ask the user for approval.
