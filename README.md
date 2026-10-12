# Local AI Assistant

A native Windows 11 desktop coding assistant built with Python and PySide6. It talks only to a
local Ollama model (`qwen2.5-coder-14b:latest`) and works fully offline once installed.

Status: Phases 1–11 built (Phase 10's Wi-Fi-off manual checklist is pending). Chat with the local model, persistent SQLite history, Project mode generator, edit/repair loop with approved commands, export to folder/ZIP, and a PyInstaller build. See `PLAN.md`, `docs/TEST_REPORT.md`, `docs/INSTALL.md` and `docs/OFFLINE.md`.

## Prerequisites

- Windows 11
- Python 3.12 (3.10 to 3.12 supported)
- [Ollama](https://ollama.com) running locally on `http://localhost:11434`
- The model, under its exact name `qwen2.5-coder-14b:latest`. Run this from the project folder:

  ```powershell
  ollama pull qwen2.5-coder:14b
  ollama create qwen2.5-coder-14b -f .\ollama\Modelfile
  ollama list
  ```

  `ollama/Modelfile` builds the exact name from the official model with this app's settings.
  The app never falls back to another model.

## Setup

```powershell
py -V:3.12 -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
```

Use `requirements.txt` instead if you only need to run the app.

## Run

```powershell
python main.py --check   # environment summary, contacts Ollama (warns if the model is missing)
python main.py           # open the desktop window (answers come from the local model)
python main.py --demo    # canned demo answers, no model needed
python main.py --screenshot shot.png [--delay 800] [--no-preview]   # scripted demo + window capture
```

The HTML preview uses QtWebEngine when it is installed (`pip install PySide6==6.12.0`).
Without it, a basic `QTextBrowser` preview is shown with an "Open in default browser" button.

## Using it

- **Chat**: ask a coding question; answers stream from the local model. Chats are saved and reopen on start.
- **Project mode** (chip in the composer): the model plans the files first (Plan card); nothing is written until
  you click **Generate files**. Projects are saved under `%LOCALAPPDATA%\LocalAIAssistant\projects`.
- **Edits**: in a project chat, ask to fix or refactor; suggested changes appear as a diff (Changes card) and are
  written only after **Apply changes** (originals kept as `<file>.bak-<time>`).
- **Run project tests** (⋯ menu): runs allowlisted commands (`python -m pytest`, `javac`/`java`) inside the project
  after you approve them; failures start a repair loop of at most 3 model-proposed fixes.
- **Export / Export ZIP**: copies the project (without caches, venvs, backups or secrets) to a folder you choose;
  ZIPs are verified before success is reported. **Settings** holds the export folder and command timeout.

## Build the Windows app

```powershell
.\venv\Scripts\pyinstaller packaging\LocalAIAssistant.spec --noconfirm
dist\LocalAIAssistant\LocalAIAssistant.exe --check
```

See `docs/INSTALL.md` for installation and troubleshooting.

## Tests

```powershell
python -m pytest -v                    # unit + GUI tests (GUI runs offscreen; integration excluded)
python -m pytest -v -m "not gui"       # skip the Qt widget tests
python -m pytest -v -m integration     # tests that need a real Ollama model
python -m pytest --offline-guard       # whole suite with non-loopback sockets blocked
python -m pytest --cov=app             # coverage (pytest-cov from requirements-dev.txt)
.\venv\Scripts\python.exe scripts\run_java_sample.py   # REAL end-to-end Java sample (slow)
```

## Configuration

Settings live in `app/config.py`. Override them with environment variables:

| Variable | Default |
|---|---|
| `LAA_OLLAMA_URL` | `http://localhost:11434` |
| `LAA_DATA_DIR` | `%LOCALAPPDATA%\LocalAIAssistant` |
| `LAA_EXPORT_DIR` | your Desktop |
| `LAA_LOG_LEVEL` | `INFO` |
| `LAA_REQUEST_TIMEOUT_S` / `LAA_CONNECT_TIMEOUT_S` | `120` / `5` |
| `LAA_TEMPERATURE` / `LAA_TOP_P` / `LAA_NUM_CTX` | `0.2` / `0.8` / `8192` |
| `LAA_MODEL_NAME` | `qwen2.5-coder-14b:latest` (overriding logs a warning) |
| `LAA_KEEP_ALIVE` | `10m` (how long Ollama keeps the model loaded) |
| `LAA_STREAM_READ_TIMEOUT_S` | `300` (max gap between streamed chunks, including model load) |
| `LAA_HEALTH_INTERVAL_S` | `10` (status card check interval) |
| `LAA_COMMAND_TIMEOUT_S` | `60` (approved commands; also in Settings) |

`LAA_OLLAMA_URL` must point at this computer (`localhost`, `127.0.0.1` or `::1`).
Any other host is rejected, so no remote or cloud service can be called.

Logs are written to `<data dir>\logs\app.log`.
