"""DEMO ONLY in-memory content (no model, no database).

Used by ``--demo`` and screenshot mode, which always run on an InMemoryChatStore.
"""

from __future__ import annotations

from app.backend.chat_store import ChatMessage, ChatStore

DEMO_STATUS = "Demo response · no model connected"
DEMO_PROJECT_NAME = "welcome-site"

DEMO_FILES: dict[str, str] = {
    "welcome.html": """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Welcome</title>
  <style>
    body {
      margin: 0;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      font-family: "Segoe UI", Arial, sans-serif;
      color: #ffffff;
      background: linear-gradient(135deg, #1e2a5a, #4b3a9a);
    }
    .card {
      text-align: center;
      padding: 48px 40px;
      border-radius: 24px;
      box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.15);
    }
    h1 { font-size: 48px; margin: 16px 0; }
    button {
      border: none;
      border-radius: 999px;
      padding: 14px 32px;
      font-size: 18px;
      font-weight: 600;
      color: #3b3bb3;
      background: #ffffff;
      cursor: pointer;
    }
  </style>
</head>
<body bgcolor="#2c2f73" text="#ffffff">
  <div class="card" align="center">
    <h1>Welcome!</h1>
    <p>We're glad you're here. This is your starting point for something great.</p>
    <p><button onclick="alert('Let\\'s build something!')">Get Started</button></p>
    <p><small>Made with care</small></p>
  </div>
</body>
</html>
""",
    "server.py": '''"""Serve the welcome site on http://localhost:8000."""

from http.server import HTTPServer, SimpleHTTPRequestHandler


def serve(port: int = 8000) -> None:
    """Serve the current folder until Ctrl+C is pressed."""
    server = HTTPServer(("127.0.0.1", port), SimpleHTTPRequestHandler)
    print(f"Serving on http://localhost:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopped.")


if __name__ == "__main__":
    serve()
''',
    "README.md": """# Welcome Site

A one-page welcome screen with a gradient background and a **Get Started** button.

## Run it

1. Double-click `welcome.html`, or
2. Run `python server.py` and open <http://localhost:8000/welcome.html>.

## Files

| File | Purpose |
|---|---|
| `welcome.html` | The page, with inline CSS |
| `server.py` | A tiny local web server |
""",
}

DEMO_ANSWER = """✅ I created your **Welcome HTML page** with a modern design, a gradient background, a welcome message and a working **Get Started** button.

### How to open it on Windows

1. Open the `welcome-site` folder.
2. Double-click `welcome.html`.
3. It opens in your default web browser.

To serve it locally instead, run the small Python server below:

```python
from http.server import HTTPServer, SimpleHTTPRequestHandler


def serve(port: int = 8000) -> None:
    \"\"\"Serve the current folder on http://localhost:<port>.\"\"\"
    server = HTTPServer(("127.0.0.1", port), SimpleHTTPRequestHandler)
    print(f"Serving on http://localhost:{port}")
    server.serve_forever()
```

You can also open the files in **VS Code** to edit the HTML and CSS.
"""

DEMO_ANSWER_FILES = ["welcome.html"]

DEMO_RECENTS = [
    "PowerShell backup script",
    "SQLite schema review",
    "Refactor Java calculator",
    "Flask login bug",
]
WELCOME_CHAT_TITLE = "Create Welcome HTML File"
WELCOME_PROMPT = "create a welcome html file web"


def seed_demo_store(store: ChatStore) -> str:
    """Fill the store with demo chats. Returns the id of the most recent chat."""
    for title in DEMO_RECENTS:
        chat = store.create_chat(title)
        store.add_message(chat.id, ChatMessage("user", f"Help me with: {title.lower()}"))
        store.add_message(
            chat.id,
            ChatMessage("assistant", f"_Demo history for **{title}**. No model is used in demo mode._"),
        )
    welcome = store.create_chat(WELCOME_CHAT_TITLE)
    store.add_message(welcome.id, ChatMessage("user", WELCOME_PROMPT))
    store.add_message(
        welcome.id,
        ChatMessage("assistant", DEMO_ANSWER, files=list(DEMO_ANSWER_FILES)),
    )
    return welcome.id
