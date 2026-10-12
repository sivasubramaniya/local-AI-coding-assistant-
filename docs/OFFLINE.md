# Offline Readiness — Local AI Assistant

Local AI Assistant is designed to run with no internet connection once the tools below
are installed. This document lists the required local tools, how offline behaviour is
verified automatically, and a manual checklist for the owner to run with Wi-Fi off.

## Required local tools

| Tool | Version used | Needed for | Required? |
|---|---|---|---|
| Windows 11 | 10.0.26300 | everything | yes |
| Python | 3.12.10 (in `venv`) | running from source | yes (source runs only; the packaged build bundles it) |
| Ollama | 0.40.2 | local model server on `http://localhost:11434` | yes |
| Model `qwen2.5-coder-14b:latest` | from `qwen2.5-coder:14b` + `ollama/Modelfile` | all AI answers | yes |
| JDK (Microsoft OpenJDK 21) | 21.0.12 | compiling/running generated Java projects | optional |
| Git | system Git | `git status/diff/log/init/add/commit` in projects | optional |

Create the model once, from the project folder:

```powershell
ollama pull qwen2.5-coder:14b          # needs internet, once
ollama create qwen2.5-coder-14b -f .\ollama\Modelfile
```

## What can never reach the internet

- **Model calls**: `app/config.py` accepts only `localhost`, `127.0.0.1` or `::1` as the Ollama
  URL (any other host is a configuration error before a request is made). `httpx` runs with
  `trust_env=False`, so proxy environment variables are ignored. There is no fallback model and
  no cloud API.
- **HTML preview**: QtWebEngine uses an off-the-record profile with a request interceptor that
  blocks every `http(s)`/`ws(s)`/`ftp` request to a non-loopback host (`app/ui/offline_web.py`).
  A generated page that loads a CDN script shows without it. "Open in default browser" is a
  separate action you choose; your browser may then try to load such resources.
- **No telemetry, update checks or analytics** exist in the code (audit below).

## Code audit (2026-10-12)

Commands run from the project folder (Git Bash):

```bash
# 1. every URL in app code, minus loopback
grep -rnoE "https?://[^\"' )>]+" app main.py scripts | grep -vE "localhost|127\.0\.0\.1|\[::1\]"
# 2. network modules
grep -rnE "^\s*(import|from) (requests|urllib|http\.client|socket|aiohttp|websocket|ftplib|smtplib)" app main.py
# 3. cloud SDKs and telemetry words
grep -rniE "openai|anthropic|googleapis|boto3|azure|telemetry|analytics|sentry|update.?check|posthog|mixpanel" app main.py requirements.txt
# 4. HTTP clients
grep -rn "httpx\.\(Client\|get\|post\|AsyncClient\)" app
```

Results:

1. Only `http://www.w3.org/2000/svg` in the bundled SVG icons — an XML namespace name, never fetched.
2. Only `from urllib.parse import urlparse` in `app/config.py` (string parsing, no network).
3. No matches.
4. One: `httpx.Client(base_url=config.ollama_url, ..., trust_env=False)` in `app/backend/ollama_client.py`.

Runtime dependencies (`requirements.txt`): PySide6 (+ WebEngine for the HTML preview), httpx,
pygments, markdown — none of them phone home in the way the app uses them.

## Automated offline tests

`tests/offline_guard.py` patches `socket.create_connection`, `socket.socket.connect/connect_ex`
and `socket.getaddrinfo` so only loopback addresses can be reached; anything else raises and is
recorded.

- `tests/test_offline.py` runs chat, project generation, SQLite storage and ZIP export through
  **real loopback sockets** (a fake Ollama on 127.0.0.1 — the model is MOCK) with the guard on,
  checks that "Ollama stopped" and "model missing" give clear errors, that remote Ollama URLs are
  refused, and that the HTML preview profile is off-the-record with the blocking interceptor.
- The **whole suite** can run under the guard: `python -m pytest --offline-guard`.

## Manual checklist (owner, Wi-Fi off)

Claude Code needs the internet, so these steps must be done by you:

1. Turn Wi-Fi off / unplug the network cable. Confirm `Test-NetConnection 8.8.8.8 -Port 53` fails.
2. Start Ollama (tray app or `ollama serve`). Run `ollama list` — `qwen2.5-coder-14b:latest` is listed.
3. Run `python main.py --check` — Ollama "running", Model present "yes (exact match)".
4. Start the app (`python main.py` or `dist\LocalAIAssistant\LocalAIAssistant.exe`). The status card
   shows **Ollama · Connected**.
5. Ask "Write is_prime in Python" — the answer streams; Stop works.
6. Turn on **Project mode**, ask for a small Python project, click **Generate files** — files appear
   in the preview panel.
7. Close and reopen the app — the chat and its project are still there.
8. **Export** and **Export ZIP** to the Desktop — the success card appears; open the folder.
9. Run the project tests (⋯ → Run project tests) and approve — output appears.
10. Quit Ollama and send a message — a clear "Ollama is not running" card appears; the app keeps working.
11. Turn the network back on.

Record any step that fails with the exact message shown.
