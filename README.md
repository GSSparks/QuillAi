<p align="center">
  <img src="./images/quillai_logo.svg" width="400" alt="QuillAI logo"/>
</p>

# QuillAI

<p align="center">
  <img src="./images/Screenshot.png" width="900" alt="QuillAI editor showing find/replace, minimap, git panel, and find in files"/>
</p>

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

## Installation

### AppImage (Linux — easiest)

Download the latest AppImage from the [Releases](../../releases) page:

```bash
chmod +x QuillAI-*.AppImage
./QuillAI-*.AppImage
```

> **NixOS users:** AppImages require `appimage-run` or system-level support.
> ```bash
> nix run nixpkgs#appimage-run -- ./QuillAI-*.AppImage
> ```
> Or add to `configuration.nix` for double-click support:
> ```nix
> programs.appimage = { enable = true; binfmt = true; };
> ```

### Nix / NixOS

```bash
# Run directly
nix run github:GSSparks/quillai

# Or install to your profile
nix profile install github:GSSparks/quillai
```

### From source

```bash
git clone https://github.com/GSSparks/quillai
cd quillai
pip install PyQt6 requests pyyaml markdown chardet
python main.py
```

For Nix development:
```bash
nix develop
python main.py
```

---

## Features

### Privacy-first AI backends
- **🏠 Local (llama.cpp)** — FIM completions via a local llama.cpp server. Zero latency, zero cost, zero data sharing. Recommended: Qwen2.5-Coder.
- **☁️ OpenAI / compatible** — any OpenAI-style API including OpenRouter, LM Studio, Ollama, and others
- **🟠 Anthropic (Claude)** — native Claude API with separate models for chat and inline completions

Switch backends at any time with the mode button in the status bar.

### Intent-aware inline completions
Completions are informed by your whole session — recent chat exchanges, pinned memory facts, files you've been editing, and functions you've been working in. Ghost text appears at natural pause points. **`Tab`** to accept, **`Ctrl+Right`** for word-by-word, **`Ctrl+Space`** to trigger manually.

### Project-aware AI chat
The chat panel understands your entire project: active file and the symbol you're working in, all open tabs, direct and transitive imports (up to 3 levels deep), LSP hover docs and live diagnostics, a structural repo map of the whole codebase, semantic search across your codebase history, and your memory facts. Responses stream live with syntax highlighting and markdown rendering. Code blocks have a one-click copy button.

### LSP integration
QuillAI connects to language servers automatically when installed, giving you IDE-grade code intelligence across multiple languages:

- **Hover tooltips** — signature and docstring for any symbol, shown on mouseover
- **Ctrl+Click go-to-definition** — jump to where a function or class is defined, across files
- **Diagnostic squiggles** — live error and warning underlines as you type
- **Context-aware chat** — LSP hover info and diagnostics are automatically injected into every chat prompt

Supported servers (all included in the Nix package):

| Language | Server |
|---|---|
| Python | `python-lsp-server` |
| YAML / Ansible | `yaml-language-server` |
| JavaScript / TypeScript | `typescript-language-server` |
| Bash / Shell | `bash-language-server` |
| HTML / CSS / JSON / Markdown | `vscode-langservers-extracted` |
| Nix | `nil` |
| Lua | `lua-language-server` |

LSP degrades gracefully — everything works normally if a server is not installed.

### Repo map
QuillAI builds a structural map of your entire project on open — every file, every class, every function signature and docstring — and injects a query-filtered slice of it into every chat prompt. The model gets a navigational overview of the whole codebase without the token cost of full source. Ansible playbooks and role imports are followed and included.

The map is built in a background thread on project open, invalidated on file save, and filtered per-query so only structurally relevant files are included.

### Vector index
QuillAI builds a semantic search index over your entire project that grows smarter with use. Four collections are indexed and searched on every chat message:

- **Code** — every function and class, chunked by AST symbol, searchable by meaning not just name
- **Conversations** — past chat exchanges, so similar problems surface relevant history
- **Completions** — ghost text you have accepted, building a model of your patterns over time
- **Edit patterns** — files you edit together, surfaced when working in related areas

Uses `sentence-transformers` locally (no API required) or OpenAI embeddings when in cloud mode. The longer you use QuillAI on a project, the more relevant its suggestions become.

### Memory system
QuillAI remembers things across sessions:
- **Global facts** — preferences that apply to all your work
- **Project facts** — things specific to the current codebase
- **Conversation history** — past exchanges, searchable, clickable to restore
- **Turn buffer** — recent messages are always included verbatim so the AI has genuine conversational continuity within a session, not just summaries

Facts are auto-extracted from your chat messages. Everything is stored locally at `~/.config/quillai/`.

### Multi-cursor editing
Full multi-cursor support — every keystroke, deletion, and paste applies to all cursors simultaneously with atomic undo:

