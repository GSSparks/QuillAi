<p align="center">
  <img src="./images/quillai_logo.svg" width="200" alt="QuillAI logo"/>
</p>

# QuillAI





**A privacy-first, AI-powered code editor built for developers who want AI assistance without sending their code to the cloud.**

QuillAI runs entirely on your machine when using a local LLM backend. No telemetry. No code uploaded to third-party servers. Your codebase stays yours.

Built with PyQt6. Supports local llama.cpp, any OpenAI-compatible API, and Anthropic Claude.

---

## Why QuillAI?

Every major AI coding tool — Copilot, Cursor, Tabnine — routes your code through external servers. QuillAI doesn't have to. When configured with a local LLM:

- **Your code never leaves your machine**
- **No API keys required**
- **No usage limits, no subscription**
- **Works offline**

When you do want cloud power (Claude, GPT-4, OpenRouter), you switch with one click in the status bar. The choice is always yours.

---

## Features

### Privacy-first AI backends
- **🏠 Local (llama.cpp)** — FIM (fill-in-middle) completions via a local llama.cpp server. Zero latency, zero cost, zero data sharing. Recommended: Qwen2.5-Coder for chat, any FIM-capable model for inline completions.
- **☁️ OpenAI / compatible** — any OpenAI-style API including OpenRouter, LM Studio, Ollama, and others
- **🟠 Anthropic (Claude)** — native Claude API with separate models for chat and inline completions

Switch backends at any time with the mode button in the status bar.

### Intent-aware inline completions
Completions aren't just based on what's at the cursor — they're informed by your whole session:
- Recent chat exchanges
- Pinned memory facts ("I always use type hints", "this project uses FastAPI")
- Files you've been editing
- Functions and classes you've been working in

Ghost text appears at natural pause points. **`Tab`** to accept, **`Ctrl+Right`** for word-by-word, **`Ctrl+Space`** to trigger manually.

### Project-aware AI chat
The chat panel knows about your entire project:
- Active file (head + tail for large files)
- All open tabs
- Direct and transitive imports (up to 3 levels deep)
- Project file tree
- Your memory facts and past conversation context

Responses stream live with syntax highlighting and markdown rendering. Code blocks have a one-click copy button.

### Memory system
QuillAI remembers things across sessions:
- **Global facts** — preferences that apply to all your work ("I prefer async functions", "always add type hints")
- **Project facts** — things specific to the current codebase
- **Conversation history** — past chat exchanges, searchable, clickable to restore

Facts are auto-extracted from your chat messages. Everything is stored locally at `~/.config/quillai/`.

### Session management
- Each project remembers which files you had open and where your cursor was
- Switching projects restores that project's tabs, chat history, and memory
- Recent Projects menu with tab count for each project

### Editor
- Syntax highlighting for Python, HTML, Ansible/YAML, Nix, Bash, and Markdown
- Line numbers with live git diff indicators (green = added, amber = modified)
- Minimap with click-to-navigate and viewport highlight
- Indent guides
- Auto-closing brackets, quotes, and braces
- Smart auto-indent on Enter
- `Ctrl+E` — AI rewrite of selected code with side-by-side diff preview
- `Ctrl+I` — inline chat popup at the cursor
- `Ctrl+G` — jump to line
- `Ctrl+D` — duplicate line or selection
- `Ctrl+/` — toggle comment (language-aware)

### Sliding panel
Chat, Memory, and settings live in a sliding panel on the right edge. Hover to expand, pin to keep open, drag the left edge to resize. Width persists across sessions.

### Markdown preview
Opens automatically when editing `.md` files. Live preview with syntax-highlighted code blocks, tables, and full CommonMark support. Floatable — drag it wherever you want on screen.

### Source control (Git)
- Changed files tree with status indicators
- Selective staging with checkboxes
- Inline diff viewer with syntax-coloured additions and removals
- Commit, push, and discard from within the editor

### Find & Replace / Find in Files
- **`Ctrl+F`** — live find/replace with match count
- **`Ctrl+Shift+F`** — search across the entire project

### Run & Debug
- **`F5`** — run the current Python script
- Output panel with stdout/stderr
- **💡 Explain Error** — sends the traceback and active file to the AI chat

### Snippet palette
- **`Ctrl+Shift+Space`** — fuzzy search across built-in snippets
- Snippets for Python, Ansible, Nix, and Bash
- User-editable at `~/.config/quillai/snippets.json`

---

## Requirements
```
Python 3.10+
PyQt6
requests
markdown
```

Optional but recommended:
```
pyyaml      # YAML/Ansible linting
chardet     # Encoding detection
shellcheck  # Bash linting (install via your package manager)
```

