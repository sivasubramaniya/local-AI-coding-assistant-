# Local AI Assistant

A native Windows 11 desktop coding assistant built with Python and PySide6. It talks only to a
local Ollama model (`qwen2.5-coder-14b:latest`) and works fully offline once installed.

Status: Phase 3 (native desktop UI with demo data). The window shows canned demo answers
until the Ollama connection is added in Phase 4.

## Prerequisites

- Windows 11
- Python 3.12 (3.10 to 3.12 supported)
- [Ollama](https://ollama.com) running locally on `http://localhost:11434`
- The model, under its exact name:

  ```powershell
  ollama pull qwen2.5-coder:14b
  ollama cp qwen2.5-coder:14b qwen2.5-coder-14b:latest
  ollama list
  ```

## Setup

```powershell
py -V:3.12 -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
```

Use `requirements.txt` instead if you only need to run the app.

## Run

```powershell
python main.py --check   # print an environment summary and exit
python main.py           # open the desktop window
python main.py --screenshot shot.png [--delay 800] [--no-preview]   # scripted demo + window capture
```

The HTML preview uses QtWebEngine when it is installed (`pip install PySide6==6.12.0`).
Without it, a basic `QTextBrowser` preview is shown with an "Open in default browser" button.

## Tests

```powershell
python -m pytest -v                    # unit + GUI tests (GUI runs offscreen; integration excluded)
python -m pytest -v -m "not gui"       # skip the Qt widget tests
python -m pytest -v -m integration     # tests that need a real Ollama model
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

Logs are written to `<data dir>\logs\app.log`.
