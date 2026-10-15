# Offline checklist

The app talks only to Ollama on your own computer. This page has the automated checks and a short
manual check that you run yourself with the network off.

## What the app enforces
- **Ollama URL is loopback only.** `LAA_OLLAMA_URL` must point to `localhost`, `127.0.0.1` or `::1`;
  any other host is rejected at startup (`app/config.py`).
- **The HTML preview stays offline.** It uses an off-the-record profile and blocks every request except
  local ones (`data:`, `about:`, `blob:`, `qrc:`, `file:` and loopback `http(s)`/`ws(s)`)
  (`app/ui/offline_web.py`). "Open in default browser" is a separate action you start yourself.
- **No telemetry, no cloud APIs.**

## Automated checks
```powershell
python -m pytest tests/test_offline.py   # chat, generation, storage and export with non-loopback sockets blocked
python -m pytest --offline-guard         # the whole suite with non-loopback networking blocked
```
These use a fake Ollama on 127.0.0.1 (MOCK), not the real model.

## Manual check (Wi-Fi off)
1. Start Ollama and check `python main.py --check` shows the model as present.
2. Turn off Wi-Fi and unplug any network cable.
3. Start the app with `python main.py`. The sidebar should show *Ollama · Connected*.
4. Ask a short coding question and check that the answer streams in.
5. Turn on **Project mode**, generate a small project, open an HTML file and check that the
   **Preview** tab renders.
6. Export the project as a ZIP and check that the ZIP opens.
7. Close the app, start it again, and check that the chat and the project are still listed.
8. Turn the network back on.

If a step fails, the log is in the `logs` folder of the data directory (`python main.py --check` prints its path).