For local LLM support you need a running [llama.cpp](https://github.com/ggerganov/llama.cpp) server or any OpenAI-compatible local server (LM Studio, Ollama, etc.).

---

## Installation
```bash
git clone https://github.com/yourname/quillai
cd quillai
pip install PyQt6 requests pyyaml markdown chardet
python main.py
```

---

## Local LLM setup (recommended)

For the full privacy-first experience, run a local inference server:

**llama.cpp:**
```bash
./server -m your-model.gguf --port 11434 -c 8192
```

Then in QuillAI settings (`Ctrl+,`):
- Backend: Local
- Server URL: `http://localhost:11434/v1/chat/completions`

**Recommended models:**
- Chat: `Qwen2.5-Coder-32B-Q4_K_M` (32GB VRAM) or `Qwen2.5-Coder-7B-Q4_K_M` (8GB VRAM)
- Inline completions: any FIM-capable model, 7B or smaller for low latency

---

## Configuration

Open **File → Settings** (`Ctrl+,`) to configure:

| Section | Setting | Description |
|---|---|---|
| Local LLM | Server URL | llama.cpp or compatible server endpoint |
| Local LLM | Inline model | Fast model for ghost text completions |
| Local LLM | Chat model | Larger model for chat responses |
| OpenAI | API URL | Defaults to `api.openai.com`, supports any compatible endpoint |
| OpenAI | API Key | `sk-...` key |
| OpenAI | Chat model | e.g. `gpt-4o` |
| Anthropic | API Key | `sk-ant-...` from console.anthropic.com |
| Anthropic | Chat model | e.g. `claude-sonnet-4-6` |
| Anthropic | Inline model | e.g. `claude-haiku-4-5-20251001` |

All settings stored locally at `~/.config/quillai/settings.json`.

---

## Keybindings

| Key | Action |
|---|---|
| `Ctrl+Space` | Trigger inline AI completion |
| `Tab` | Accept full ghost text suggestion |
| `Ctrl+Right` | Accept next word of suggestion |
| `Ctrl+Shift+Space` | Open snippet palette |
| `Ctrl+E` | AI rewrite of selection (with diff preview) |
| `Ctrl+I` | Inline chat at cursor |
| `Ctrl+Return` | Send chat message |
| `Ctrl+G` | Go to line |
| `Ctrl+D` | Duplicate line or selection |
| `Ctrl+/` | Toggle comment |
| `Ctrl+]` | Indent selection |
| `Ctrl+[` | Unindent selection |
| `Ctrl+F` | Find / replace |
| `Ctrl+H` | Find / replace (focus replace field) |
| `Ctrl+Shift+F` | Find in files |
| `Ctrl+N` | New tab |
| `Ctrl+O` | Open file |
| `Ctrl+S` | Save |
| `Ctrl+Shift+S` | Save as |
| `Ctrl+,` | Settings |
| `F5` | Run script |

---

## Project structure
```
quillai/
├── main.py                    # Main window and application entry point
├── ai/
│   └── worker.py              # AIWorker — all LLM backends and streaming
├── editor/
│   ├── ghost_editor.py        # Editor with ghost text, minimap, inline chat
│   └── highlighter.py         # Syntax highlighter registry
├── plugins/
│   ├── python_plugin.py
│   ├── html_plugin.py
│   ├── ansible_plugin.py
│   ├── nix_plugin.py
│   ├── bash_plugin.py
│   ├── markdown_plugin.py
│   └── git_plugin.py          # Git dock — status, diff, commit, push
└── ui/
    ├── menu.py                # File menu and recent projects
    ├── chat_renderer.py       # Chat rendering, streaming, syntax highlighting
    ├── sliding_chat_panel.py  # Sliding panel with Chat and Memory tabs
    ├── memory_manager.py      # Per-project memory, facts, conversations
    ├── memory_panel.py        # Memory panel UI
    ├── session_manager.py     # Per-project tab session save/restore
    ├── intent_tracker.py      # Session intent for smarter completions
    ├── find_replace.py
    ├── find_in_files.py
    ├── markdown_preview.py
    ├── snippet_palette.py
    ├── settings_manager.py
    ├── settings_dialog.py
    └── diff_viewer.py
```

---

## Data & privacy

All user data is stored locally:

| Data | Location |
|---|---|
| Settings | `~/.config/quillai/settings.json` |
| Memory & facts | `~/.config/quillai/memory/` |
| Chat history | `~/.config/quillai/memory/chat_*.html` |
| Sessions | `~/.config/quillai/sessions/` |
| Snippets | `~/.config/quillai/snippets.json` |

When using a local backend, no data is transmitted anywhere. When using a cloud backend, only the content you explicitly send in a chat message or the code context you've configured is transmitted to that provider — nothing else.

---

## Roadmap

- [ ] Code timeline — per-file local history without git
- [ ] Embedded terminal
- [ ] Command palette (`Ctrl+P`)
- [ ] TODO/FIXME panel
- [ ] Session debrief — AI summary of what changed each session
- [ ] Passive code review — background suggestions without interrupting flow

---

## License

MIT