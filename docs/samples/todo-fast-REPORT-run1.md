# Python to-do sample — REAL model run (qwen2.5-coder-7b:latest) — run 1

Recorded from the run log (at the time, the script wrote no report for BLOCKED runs).

- Ollama 0.40.2, model `qwen2.5-coder-7b:latest` (REAL)
  - model call: 18 s (126 tokens, 7.2 tok/s)
- Plan: `todo-cli`, 3 files: `todo.py`, `tests/test_todo.py`, `README.md`
  - [1/3] todo.py
  - model call: 46 s (279 tokens, 6.4 tok/s)
  - [2/3] tests/test_todo.py
  - model call: 51 s (298 tokens, 6.1 tok/s)
  - model call: 54 s (283 tokens, 5.7 tok/s)
  - [3/3] README.md
  - model call: 45 s (279 tokens, 6.5 tok/s)
- Generated into `%LOCALAPPDATA%\LocalAIAssistant\projects\todo-cli`: 2 written, failed: {'tests/test_todo.py': 'The answer must contain exactly one code block. (2 blocks)'}
- Project check passed.
- BLOCKED: no tests or sources were generated, nothing to run.

Result: the test file was answered with 2 code blocks twice (first try + corrective retry), so no tests existed to run. This led to the Phase 13 parser change: several blocks are accepted only if exactly one is in the file's language.
