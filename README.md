# QuillAI

A fast, keyboard-driven code editor with AI-powered completions, chat, and project-aware context — built with PyQt6 and designed to run locally or against any OpenAI-compatible or Anthropic API.

---

## Features

### AI Backends
- **Local (llama.cpp)** — FIM (fill-in-middle) completions via llama.cpp server, zero latency, zero cost
- **OpenAI / compatible** — any OpenAI-style API including OpenRouter
- **Anthropic (Claude)** — native Claude API with Sonnet for chat and Haiku for inline completions

Switch backends at any time with the mode button in the status bar (`🏠 LOCAL` / `☁️ OPENAI` / `🟠 CLAUDE`).

### Inline Completions
- Ghost text appears at the cursor on natural pause points (entering a block body, after a comment, inside an indented scope)
- **`Tab`** — accept full suggestion
- **`Ctrl+Right`** — accept one word at a time
- **`Ctrl+Space`** — trigger manually at any cursor position

### AI Chat Panel
- Full project-aware context: active file, all open tabs, direct and transitive imports (up to 3 levels deep), and the project file tree
- Streaming responses with syntax highlighting
- **⚡ INSERT CODE AT CURSOR** button injects the last code block directly into the editor
- Send selected code to chat via right-click → `💬 Send to Chat`

### Editor
- Syntax highlighting for Python, HTML, Ansible, Nix, Bash, and Markdown
- Line numbers with git diff indicators (green = added, amber = modified)
- Minimap with click-to-navigate
- Indent guides
- Auto-closing brackets, quotes, and braces
- Smart auto-indent on Enter
- Paste re-indentation — pasted code aligns to the cursor's indentation level
- Fix Indentation — right-click → `⇥ Fix Indentation` to normalise a selection
- Ctrl+scroll to zoom
- `Ctrl+E` — AI rewrite of selected code

### Snippet Palette
- **`Ctrl+Shift+Space`** — open the snippet palette
- Fuzzy search across name and category
- Live code preview pane
- Snippets for Python, Ansible, Nix, and Bash
- User-editable at `~/.config/quillai/snippets.json`

### Markdown Preview
- Opens automatically when editing `.md` files
- Live preview with 300ms debounce — scrolls in sync with edits
- Supports headings, bold, italic, inline code, fenced code blocks, blockquotes, lists, horizontal rules, and links

### Source Control (Git)
- Changed files tree with status indicators (M / A / D / ?)
- Selective staging — check boxes next to files to commit
- Inline diff viewer with syntax-coloured additions and removals
- Discard changes via right-click context menu
- Push button with status feedback
- Works correctly regardless of launch directory — tracks the open project folder

### Find & Replace
- **`Ctrl+F`** — open find/replace panel
- Live search with green (match) / red (no match) input feedback
- Match count display
- Case-sensitive and whole-word toggles
- **`Ctrl+Shift+F`** — find in files across the whole project

### Run & Debug
- **`F5`** — run the current script
- Output panel with stdout / stderr
- **💡 Explain Error** — sends the traceback and active file to the AI chat for diagnosis

---

## Requirements

```
Python 3.10+
PyQt6
requests
markdown
```

Optional:
```
pyyaml      # YAML/Ansible linting
shellcheck  # Bash linting (system package)
```

---

## Installation

```bash
git clone https://github.com/yourname/quillai
cd quillai
pip install PyQt6 requests pyyaml
python main.py
```

---

## Configuration

Open **File → Settings** (`Ctrl+,`) to configure:

| Section | Setting | Description |
|---|---|---|
| Local LLM | Server URL | llama.cpp server endpoint |
| Local LLM | Model name | Model identifier sent to the server |
| OpenAI | API URL | Defaults to `api.openai.com`, supports any compatible endpoint |
| OpenAI | API Key | `sk-...` key |
| OpenAI | Chat model | e.g. `gpt-4o` |
| Anthropic | API Key | `sk-ant-...` from console.anthropic.com |
| Anthropic | Chat model | e.g. `claude-sonnet-4-6` |
| Anthropic | Inline model | e.g. `claude-haiku-4-5-20251001` |

Settings are stored at `~/.config/quillai/settings.json`.

---

## Keybindings

| Key | Action |
|---|---|
| `Ctrl+Space` | Trigger inline AI completion |
| `Ctrl+Shift+Space` | Open snippet palette |
| `Tab` | Accept ghost text suggestion |
| `Ctrl+Right` | Accept next word of suggestion |
| `Ctrl+E` | AI rewrite of selection |
| `Ctrl+F` | Find / replace |
| `Ctrl+H` | Find / replace (focus replace) |
| `Ctrl+Shift+F` | Find in files |
| `Ctrl+N` | New tab |
| `Ctrl+O` | Open file |
| `Ctrl+S` | Save |
| `Ctrl+Shift+S` | Save as |
| `Ctrl+,` | Settings |
| `F5` | Run script |
| `Ctrl+Return` | Send chat message |

---

## Project Structure

```
quillai/
├── main.py                  # Main window and application entry point
├── ai/
│   └── worker.py            # AIWorker — handles all LLM backends and streaming
├── editor/
│   ├── ghost_editor.py      # Main editor widget with ghost text and minimap
│   └── highlighter.py       # Syntax highlighter registry
├── plugins/
│   ├── python_plugin.py
│   ├── html_plugin.py
│   ├── ansible_plugin.py
│   ├── nix_plugin.py
│   ├── bash_plugin.py
│   ├── markdown_plugin.py
│   └── git_plugin.py        # Git dock — status, diff, commit, push
└── ui/
    ├── menu.py
    ├── find_replace.py
    ├── find_in_files.py
    ├── markdown_preview.py  # Live markdown preview dock
    ├── snippet_palette.py   # Ctrl+Shift+Space snippet browser
    ├── settings_manager.py
    ├── settings_dialog.py
    └── diff_viewer.py
```

---

## License

MIT