- **`Ctrl+D`** — add cursor at next occurrence of selected word (press again to step through)
- **`Ctrl+Shift+L`** — add cursors at all occurrences in the file
- **`Ctrl+Alt+Up/Down`** — add cursor on line above/below (column mode)
- **`Alt+Click`** — add cursor at any position (click again to remove)
- **`Escape`** — clear all secondary cursors, return to single cursor

### Crash recovery
QuillAI autosaves every 2 minutes to `~/.config/quillai/autosave/`. If the app crashes, your work is silently restored on next launch — no dialog, no friction. Recovered tabs are marked with ↩ in their title until saved. On clean exit, autosave files are removed automatically.

### Command palette
**`Ctrl+P`** — fuzzy search across open tabs, all project files, and editor actions in a unified list. Arrow keys or Tab to navigate, Enter to open, Esc to dismiss.

### Embedded terminal
**`Ctrl+\``** — toggle a full terminal docked at the bottom. Uses `qtermwidget` for a full PTY experience when available, with a QProcess-driven interactive shell as fallback. Working directory follows the open project automatically.

### Session management
Each project remembers which files you had open and where your cursor was. Switching projects restores that project's tabs, chat history, and memory. Recent Projects menu with tab count for each entry.

### Editor
- Syntax highlighting for Python, HTML, Ansible/YAML, Nix, Bash, and Markdown
- Line numbers with live git diff indicators (green = added, amber = modified)
- Double-click line number to select the entire line
- Minimap with click-to-navigate and viewport highlight
- Git blame in the gutter — toggle per-file to see commit hash and author per line
- Bracket match highlighting
- Indent guides, auto-closing brackets, smart auto-indent
- `Ctrl+E` — AI rewrite of selection with side-by-side diff preview
- `Ctrl+I` — inline chat popup at the cursor
- `Ctrl+G` — jump to line, `Ctrl+Shift+D` — duplicate line, `Ctrl+/` — toggle comment

### Sliding panel
Chat and Memory live in a sliding panel on the right edge. Hover to expand, pin to keep open, drag the left edge to resize. Width persists across sessions.

### Markdown preview
Opens automatically when editing `.md` files. Live preview with full CommonMark support. Floatable — drag it wherever you want on screen.

### Source control (Git)
Changed files tree, selective staging with checkboxes, inline diff viewer, commit/push/discard — plus AI-generated commit messages from your staged diff.

### Find & Replace / Find in Files
- **`Ctrl+F`** — live find/replace with match count
- **`Ctrl+Shift+F`** — search across the entire project

### Run & Debug
**`F5`** — run the current Python script. Output panel with stdout/stderr and a **💡 Explain Error** button that sends the traceback to the AI chat.

### Snippet palette
**`Ctrl+Shift+Space`** — fuzzy search across built-in snippets for Python, Ansible, Nix, and Bash. User-editable at `~/.config/quillai/snippets.json`.

---

## Local LLM setup

**llama.cpp:**
```bash
./server -m your-model.gguf --port 11434 -c 8192
```

Then in QuillAI settings (`Ctrl+,`):
- Server URL: `http://localhost:11434/v1/chat/completions`

**Recommended models:**
- Chat: `Qwen2.5-Coder-32B-Q4_K_M` (32GB VRAM) or `Qwen2.5-Coder-7B-Q4_K_M` (8GB VRAM)
- Inline completions: any FIM-capable model, 7B or smaller for low latency

---

## Configuration

Open **File → Settings** (`Ctrl+,`):

| Section | Setting | Description |
|---|---|---|
| Local LLM | Server URL | llama.cpp or compatible endpoint |
| Local LLM | Inline model | Fast model for ghost text |
| Local LLM | Chat model | Larger model for chat |
| OpenAI | API URL | Defaults to `api.openai.com` |
| OpenAI | API Key | `sk-...` |
| OpenAI | Chat model | e.g. `gpt-4o` |
| Anthropic | API Key | `sk-ant-...` |
| Anthropic | Chat model | e.g. `claude-sonnet-4-6` |
| Anthropic | Inline model | e.g. `claude-haiku-4-5-20251001` |

All settings stored locally at `~/.config/quillai/settings.json`.

---

## Keybindings

