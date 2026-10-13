# CLAUDE.md — Local AI Assistant

This file gives Claude Code the standing context and rules for this repository.
Read it fully before doing any work.

## Project

**Local AI Assistant** is a native Windows 11 desktop application for software development
tasks only: writing, debugging, explaining, reviewing and refactoring code, generating
multi-file projects, running approved tools and tests, and exporting projects.

It runs fully offline once the model and dependencies are installed.

## Fixed Technology Stack (do not change without explicit permission)

| Area | Technology |
|---|---|
| OS | Windows 11 |
| Language | Python |
| Desktop UI | PySide6 (Qt Widgets) |
| AI runtime | Ollama (local API at http://localhost:11434) |
| Model | `qwen2.5-coder-14b:latest` (default; exact name, never substitute) |
| Fast model (optional) | `qwen2.5-coder-7b:latest` — only when the user selects Fast mode (owner decision 2026-10-12) |
| Database | SQLite (`sqlite3`) |
| Tests | pytest |
| Packaging | PyInstaller |
| ZIP export | `pathlib`, `zipfile` (standard library) |

**Forbidden:** React, Node.js web frontends, Electron, browser-based UI, cloud LLM APIs,
silent model fallback.

## Project Structure

```
LocalAIAssistant/
  main.py
  requirements.txt
  README.md
  CLAUDE.md
  PLAN.md
  app/
    ui/          main_window.py, chat_view.py, code_view.py, project_preview.py, settings_view.py
    backend/     chat_service.py, ollama_client.py, task_classifier.py
    agent/       coding_agent.py, project_generator.py, tool_runner.py
    prompts/     coding_system_prompt.txt
    storage/     database.py
    validation/  path_validator.py, project_validator.py
    export/      project_exporter.py
  tests/         test_backend.py, test_ollama_client.py, test_storage.py,
                 test_agent.py, test_validation.py, test_export.py
  packaging/     LocalAIAssistant.spec
  data/          .gitkeep
```

Always inspect the existing repository before changing this structure.
Database and output paths must come from central configuration, not be hard-coded.

## Common Commands (PowerShell)

```powershell
# Activate virtual environment
.\venv\Scripts\Activate.ps1

# Run the app
python main.py

# Run tests
python -m pytest -v

# Check Ollama and model
ollama list
Invoke-RestMethod http://localhost:11434/api/tags
```

## Mandatory Development Rules

1. **One phase at a time.** Follow `PLAN.md`. Stop at the phase boundary and ask for approval.
2. **Inspect before modifying.** Read existing files before editing them.
3. **Preserve working code.** No unnecessary rewrites of the repository.
4. **Test after every phase.** Run `python -m pytest -v` and report real results.
5. **Never claim success without evidence.** Show actual test output and exit codes.
6. **No installs or downloads without permission.** No `pip install` or `ollama pull` unless approved.
7. **No global system changes** (PATH, environment variables, registry) without permission.
8. **No cloud AI APIs.** All inference goes through the local Ollama API.
9. **Never switch the model.** `qwen2.5-coder-14b:latest` is the default. The only other allowed model is
   `qwen2.5-coder-7b:latest`, used only when the user explicitly selects Fast mode for a chat (owner
   decision 2026-10-12). There is no silent fallback in either direction: if the selected model is
   missing, report it with the exact `ollama create` command and stop.
10. **Never execute arbitrary model-generated commands.** Use the allowlist in `tool_runner.py`.
11. **Show commands before running** anything that modifies files or the environment.
12. **Keep the UI responsive.** Long work (inference, generation, tests) runs in Qt worker threads.
13. **Report blockers honestly.**
14. **Update `PLAN.md`** (checklist and changelog) at the end of each phase.

Autonomous mode approved by owner on 2026-10-12 for Phases 5–11: plan, implement, test, commit and continue without waiting for approval.

## Security Requirements (enforced in code, not only by the prompt)

- The system prompt guides model behavior but is **not** a security boundary.
- Validate all output paths. Reject absolute paths, `..` traversal, and symlink escapes.
- Writes are allowed only inside the approved project output directory.
- Ask for confirmation before overwriting existing files.
- Commands run through an allowlist of executables and arguments, with timeouts.
- Capture stdout, stderr and exit codes. Never store secrets or credentials.

## Coding Style

- Python 3.10+ with type hints on public functions.
- Small, testable modules. UI code must not contain business logic.
- Use `logging` instead of `print` in application code.
- Raise clear custom exceptions (for example `OllamaUnavailableError`, `ModelNotFoundError`, `PathValidationError`).
- Mock Ollama in unit tests. Mark real-model tests with `@pytest.mark.integration`.

## Current Status

See `PLAN.md` for the active phase. Do not assume a phase has passed until its report confirms it.
