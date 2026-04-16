<p align="center">
  <img src="./images/quillai_logo.svg" width="400" alt="QuillAI logo"/>
</p>
 
<p align="center">
  <img src="https://img.shields.io/badge/python-3.10+-blue?style=flat-square&logo=python&logoColor=white"/>
  <img src="https://img.shields.io/badge/platform-Linux-lightgrey?style=flat-square&logo=linux&logoColor=white"/>
  <img src="https://img.shields.io/badge/license-MIT-green?style=flat-square"/>
  <img src="https://img.shields.io/badge/AI-local%20%7C%20cloud-purple?style=flat-square"/>
</p>
 
# QuillAI
 
<p align="center">
  <img src="./images/Screenshot.png" width="900" alt="QuillAI editor showing find/replace, minimap, git panel, and find in files"/>
</p>
 
**QuillAI is an AI-powered code editor that actually understands your codebase** — not just the file you have open, but your entire project's structure, history, and conventions. Ask it about any function, class, or pattern across your whole project and get accurate answers backed by real source code, not hallucination.
 
Built with PyQt6. Runs fully local with llama.cpp or connects to Claude, GPT-4, Gemini, or any OpenAI-compatible API. Your choice, switchable in one click.
 
---
 
## Why QuillAI?
 
Most AI coding tools — Copilot, Cursor, Tabnine — send your code to external servers on every keystroke. QuillAI doesn't have to. When configured with a local LLM:
 
- **Your code never leaves your machine**
- **No API keys required**
- **No usage limits, no subscription**
- **Works offline**
 
When you do want cloud power (Claude, GPT-4, Gemini, OpenRouter), you switch with one click in the status bar. The choice is always yours.
 
**What makes the AI actually useful:** QuillAI builds a structured wiki of your entire codebase — every file summarized, every symbol indexed — and injects relevant pages into every prompt. Combined with a repo map, memory system, and LSP integration, the AI has genuine context about your project rather than just the file you happen to have open. It can answer "how does the auth flow work?" or "what calls this function?" accurately, because it's read the whole codebase.
 
---

## Screenshots

### Editor with Split Panes
<p align="center">
  <img src="./images/screenshot_split_panes.png" width="900" alt="QuillAI split editor panes"/>
</p>

### Symbol Outline Panel
<p align="center">
  <img src="./images/screenshot_outline.png" width="900" alt="QuillAI symbol outline panel showing class and method tree"/>
</p>

### Import Graph
<p align="center">
  <img src="./images/screenshot_import_graph.png" width="900" alt="QuillAI import dependency graph visualization"/>
</p>

### Visual CI/CD pipeline editor
 
QuillAI includes a full visual editor for GitLab CI and GitHub Actions pipelines — renders your pipeline as an interactive graph and lets you edit it without touching YAML directly.
 
<p align="center">
  <img src="./images/screenshot_pipeline_viewer.png" width="900" alt="QuillAI pipeline viewer showing job cards, stage columns, and dependency arrows"/>
</p>
 
**Graph tab:**
- Jobs rendered as cards grouped into stage columns
- Dependency arrows drawn between jobs connected by `needs:`
- Drag a card to a different column to change its `stage:` — writes back to YAML immediately
- **Hover a card** to reveal connection ports; **drag from output port to input port** to add a `needs:` dependency
- **Right-click an arrow** to remove a dependency
- **Double-click a card** to open the inline job editor — edit name, stage, image, when, environment, allow_failure, needs, and script
- Child pipelines from `trigger:` jobs rendered as separate swimlanes
- Template jobs (`.dot-prefixed`) shown in a muted Templates swimlane with `extends:` inheritance resolved
 
**Info tab:**
- **📦 Includes** — remote project references, local includes, template includes with full path breakdown
- **🔀 Workflow rules** — every `if:` condition shown with ✓/✗ indicating when the pipeline fires, `never` rules highlighted
- **📋 Variables** — all pipeline-level variables, secrets automatically masked, CI runtime variables shown in muted style
 
All edits are surgical — only the specific lines that changed are touched. Comments, anchors, and formatting are preserved.
 
---
 
### AI self-modification
 
QuillAI can propose and apply code changes to files directly from the chat panel.
 
<p align="center">
  <img src="./images/screenshot_apply.png" width="900" alt="QuillAI chat showing Apply button and diff review dialog"/>
