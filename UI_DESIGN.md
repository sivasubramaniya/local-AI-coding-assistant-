# UI_DESIGN.md — Local AI Assistant Desktop UI Specification

Reference screenshots: `docs/ui-reference/ref-1.png` … `ref-4.png`.
The app must match this **layout, dark theme, spacing and interaction model**, built
natively with **PySide6 Qt Widgets** (no browser UI). Use the app's own name and icons,
not any third-party product branding or logos.

---

## 1. Overall Layout (3 columns)

```
┌──────────────┬───────────────────────────────┬──────────────────────────┐
│  SIDEBAR     │  CHAT AREA                    │  PREVIEW PANEL           │
│  fixed 300px │  flexible, content centered   │  optional, resizable     │
│  collapsible │  max content width ~760px     │  closable (X)            │
└──────────────┴───────────────────────────────┴──────────────────────────┘
```

- Use a `QSplitter` between the chat area and the preview panel so the user can drag the divider (ref-1 vs ref-3).
- When the preview panel is closed, the chat area expands and its content stays centered (ref-4).
- The sidebar collapses to a thin icon rail via the collapse button.
- Minimum window size: 1100 × 700. Default: maximized.

---

## 2. Color Tokens (dark theme)

| Token | Hex | Use |
|---|---|---|
| `bg_app` | `#000000` | Chat area background |
| `bg_sidebar` | `#000000` | Sidebar background |
| `border_subtle` | `#1F1F1F` | Divider between sidebar and chat |
| `bg_item_hover` | `#1A1A1A` | Sidebar item hover |
| `bg_item_selected` | `#262626` | Selected chat in Recents |
| `bg_card` | `#171717` | File card, input bar |
| `border_card` | `#333333` | File card and input bar border |
| `bg_inline_code` | `#2A2A2A` | Inline `code` background |
| `bg_code_block` | `#0D0D0D` | Code block background |
| `text_primary` | `#ECECEC` | Main text |
| `text_secondary` | `#9B9B9B` | Section labels, status text, disclaimer |
| `accent_user_bubble` | `#1E4A8C` | User message bubble |
| `accent_primary` | `#2F6FE0` | Round send button, links, focus ring |
| `success` | `#3FB950` | Checkmarks, "Connected" dot |
| `error` | `#F85149` | Error states, "Disconnected" dot |
| `preview_bg` | gradient `#1E2A5A` → `#4B3A9A` | Empty preview panel background |

Put all tokens in one Python module (`app/ui/theme.py`) and generate a single QSS stylesheet from them.

---

## 3. Typography

- UI font: **Segoe UI** (Windows system font), fallback `Arial`.
- Code font: **Cascadia Code**, fallback `Consolas`.
- Sizes: app title 20px semibold; sidebar items 15px; section labels 14px `text_secondary`; message body 16px, line height ~1.6; message headings 16px bold; disclaimer 12px.

---

## 4. Sidebar (left)

Top to bottom:

1. **Header row:** app name "Local AI Assistant" (left, 20px semibold); search icon and collapse-sidebar icon (right).
2. **Primary actions** (icon + label, 40px rows, 8px radius on hover):
   - New chat
   - Search chats
   - Generated Projects
3. **Section label "Projects"** (`text_secondary`), then a list of generated projects with folder icons.
4. **Section label "Recents"**, then the chat history list (scrollable). The selected chat gets `bg_item_selected` with 10px rounded corners. Right-click opens a menu: Rename, Delete.
5. **Footer (pinned bottom):**
   - Model status card: a circular badge on the left, then `qwen2.5-coder-14b` (bold) above an "Ollama · Connected" line with a green dot. The dot turns red with "Disconnected" or "Model missing".
   - A full-width rounded outline button below it: **Settings**.

---

## 5. Chat Area (center)

### Top bar (right-aligned, 56px high)
- **Export** button (icon + label), the equivalent of "Share" in the reference.
- A file-tree toggle icon (opens or closes the preview panel).
- An overflow `⋯` menu: Rename chat, Export ZIP, Delete chat.

### Messages
- **User message:** right-aligned pill bubble, `accent_user_bubble`, white text, 20px radius, padding 12×20, max width ~70%.
- **Assistant message:** no bubble, left-aligned, full content width, `text_primary`.
  - Optional status line above the text in `text_secondary` (for example "Analyzed", "Generating project…", "Running tests…").
  - Markdown rendering: bold, numbered lists, headings, links, inline code (monospace on `bg_inline_code`, 4px radius), and fenced code blocks with syntax highlighting (Pygments) plus a Copy button in the block header.
  - Success lines may start with a green check.
- **File card** (for each generated or edited file): rounded rectangle, `bg_card`, 1px `border_card`, 14px radius, about 75% width. Icon on the left; filename (bold) above the file type (for example "HTML", "Python") in `text_secondary`. Clicking it opens the file in the Preview Panel.
- **Action row under each assistant message** (small 18px icons, `text_secondary`, hover to `text_primary`, tooltips): Copy, Export, Regenerate, Thumbs-down (marks a bad answer locally), `⋯` (more).

### Composer (bottom, pinned)
- Disclaimer line above it, centered, 12px `text_secondary`: "Local model output can contain mistakes. Review code before running."
- Rounded pill input bar (`bg_card`, `border_card`, 28px radius, about 64px tall, same width as the message column):
  - Left: `+` button (attach a file or folder from disk).
  - Center: multiline input with placeholder "Ask a coding question…". Enter sends; Shift+Enter inserts a newline. The bar grows up to 8 lines.
  - Right: a **Project mode** toggle chip (icon + label; when on, the request goes to the project generator), then the round **Send** button (40px, `accent_primary`, white icon). While generating, Send becomes a **Stop** (square) button that cancels.

---

## 6. Preview Panel (right)

- **Header bar (56px):**
  - Left: pill dropdown `</> filename ▾` listing all files of the current project, to switch files.
  - Right: three round icon buttons: **Save/Export** (download icon), **Expand** (full-window preview), **Close** (X).
- **Body:** a tab switch, **Code | Preview**.
  - Code: read-only code viewer with line numbers and syntax highlighting.
  - Preview: for `.html` files, a rendered preview; for Markdown, rendered text; for other types, the Code tab is shown.
  - Above the body, a collapsible file tree for multi-file projects.
- Empty state: `preview_bg` gradient with centered text "Select a file to preview".

---

## 7. States and Feedback

- Streaming text appears token by token, and the view auto-scrolls unless the user has scrolled up.
- Status line spinner while the model is generating, a project is being created, or tests are running.
- Errors appear as an inline red-bordered card in the chat (for example "Ollama is not running", "Model qwen2.5-coder-14b:latest not found") with a **Retry** button.
- Command-approval dialog: modal, dark, showing the command and working directory, with **Approve** and **Reject** buttons.

---

## 8. Qt Implementation Notes

- Sidebar: `QFrame` with a `QVBoxLayout`; Recents is a `QListView` with a custom delegate.
- Messages: a `QScrollArea` with a vertical stack of message widgets; markdown converted to HTML and shown in auto-height `QTextBrowser` widgets.
- Syntax highlighting: Pygments → HTML/CSS for message code blocks; a `QSyntaxHighlighter` or Pygments for the code viewer.
- HTML preview: `QWebEngineView` *only* for previewing generated HTML files (this is not the app UI). If QtWebEngine is unavailable or not approved, fall back to `QTextBrowser` (basic HTML) plus a "Open in default browser" button.
- Icons: SVG icons bundled in `app/ui/icons/` (an open-source line icon set such as Lucide or Tabler, with its license file).
- All long work runs in worker threads. UI updates go through Qt signals only.