| Key | Action |
|---|---|
| `Ctrl+P` | Command palette |
| `Ctrl+Space` | Trigger inline AI completion |
| `Tab` | Accept full ghost text suggestion |
| `Ctrl+Right` | Accept next word of suggestion |
| `Ctrl+Shift+Space` | Open snippet palette |
| `Ctrl+E` | AI rewrite of selection (with diff preview) |
| `Ctrl+I` | Inline chat at cursor |
| `Ctrl+Click` | Go to definition (LSP) |
| `Ctrl+Return` | Send chat message |
| `Ctrl+\`` | Toggle terminal |
| `Ctrl+D` | Multi-cursor: add next occurrence |
| `Ctrl+Shift+L` | Multi-cursor: add all occurrences |
| `Ctrl+Alt+Up/Down` | Multi-cursor: add cursor above/below |
| `Alt+Click` | Multi-cursor: add cursor at position |
| `Escape` | Clear secondary cursors |
| `Ctrl+G` | Go to line |
| `Ctrl+Shift+D` | Duplicate line or selection |
| `Ctrl+/` | Toggle comment |
| `Ctrl+]` | Indent selection |
| `Ctrl+[` | Unindent selection |
| `Ctrl+F` | Find / replace |
| `Ctrl+H` | Find / replace (focus replace field) |
| `Ctrl+Shift+F` | Find in files |
| `Ctrl+N` | New tab |
| `Ctrl+Shift+N` | New project |
| `Ctrl+O` | Open file |
| `Ctrl+S` | Save |
| `Ctrl+Shift+S` | Save as |
| `Ctrl+,` | Settings |
| `F5` | Run script |

---

## Requirements

```
Python 3.10+
PyQt6
requests
markdown
pygments
```

Optional but recommended:
```
pyyaml                 # YAML/Ansible linting
chardet                # Encoding detection
python-lsp-server      # LSP for Python
sentence-transformers  # Local embeddings for vector index
chromadb               # Vector index storage
pyqtermwidget          # Full PTY terminal (Linux/macOS)
shellcheck             # Bash linting (via system package manager)
```

---

## Project structure
```
quillai/
├── main.py                    # Main window and application entry point
├── ai/
│   ├── worker.py              # AIWorker — all LLM backends and streaming
│   ├── context_engine.py      # Context assembly — symbols, imports, LSP, repo map, vector
│   ├── lsp_client.py          # Generic JSON-RPC LSP client
│   ├── lsp_manager.py         # Multi-server LSP registry and routing
│   ├── lsp_context.py         # Formats LSP hover/diagnostics for chat context
│   ├── repo_map.py            # AST-based structural project map (Python + Ansible)
│   ├── embedder.py            # Embedding router (local sentence-transformers / OpenAI)
│   ├── vector_store.py        # ChromaDB wrapper, per-project collections
│   └── vector_index.py        # Semantic index orchestration and query
├── editor/
│   ├── ghost_editor.py        # Editor with ghost text, minimap, inline chat, LSP
│   ├── multi_cursor.py        # Multi-cursor editing logic
│   └── highlighter.py         # Syntax highlighter registry
├── plugins/
│   ├── python_plugin.py
│   ├── html_plugin.py
│   ├── ansible_plugin.py
│   ├── nix_plugin.py
│   ├── bash_plugin.py
│   ├── markdown_plugin.py
│   └── git_plugin.py
└── ui/
    ├── menu.py                # File menu and recent projects
    ├── chat_renderer.py       # Chat rendering, streaming, syntax highlighting
    ├── command_palette.py     # Ctrl+P command palette
    ├── lsp_editor.py          # LspEditorMixin — hover, go-to-def, squiggles
    ├── terminal.py            # Embedded terminal dock
    ├── sliding_chat_panel.py  # Sliding panel with Chat and Memory tabs
    ├── memory_manager.py      # Per-project memory, facts, conversations, turns
    ├── memory_panel.py        # Memory panel UI
    ├── autosave_manager.py    # Crash recovery and periodic autosave
    ├── startup_progress.py    # Animated startup indicator
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
| Vector index | `~/.config/quillai/vector/` |
| Autosave | `~/.config/quillai/autosave/` |

When using a local backend, no data is transmitted anywhere. When using a cloud backend, only the content you explicitly send is transmitted to that provider — nothing else.

---

## Roadmap

### Planned
- [ ] Breadcrumb bar (file › class › method)
- [ ] Symbol outline panel
- [ ] Split editor panes
- [ ] LSP rename symbol
- [ ] LSP-powered completions (replace ghost text with semantically-aware suggestions)
- [ ] Git diff context in chat — auto-inject recent changes for debug queries
- [ ] Terminal stderr capture — pipe last error into chat context automatically
- [ ] Smooth scrolling
- [ ] Code folding
- [ ] Markdown preview scroll sync
- [ ] Completion feedback loop — use acceptance data to influence suggestion ranking

### Completed
- [x] Multi-cursor editing — Ctrl+D, Ctrl+Shift+L, Ctrl+Alt+Up/Down, Alt+Click
- [x] Crash recovery — autosave every 2 minutes, silent restore on next launch
- [x] Vector index — semantic search across code, conversations, completions, edit patterns
- [x] LSP support — hover docs, Ctrl+Click go-to-definition, diagnostics, 7 languages
- [x] Repo map — structural project index for codebase-aware chat (Python + Ansible)
- [x] Git blame in gutter
- [x] Bracket match highlight
- [x] Embedded terminal
- [x] Command palette (Ctrl+P)
- [x] Memory system with turn buffer and session continuity
- [x] Line number double-click to select line

---

## License

MIT