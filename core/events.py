"""
core/events.py

Named constants for all QuillAI plugin event bus events.

Usage in a plugin:
    from core.events import EVT_FILE_OPENED, EVT_PROJECT_OPENED
    self.on(EVT_FILE_OPENED, self._on_file_opened)
    self.emit(EVT_PROJECT_OPENED, project_root="/path/to/project")
"""

# ── File events ───────────────────────────────────────────────────────────────

EVT_FILE_OPENED = "file_opened"
"""
Emitted when a file is opened or becomes the active editor.

kwargs:
    path   (str)         — absolute path to the file
    editor (GhostEditor) — the editor instance, may be None
"""

EVT_FILE_SAVED = "file_saved"
"""
Emitted after a file is successfully written to disk.

kwargs:
    path (str) — absolute path to the saved file
"""

# ── Project events ────────────────────────────────────────────────────────────

EVT_PROJECT_OPENED = "project_opened"
"""
Emitted when a project folder is opened or switched to.

kwargs:
    project_root (str) — absolute path to the project root directory
"""

# ── Editor content events ─────────────────────────────────────────────────────

EVT_MARKDOWN_CHANGED = "markdown_changed"
"""
Emitted when the content of a markdown file changes (debounced).

kwargs:
    text (str) — current full text content of the editor
"""

EVT_EDITOR_SCROLLED = "editor_scrolled"
"""
Emitted when the active editor is scrolled (used for preview sync).

kwargs:
    first_visible (int) — block number of the first visible line
    total_lines   (int) — total block count in the document
"""