</p>
 
When the AI responds with code that belongs in a specific file, an apply bar appears below the response:
 
```
🔧 Replace function search_project()
📄 ai/context_engine.py   ⚡ Apply to context_engine.py   ↩ Undo
```
 
- **Single function/class** — applied instantly using AST-precise replacement. Only the target symbol is replaced; surrounding code is untouched.
- **Full file rewrite** — opens a side-by-side diff review dialog before writing anything. Accept or discard.
- **Multi-file changes** — when the AI proposes changes across multiple files at once, a unified review dialog shows a side-by-side diff for each file. Check or uncheck individual files, then apply selected or all at once.
- **Perl subroutines** — brace-counting replacement for `sub name { ... }` blocks.
- **↩ Undo** — restores the previous version instantly. One level deep.
 
Detection is automatic — no special syntax required from the AI. For explicit control, the AI can wrap suggestions in `<file_change path="..." mode="function|full">` tags.

After applying, the editor reloads the file automatically. The repo map is invalidated so the next chat prompt reflects the change.

---

### Agentic mode

QuillAI includes a full agentic loop — the AI can investigate your codebase, read files, search for patterns, and apply changes autonomously.

When the AI needs to look at files or make changes, it automatically switches into agent mode and uses a set of tools:

- **`read_file`** — reads any file in the project, with line numbers
- **`grep`** — searches for patterns across the project
- **`find_files`** — finds files matching a glob
- **`find_symbol`** — looks up a symbol in the repo map
- **`run_shell`** — runs read-only shell commands (including `wc -l` before reading files)
- **`write_file`** — writes a complete new file (used for files under 150 lines)
- **`patch_file`** — replaces a line range in a file by number (used for larger files)

The agent always checks line count before reading, reads the entire file before proposing changes, and uses `write_file` for small files rather than fragile string matching. All write operations are shown in a diff review dialog — the dialog is the confirmation, no verbal "yes" needed. Agent memory persists between turns within a session, so follow-up requests like "now do the same for storage.py" don't require re-investigation.

---

### Ansible Playbook Debugger

A live execution debugger for `ansible-playbook` runs, showing a host×task matrix that updates in real time as your playbook executes.

<p align="center">
  <img src="./images/screenshot_playbook_debugger.png" width="900" alt="QuillAI Playbook Debugger showing host×task matrix with per-host status cells"/>
</p>

**Matrix view:**
- Rows are tasks, columns are hosts
- Cells colored by status: ✓ ok (green), ~ changed (yellow), ✗ failed (red), ! unreachable (red), – skipped (grey)
- Updates live as ansible output streams through the terminal
- Click any cell to see full detail in the pane below

**Detail pane:**
- Full `msg`, `stdout`, `stderr`, and `rc` captured from verbose (`-v`) output
- Other hosts' outcomes shown inline for immediate comparison
- **Compare hosts** button appears when a task fails on some hosts but succeeds on others — builds a prompt comparing host variables using the inventory explorer
- **💡 Ask AI** button sends the full error context, per-host detail, and relevant task YAML to chat

**Works automatically** — just run `ansible-playbook` in the QuillAI terminal. The debugger detects the output and populates the matrix without any configuration. Re-run with `-v` for full stdout/stderr capture.

---

### Context Debugger

The Context Debugger visualizes the AI's internal context and prompt construction:

- **Context Tree** — structured view of model info, editor state, and wiki context
- **Prompt** — the exact prompt text sent to the AI model
- **Raw Context** — full JSON representation of the context
- **Tools** — live log of agent tool calls and their results

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
- **🏠 Local (llama.cpp / Ollama)** — FIM completions via a local llama.cpp server or any OpenAI-compatible local endpoint. Zero latency, zero cost, zero data sharing. Recommended: Qwen2.5-Coder.
- **☁️ OpenAI / compatible** — any OpenAI-style API including OpenRouter, LM Studio, Ollama, and others
- **🟠 Anthropic (Claude)** — native Claude API with separate models for chat and inline completions
- **💎 Google Gemini** — native Gemini API; model configurable in settings (defaults to `gemini-2.0-flash`)

Switch backends at any time with the mode button in the status bar. Cycles through Local → OpenAI → Claude → Gemini.

