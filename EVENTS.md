# QuillAI Plugin Event Reference

Events are emitted and subscribed to via the plugin manager's event bus.

## Usage

**Subscribing** (inside `activate()`):
```python
from core.events import EVT_FILE_OPENED

self.on(EVT_FILE_OPENED, self._on_file_opened)
```

**Emitting** (from anywhere with access to `plugin_manager`):
```python
from core.events import EVT_FILE_OPENED

self.app.plugin_manager.emit(EVT_FILE_OPENED, path="/foo/bar.py", editor=editor)
```

---

## Event Catalogue

### `file_opened`
Emitted when a file is opened or becomes the active editor tab.

| kwarg    | type          | description                        |
|----------|---------------|------------------------------------|
| `path`   | `str`         | Absolute path to the file          |
| `editor` | `GhostEditor` | The editor instance, may be `None` |

Emitted from: `_on_tab_changed`, `_refresh_markdown_preview`, `open_file_in_tab`

---

### `file_saved`
Emitted after a file is successfully written to disk.

| kwarg  | type  | description                    |
|--------|-------|--------------------------------|
| `path` | `str` | Absolute path to the saved file |

Emitted from: `save_file`

---

### `project_opened`
Emitted when a project folder is opened or switched to.

| kwarg          | type  | description                            |
|----------------|-------|----------------------------------------|
| `project_root` | `str` | Absolute path to the project root directory |

Emitted from: `_restore_session`, `_open_recent_project` (menu.py), `_new_project` (menu.py)

---

### `markdown_changed`
Emitted when the content of a markdown file changes (debounced via `textChanged`).

| kwarg  | type  | description                          |
|--------|-------|--------------------------------------|
| `text` | `str` | Current full text content of the editor |

Emitted from: `add_new_tab` (via `textChanged` connection)

---

### `editor_scrolled`
Emitted when the active editor is scrolled. Used for markdown preview scroll sync.

| kwarg           | type  | description                              |
|-----------------|-------|------------------------------------------|
| `first_visible` | `int` | Block number of the first visible line   |
| `total_lines`   | `int` | Total block count in the document        |

Emitted from: `_sync_markdown_scroll`

---

## Adding a New Event

1. Add a constant to `core/events.py` with a docstring describing kwargs
2. Emit it from the appropriate place in `main.py` or another plugin
3. Add an entry to this file

Keep event names lowercase with underscores. Prefix with the domain
(`file_`, `project_`, `editor_`, `lsp_`) to keep them organised as the
list grows.