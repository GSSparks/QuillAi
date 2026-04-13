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

# ── Terminal output events ─────────────────────────────────────────────────────

EVT_TERMINAL_OUTPUT = "terminal_output"
"""
Emitted for each chunk of output from the terminal.

kwargs:
    text (str) — raw text chunk from the PTY
"""

EVT_RUN_FAILURE = "run_failure"
"""
kwargs:
    run_event  (RunEvent) — the parsed failure event
    code       (str)      — contents of the relevant file, if found
    file_path  (str)      — absolute path to the relevant file, if found
"""

EVT_RUN_COMPLETE = "run_complete"
"""
Emitted when a run finishes (PLAY RECAP detected).

kwargs:
    tool    (str)  — "ansible" | "terraform"
    success (bool) — True if no failures
    summary (str)  — recap text
"""

# ── AI Context events ─────────────────────────────────────────────────────

EVT_CONTEXT_BUILT = "context_built"
"""
Emitted when AI context is fully assembled before a request.

| kwarg    | type   | description                          |
|----------|--------|--------------------------------------|
| context  | dict   | Structured context object            |
| prompt   | str    | Final prompt sent to the model       |
| metadata | dict   | Optional debug info (tokens, timing) |
"""

EVT_TOOL_CALLED = "tool_called"
"""
Emitted when a tool is called by the AI.

| kwarg    | type   | description                          |
|----------|--------|--------------------------------------|
| tool     | str    | Name of the tool called              |
| args     | dict   | Arguments passed to the tool         |
"""

EVT_TOOL_RESULT = "tool_result"
"""
Emitted when a tool call returns a result.

| kwarg    | type   | description                          |
|----------|--------|--------------------------------------|
| tool     | str    | Name of the tool                     |
| success  | bool   | Whether the tool call succeeded      |
| result   | str    | Output or error message from the tool|
"""