### Plugin system
QuillAI features a lightweight auto-discovery plugin system. Drop a new plugin folder into `plugins/features/` and it is loaded automatically on next launch — no changes to core code required.

Plugins communicate via a named event bus (`file_opened`, `file_saved`, `project_opened`, and more — see `EVENTS.md`). Individual plugins can be enabled or disabled at runtime from **File → Settings → Plugins** without restarting. The following panels are implemented as plugins:

- **Terminal** — custom VT100 terminal emulator (Ctrl+\`)
- **Import Graph** — dependency graph visualization
- **Symbol Outline** — LSP-powered class/method tree
- **Markdown Preview** — live preview with scroll sync
- **Code Folding** — fold/unfold functions and classes in the gutter
- **Context Debugger** — visualize AI context and tool calls in real time
- **Playbook Debugger** — live Ansible execution matrix with host-level detail and AI fixes
- **SSH Host Manager** — manage SSH hosts with ProxyJump and Jinja2 variable resolution
- **Inventory Explorer** — Ansible inventory browser with group_vars/host_vars precedence
- **Pipeline Viewer** — visual CI/CD pipeline editor for GitLab CI and GitHub Actions

### Intent-aware inline completions
Ghost text at natural pause points. **`Tab`** to accept, **`Ctrl+Right`** for word-by-word, **`Ctrl+Space`** to trigger manually. For non-LSP files, **`Ctrl+Space`** opens an AI-powered completion popup with ranked suggestions.

### Project-aware AI chat
The chat panel understands your entire project: active file and symbol, all open tabs, imports up to 3 levels deep, LSP hover docs and diagnostics, structural repo map, wiki knowledge base, recent git diff context, and memory facts. Responses stream live with syntax highlighting and markdown rendering.

### Wiki knowledge base
QuillAI builds and maintains a structured Markdown wiki of your entire codebase at `~/.config/quillai/wiki/<project>/`. Each source file gets its own wiki page — summary, key symbols, dependencies, and architectural notes — kept automatically up to date.

The wiki is injected into every AI prompt as structured context, giving the model a permanent, always-current understanding of your codebase.

**Wiki menu** (`Wiki` in the menu bar):
- **Update Stale Pages** (`Ctrl+Shift+U`) — immediate rescan for anything that has changed
- **Rebuild All Pages…** — regenerate every page from scratch
- **Export FAQ → Markdown** — export the project FAQ as a Markdown document

### FAQ knowledge layer
A curated, living knowledge base of how-to answers, architectural decisions, and codebase gotchas — extracted automatically from chat conversations and wiki pages. Entries are classified by type (`howto`, `concept`, `decision`, `gotcha`), re-evaluated when source files change, and pruned when stale. Injected into every AI prompt alongside the wiki.

### LSP integration

- **Hover tooltips** — signature and docstring for any symbol
- **Ctrl+Click go-to-definition** — jump to definition, across files
- **Diagnostic squiggles** — live error and warning underlines as you type
- **Breadcrumb bar** — always-visible `file › class › method` navigation
- **Symbol outline panel** — full tree with click-to-jump
- **LSP completion dropdown** — type signatures and docstrings
- **Rename symbol (F2)** — project-wide rename with preview

Supported servers:

| Language | Server |
|---|---|
| Python | `python-lsp-server` |
| YAML / Ansible | `yaml-language-server` |
| JavaScript / TypeScript | `typescript-language-server` |
| Bash / Shell | `bash-language-server` |
| HTML / CSS / JSON / Markdown | `vscode-langservers-extracted` |
| Nix | `nil` |
| Lua | `lua-language-server` |
| Perl | `perlnavigator` |
| Terraform | `terraform-lsp` |

### Split editor panes
Split the editor horizontally or vertically. Tabs can be dragged between panes. Panes collapse automatically when their last tab is closed.

- **`Ctrl+\`** — split side by side
- **`Ctrl+Shift+\`** — split top/bottom
- **`Ctrl+Shift+W`** — close active pane
- **`Ctrl+K Left/Right`** — move focus between panes

### Terminal stderr capture
When a command in the terminal produces an error, a **💡 Terminal Error** button appears in the status bar. Clicking it sends the last 50 lines of output (ANSI-stripped) to chat. Triggers on: `Traceback`, `Error:`, `Exception:`, `FAILED`, `fatal:`, `command not found`, `No such file or directory`, `Permission denied`.

### Git diff context in chat
Recent staged and unstaged diffs are automatically injected into chat context when your query is about recent changes, bugs, or code review. Triggers on phrases like "what did I change", "why is it broken", "stopped working after", etc.

### DevOps features

- **Ansible Playbook Debugger** — live host×task matrix, verbose output capture, host var comparison, AI fixes. See above.
- **Ansible Inventory Explorer** — browse inventory with full group_vars/host_vars precedence resolution
- **Terraform Run Analyzer** — parses plan/apply output, surfaces errors with file hints, AI fixes
- **SSH Host Manager** — manage SSH hosts with ProxyJump resolution and Jinja2 variable expansion
- **Visual CI/CD Pipeline Editor** — interactive graph editor for GitLab CI and GitHub Actions

### Memory system
- **Global facts** — preferences that apply to all your work
- **Project facts** — things specific to the current codebase
- **Conversation history** — past exchanges, searchable, clickable to restore
- **Turn buffer** — recent messages always included verbatim for genuine conversational continuity

### Multi-cursor editing
- **`Ctrl+D`** — add cursor at next occurrence
- **`Ctrl+Shift+L`** — add cursors at all occurrences
- **`Ctrl+Alt+Up/Down`** — column mode
- **`Alt+Click`** — add cursor at any position
- **`Escape`** — clear secondary cursors

### Editor
- Syntax highlighting for Python, HTML, Ansible/YAML, Nix, Bash, Markdown, Perl, Terraform, and more
- Line numbers with live git diff indicators
- Minimap with click-to-navigate
- Smooth scrolling, bracket match highlighting, indent guides, auto-closing brackets
- Git blame in the gutter
- Code folding from the gutter
- Color swatch inline for hex values — click to open color picker
- Crash recovery — autosave every 2 minutes, silent restore on next launch

---

## Local LLM setup

**llama.cpp:**
```bash
./server -m your-model.gguf --port 11434 -c 8192
```

**Ollama:**
```bash
ollama serve
```

In QuillAI settings (`Ctrl+,`), set the Server URL to `http://localhost:11434/v1/chat/completions` and the model name to whichever model you have pulled.

**Recommended models:**
- Chat: `Qwen2.5-Coder-32B-Q4_K_M` (32GB VRAM) or `Qwen2.5-Coder-7B-Q4_K_M` (8GB VRAM)
- Inline completions: any FIM-capable model, 7B or smaller for low latency
- Agentic tasks: `gpt-4.1`, `claude-sonnet-4-6`, or a 32B+ local model for reliable tool use

---

## Configuration

Open **File → Settings** (`Ctrl+,`):

| Section | Setting | Description |
|---|---|---|
| Local LLM | Server URL | llama.cpp, Ollama, or compatible endpoint |
| Local LLM | Model name | Model identifier |
| Local LLM | Context budget | Max tokens per request |
| OpenAI | API URL | Defaults to `api.openai.com` |
| OpenAI | API Key | `sk-...` |
| OpenAI | Chat model | e.g. `gpt-4.1` |
| Anthropic | API Key | `sk-ant-...` |
| Anthropic | Chat model | e.g. `claude-sonnet-4-6` |
| Anthropic | Inline model | e.g. `claude-haiku-4-5-20251001` |
| Gemini | API Key | `AIza...` (from aistudio.google.com) |
| Gemini | Chat model | e.g. `gemini-2.0-flash` |

---

## Keybindings

| Key | Action |
|---|---|
| `Ctrl+P` | Command palette |
| `Ctrl+Space` | Trigger inline completion / completion popup |
| `Tab` | Accept full ghost text suggestion |
| `Ctrl+Right` | Accept next word of suggestion |
| `Ctrl+Shift+Space` | Open snippet palette |
| `Ctrl+E` | AI rewrite of selection (with diff preview) |
| `Ctrl+I` | Inline chat at cursor |
| `Ctrl+Click` | Go to definition (LSP) |
| `F2` | Rename symbol (LSP) |
| `Ctrl+Return` | Send chat message |
| `Ctrl+\`` | Toggle terminal |
| `Ctrl+\` | Split editor pane (side by side) |
| `Ctrl+Shift+\` | Split editor pane (top/bottom) |
| `Ctrl+Shift+W` | Close active pane |
| `Ctrl+K Left/Right` | Focus adjacent pane |
| `Ctrl+D` | Multi-cursor: add next occurrence |
| `Ctrl+Shift+L` | Multi-cursor: add all occurrences |
| `Ctrl+Alt+Up/Down` | Multi-cursor: add cursor above/below |
| `Alt+Click` | Multi-cursor: add cursor at position |
| `Escape` | Clear secondary cursors |
| `Ctrl+G` | Go to line |
| `Ctrl+Shift+D` | Duplicate line or selection |
| `Ctrl+/` | Toggle comment |
| `Ctrl+]` / `Ctrl+[` | Indent / unindent selection |
| `Ctrl+F` | Find / replace |
| `Ctrl+H` | Find / replace (focus replace field) |
| `Ctrl+Shift+F` | Find in files |
| `Ctrl+Shift+U` | Update stale wiki pages |
| `Ctrl+N` | New tab |
| `Ctrl+O` | Open file |
| `Ctrl+S` | Save |
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
shellcheck             # Bash linting
perlnavigator          # LSP for Perl
terraform-lsp          # LSP for Terraform
```

---

## Project structure

```
quillai/
├── main.py                        # Main window and application entry point
├── EVENTS.md                      # Plugin event bus reference
├── ai/
│   ├── worker.py                  # AIWorker — all LLM backends and streaming
│   ├── agent_worker.py            # AgentWorker — agentic tool-use loop with memory
│   ├── context_engine.py          # Context assembly — symbols, imports, LSP, repo map, wiki
│   ├── lsp_client.py              # Generic JSON-RPC LSP client
│   ├── lsp_manager.py             # Multi-server LSP registry and routing
│   ├── lsp_context.py             # Formats LSP hover/diagnostics for chat context
│   ├── repo_map.py                # AST-based structural project map
│   ├── tools.py                   # Agent tool definitions and execution
│   └── embedder.py                # Embedding router
├── core/
│   ├── plugin_base.py             # FeaturePlugin ABC
│   ├── plugin_manager.py          # Auto-discovery, loading, event bus, dock registry
│   ├── events.py                  # Named constants for all plugin bus events
│   ├── faq_manager.py             # Per-project FAQ — extraction, staleness, export
│   ├── patch_applier.py           # AST-precise function replacement and undo
│   ├── wiki_manager.py            # Wiki filing system
│   ├── wiki_generator.py          # LLM prompt → Markdown wiki page
│   ├── wiki_indexer.py            # Background daemon — crawls repo, processes stale files
│   ├── wiki_watcher.py            # Git commit watcher
│   └── wiki_context_builder.py    # Assembles wiki context for AI prompts
├── editor/
│   ├── ghost_editor.py            # Editor with ghost text, minimap, inline chat, LSP
│   ├── multi_cursor.py            # Multi-cursor editing logic
│   └── highlighter.py             # Syntax highlighter registry
├── plugins/
│   ├── languages/                 # Per-language syntax highlighting plugins
│   ├── features/                  # Auto-discovered feature plugins
│   │   ├── terminal/              # Custom VT100 terminal emulator
│   │   ├── import_graph/          # Import dependency graph
│   │   ├── symbol_outline/        # LSP symbol outline panel
│   │   ├── markdown_preview/      # Live markdown preview
│   │   ├── code_folding/          # Gutter code folding
│   │   ├── context_debugger/      # AI context visualizer
│   │   ├── pipeline_viewer/       # Visual CI/CD pipeline editor
│   │   ├── run_analyzer/          # Ansible Playbook Debugger
│   │   ├── inventory_explorer/    # Ansible inventory browser
│   │   └── ssh_host_manager/      # SSH host manager
│   └── themes/                    # Theme definitions (Gruvbox, VSCode, Monokai, etc.)
└── ui/
    ├── menu.py                    # Application menus
    ├── chat_renderer.py           # Chat rendering and streaming
    ├── multi_file_diff_dialog.py  # Multi-file diff review
    ├── diff_apply_dialog.py       # Single-file diff preview
    ├── command_palette.py         # Ctrl+P command palette
    ├── lsp_editor.py              # LSP mixin — hover, go-to-def, squiggles
    ├── breadcrumb_bar.py          # File › class › method navigation
    ├── completion_popup.py        # LSP completion dropdown
    ├── split_container.py         # Split pane container
    ├── sliding_chat_panel.py      # Sliding Chat + Memory panel
    ├── memory_manager.py          # Memory, facts, conversations
    ├── git_panel.py               # Source control panel
    ├── settings_manager.py        # Settings persistence
    ├── settings_dialog.py         # Settings UI
    └── theme.py                   # Theme engine
```

### Writing a plugin

Create a folder under `plugins/features/` with a `main.py` containing a `FeaturePlugin` subclass:

```python
from core.plugin_base import FeaturePlugin
from core.events import EVT_FILE_OPENED
from PyQt6.QtCore import Qt

class MyPlugin(FeaturePlugin):
    name = "my_plugin"
    enabled = True

    def activate(self):
        from plugins.features.my_plugin.my_widget import MyDockWidget
        self.dock = MyDockWidget(self.app)
        self.app.my_dock = self.dock
        self.app.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock)
        self.app.plugin_manager.register_dock("My Panel", "my_dock")
        self.on(EVT_FILE_OPENED, self._on_file_opened)

    def _on_file_opened(self, path=None, editor=None, **kwargs):
        pass

    def deactivate(self):
        self.dock.close()
        self.app.my_dock = None
```

Restart QuillAI — the plugin is discovered and loaded automatically. See `EVENTS.md` for the full event reference.

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
| Wiki knowledge base | `~/.config/quillai/wiki/` |
| FAQ knowledge base | `~/.config/quillai/faq/` |
| Autosave | `~/.config/quillai/autosave/` |

When using a local backend, no data is transmitted anywhere. When using a cloud backend, only the content you explicitly send is transmitted to that provider — nothing else.

---

## Roadmap

### Planned
- [ ] Infrastructure Drift Detector — connect to hosts via SSH, collect facts, compare against playbook expectations, surface diffs
- [ ] Test generation — "Generate tests for this file" shortcut via the agentic loop
- [ ] Completion feedback loop — use acceptance data to influence suggestion ranking

### Completed
- [x] Ansible Playbook Debugger — live host×task matrix, per-host verbose detail (msg/stdout/stderr/rc), host variable comparison, AI-assisted fixes
- [x] Google Gemini backend — native Gemini API with streaming; model configurable in settings
- [x] Terminal stderr capture — errors in terminal output surface a 💡 button to explain in chat
- [x] Drag-and-drop tabs between split panes
- [x] Agentic loop improvements — disciplined file editing (wc -l → read → write/patch), agent memory between turns, diff dialog as confirmation
- [x] Wiki FAQ system — per-project FAQ auto-extracted from conversations and wiki pages; exported as Markdown
- [x] Plugin settings UI — enable/disable plugins at runtime without restarting
- [x] Code folding — fold/unfold from the gutter
- [x] AI completion popup — `Ctrl+Space` for non-LSP files
- [x] Git diff context in chat — recent diffs injected automatically for debugging queries
- [x] Multi-file diff review — unified side-by-side dialog for agent changes across multiple files
- [x] Wiki knowledge base — per-project Markdown wiki, auto-generated and kept current
- [x] Plugin system — auto-discovery, event bus, dock registry
- [x] Split editor panes — horizontal and vertical, auto-collapse
- [x] Symbol outline panel — LSP-powered with click-to-jump
- [x] Import dependency graph — interactive force-directed visualization
- [x] LSP completion dropdown — type signatures and docstrings
- [x] Breadcrumb bar — file › class › method with symbol picker
- [x] Markdown preview scroll sync
- [x] LSP rename symbol (F2) — project-wide rename with preview
- [x] Multi-cursor editing — Ctrl+D, Ctrl+Shift+L, Ctrl+Alt+Up/Down, Alt+Click
- [x] Crash recovery — autosave every 2 minutes, silent restore
- [x] LSP support — hover, go-to-definition, diagnostics, 9 languages
- [x] Repo map — structural project index for codebase-aware chat
- [x] Git blame in gutter
- [x] Embedded terminal — custom VT100 emulator built from scratch
- [x] Command palette (Ctrl+P)
- [x] Memory system with turn buffer and session continuity
- [x] Visual CI/CD pipeline editor — GitLab CI and GitHub Actions
- [x] AI self-modification — AST-precise apply, full file diff review, undo

---

## License

MIT