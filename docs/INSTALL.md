# Installing Local AI Assistant

Local AI Assistant is a Windows 11 desktop app for coding help. It runs fully offline: all AI
answers come from a model running on your own computer through Ollama.

## 1. Prerequisites

| What | Why | How |
|---|---|---|
| Windows 11 (64-bit) | the app is a native Windows program | — |
| 16 GB RAM or more | the 14B model needs about 10 GB | — |
| ~12 GB free disk | model (9 GB) + app (~0.6 GB) | — |
| **Ollama** | runs the model locally | `winget install Ollama.Ollama`, or the installer from ollama.com |
| **Model** `qwen2.5-coder-14b:latest` | the only model the app uses | see step 2 |
| JDK 21 (optional) | compile/run generated Java projects | `winget install Microsoft.OpenJDK.21` |
| Git (optional) | `git` commands inside generated projects | `winget install Git.Git` |

A GPU is optional. On a CPU-heavy setup expect roughly 3 tokens per second, so long answers
take minutes (see Troubleshooting).

## 2. Set up Ollama and the model (needs internet once)

```powershell
ollama pull qwen2.5-coder:14b
```

Then create the exact model name the app expects, using the bundled Modelfile
(temperature 0.2, top_p 0.8, num_ctx 8192). From the app folder:

```powershell
ollama create qwen2.5-coder-14b -f ".\_internal\docs\Modelfile"
```

(From a source checkout use `ollama create qwen2.5-coder-14b -f .\ollama\Modelfile`.)
Check it: `ollama list` must show `qwen2.5-coder-14b:latest`. The app never uses another model
and never downloads anything itself.

## 3. Install the app

1. Copy the `LocalAIAssistant` folder (from `dist\LocalAIAssistant`) to a location such as
   `C:\Program Files\LocalAIAssistant` or `%LOCALAPPDATA%\Programs\LocalAIAssistant`.
2. Optional: right-click `LocalAIAssistant.exe` → *Show more options* → *Send to* → *Desktop (create shortcut)*.

Your data is stored separately in `%LOCALAPPDATA%\LocalAIAssistant`:

| Path | Contents |
|---|---|
| `assistant.db` | chat history (SQLite) |
| `projects\` | generated projects |
| `logs\app.log` | log file (no prompts or code are logged) |
| `logs\check.txt` | output of the last `--check` |

Deleting the app folder does not delete this data.

## 4. First run

1. Make sure Ollama is running (tray icon, or `ollama serve`).
2. Check the environment from PowerShell:
   ```powershell
   & "C:\path\to\LocalAIAssistant\LocalAIAssistant.exe" --check
   ```
   The summary is printed in the terminal and saved to `%LOCALAPPDATA%\LocalAIAssistant\logs\check.txt`.
   Look for `Ollama : running` and `Model present : yes (exact match)`.
3. Start `LocalAIAssistant.exe`. The sidebar status card shows **Ollama · Connected** (green).
4. Ask a coding question. Turn on **Project mode** to generate a multi-file project; review the
   plan, then click **Generate files**.
5. Commands (tests, compilers, git) only run from the approved list, inside the project folder,
   after you click **Approve**.

## 5. Troubleshooting

**"Ollama is not running at http://localhost:11434"** (red status) — start Ollama from the Start
menu or run `ollama serve`, then click **Retry**. The app only talks to `localhost`.

**"Model qwen2.5-coder-14b:latest is not installed"** (amber status) — run the `ollama create`
command from step 2. Similar models such as `qwen2.5-coder:14b` are listed but never used
automatically.

**Slow responses / "The model took too long to respond"** — the first answer loads the model
(up to a minute). `ollama ps` shows how much runs on CPU vs GPU; mostly-CPU means a few tokens per
second. Close other heavy programs, keep answers small, or raise the timeouts with environment
variables before starting the app, for example `$env:LAA_STREAM_READ_TIMEOUT_S = "600"`.
The command timeout is in **Settings**.

**Antivirus warns about LocalAIAssistant.exe** — PyInstaller-built apps are sometimes flagged as a
false positive because of how they unpack. The build does not use UPX packing to reduce this.
If your antivirus quarantines it, restore it and add an exclusion for the app folder only, or run
from source (`python main.py`).

**Windows SmartScreen: "Windows protected your PC"** — the app is not code-signed. Click
*More info* → *Run anyway* if you built or copied it yourself from a trusted source.

**The window opens but the HTML preview is blank** — previews block remote resources (CDN
scripts/fonts) on purpose, so pages that depend on them look incomplete. Use *Open in default
browser* if you want the full page.

**The app says the chat history database is damaged** — the old file is kept as
`assistant.db.corrupt-<time>` next to the new one; nothing is deleted. Choose *Start a fresh
database* or *Continue without saving history*.

**Where are the logs?** — `%LOCALAPPDATA%\LocalAIAssistant\logs\app.log`.
