# Test report

MOCK and REAL results are kept separate. MOCK tests use a fake Ollama (`tests/fake_ollama.py`)
or no model. REAL tests use the local Ollama model and are marked `integration`.

## MOCK: unit and GUI tests
Command: `python -m pytest` (integration tests are skipped by default, see `pytest.ini`).

| Date | Result |
|---|---|
| 2026-10-14 | 682 passed, 2 skipped, 11 deselected (integration), 0 warnings |

GUI tests run offscreen. Phase-by-phase results are in [docs/reports/](reports/PHASE_1_REPORT.md).

## REAL: local model
Command: `python -m pytest -m integration` (needs Ollama running and the exact model).

There are 11 real-model tests: `test_integration_app.py` (5), `test_integration_fast.py` (2),
`test_integration_generator.py` (1) and `test_integration_ollama.py` (3).
**They were not run in this checkout**, so there is no REAL result to report yet.

## Screenshots
The screenshots in the README are demo-mode captures (`python main.py --screenshot PATH --theme dark|glass`).
They use canned answers, not the model.
Real-model screenshots can be regenerated with
`python -m pytest -m integration tests/test_integration_app.py`, which writes them to `docs/screenshots/`.

## Known limitations
See the README's *Known limitations* section.
