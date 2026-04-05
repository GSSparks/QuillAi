"""
ui/lsp_editor.py

LspEditorMixin — add to GhostEditor for:
  - Ctrl+Click  → go-to-definition
  - Hover       → tooltip with signature/docstring
  - Squiggles   → diagnostic underlines coexisting with lint/bracket selections

Now accepts an LSPManager instead of a raw LSPClient, so all language
servers work transparently — the mixin doesn't need to know which server
is handling the current file.
"""

import re as _re
from PyQt6.QtCore    import Qt, QTimer, QPoint
from PyQt6.QtGui     import QTextCharFormat, QColor, QFont, QPalette, QTextCursor, QMouseEvent
from PyQt6.QtWidgets import QTextEdit, QToolTip, QFrame, QVBoxLayout, QLabel, QScrollArea

from ai.lsp_client import uri_to_path
from ui.completion_popup import CompletionPopup


_SEVERITY_COLOR = {
    1: "#fb4934",   # Error   — Gruvbox red
    2: "#fabd2f",   # Warning — Gruvbox yellow
    3: "#83a598",   # Info    — Gruvbox blue
    4: "#a89984",   # Hint    — Gruvbox grey
}

class _HoverPopup(QFrame):
    """Styled hover tooltip that renders markdown code blocks."""

    _instance = None   # singleton — only one at a time

    @classmethod
    def show_at(cls, parent, text: str, global_pos):
        # Dismiss any existing popup
        if cls._instance is not None:
            try:
                cls._instance.close()
                cls._instance.deleteLater()
            except RuntimeError:
                pass
            cls._instance = None

        popup = cls(parent, text)
        cls._instance = popup

        # Position: below cursor, nudge left if near right edge
        from PyQt6.QtWidgets import QApplication
        screen = QApplication.screenAt(global_pos)
        popup.adjustSize()
        x = global_pos.x()
        y = global_pos.y() + 20

        if screen:
            sg = screen.availableGeometry()
            if x + popup.width() > sg.right():
                x = sg.right() - popup.width() - 8
            if y + popup.height() > sg.bottom():
                y = global_pos.y() - popup.height() - 8

        popup.move(x, y)
        popup.show()
        popup.raise_()

        # Auto-dismiss after 8s
        QTimer.singleShot(8000, popup._dismiss)

    @classmethod
    def dismiss(cls):
        if cls._instance is not None:
            try:
                cls._instance._dismiss()
            except RuntimeError:
                pass
            cls._instance = None

    def __init__(self, parent, text: str):
        super().__init__(parent.window(), Qt.WindowType.ToolTip)
        self.setObjectName("HoverPopup")

        from ui.theme import get_theme, FONT_UI, FONT_CODE
        t = get_theme()

        bg      = t.get("bg1",      "#3c3836")
        bg_code = t.get("bg0_hard", "#1d2021")
        fg      = t.get("fg1",      "#ebdbb2")
        fg_dim  = t.get("fg4",      "#a89984")
        border  = t.get("border",   "#504945")
        accent  = t.get("blue",     "#83a598")
        orange  = t.get("orange",   "#fe8019")

        self.setStyleSheet(f"""
            QFrame#HoverPopup {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 4px;
            }}
        """)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(f"background: {bg}; border: none;")
        outer.addWidget(scroll)

        content = QFrame()
        content.setStyleSheet(f"background: {bg};")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)
        scroll.setWidget(content)

        # Parse and render markdown blocks
        blocks = _parse_hover_markdown(text)
        for block_type, block_text in blocks:
            if block_type == "code":
                # Detect language label if present
                lines = block_text.split("\n")
                lbl = QLabel(block_text)
                lbl.setWordWrap(False)
                lbl.setTextInteractionFlags(
                    Qt.TextInteractionFlag.TextSelectableByMouse
                )
                lbl.setStyleSheet(f"""
                    QLabel {{
                        background-color: {bg_code};
                        color: {orange};
                        font-family: '{FONT_CODE}', monospace;
                        font-size: 9pt;
                        padding: 6px 10px;
                        border-radius: 3px;
                        border: 1px solid {border};
                    }}
                """)
                layout.addWidget(lbl)

            elif block_type == "heading":
                lbl = QLabel(block_text)
                lbl.setWordWrap(True)
                lbl.setTextInteractionFlags(
                    Qt.TextInteractionFlag.TextSelectableByMouse
                )
                lbl.setStyleSheet(f"""
                    QLabel {{
                        color: {accent};
                        font-family: '{FONT_UI}', system-ui, sans-serif;
                        font-size: 9.5pt;
                        font-weight: 600;
                        padding: 0;
                    }}
                """)
                layout.addWidget(lbl)

            else:  # prose
                if not block_text.strip():
                    continue
                lbl = QLabel(block_text)
                lbl.setWordWrap(True)
                lbl.setTextInteractionFlags(
                    Qt.TextInteractionFlag.TextSelectableByMouse
                )
                lbl.setStyleSheet(f"""
                    QLabel {{
                        color: {fg};
                        font-family: '{FONT_UI}', system-ui, sans-serif;
                        font-size: 9pt;
                        padding: 0;
                    }}
                """)
                layout.addWidget(lbl)

        # Max size
        self.setMaximumWidth(520)
        self.setMaximumHeight(320)

    def _dismiss(self):
        self.close()
        self.deleteLater()
        if _HoverPopup._instance is self:
            _HoverPopup._instance = None

    def leaveEvent(self, event):
        super().leaveEvent(event)
        if hasattr(self, "_hover_timer"):
            self._hover_timer.stop()
        QToolTip.hideText()
        _HoverPopup.dismiss()


def _parse_hover_markdown(text: str) -> list:
    """
    Parse hover markdown into [(type, content), ...].
    Types: 'code', 'heading', 'prose'
    """
    blocks = []
    lines  = text.split("\n")
    i      = 0

    while i < len(lines):
        line = lines[i]

        # Fenced code block
        if line.strip().startswith("```"):
            lang  = line.strip()[3:].strip()
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            code = "\n".join(code_lines).strip()
            if code:
                blocks.append(("code", code))
            i += 1
            continue

        # Heading
        if line.startswith("#"):
            heading = _re.sub(r"^#+\s*", "", line).strip()
            if heading:
                blocks.append(("heading", heading))
            i += 1
            continue

        # Prose — accumulate until next special block
        prose_lines = []
        while i < len(lines):
            l = lines[i]
            if l.strip().startswith("```") or l.startswith("#"):
                break
            prose_lines.append(l)
            i += 1

        prose = "\n".join(prose_lines).strip()
        # Strip inline backticks for display — wrap in prose with accent
        prose = _re.sub(r'`([^`]+)`', r'\1', prose)
        if prose:
            blocks.append(("prose", prose))

    return blocks


def _show_hover_popup(parent, text: str, global_pos):
    _HoverPopup.show_at(parent, text, global_pos)
    
def _strip_snippet_markers(text: str) -> str:
    """Remove LSP snippet syntax: $0, $1, ${1:placeholder} etc."""
    import re
    # ${N:placeholder} → placeholder
    text = re.sub(r'\$\{[0-9]+:([^}]*)\}', r'\1', text)
    # ${N} or $N → empty
    text = re.sub(r'\$\{[0-9]+\}', '', text)
    text = re.sub(r'\$[0-9]+', '', text)
    return text

class LspEditorMixin:
    """
    Mixin for GhostEditor.

    Assumes the host class provides:
        self.file_path                  — str | None
        self.lsp_selections             — list
        self.update_extra_selections()
        self.goto_file_requested        — pyqtSignal(str, int, int)
    """

    def setup_lsp(self, lsp_manager):
        """
        Wire up LSP. Accepts an LSPManager.
        Call once the editor has a file_path.
        """
        self._lsp_manager    = lsp_manager
        self._hover_timer    = QTimer(self)
        self._hover_timer.setSingleShot(True)
        self._hover_timer.setInterval(450)
        self._hover_timer.timeout.connect(self._lsp_request_hover)

        self._last_hover_pos = QPoint()

        # Subscribe to diagnostics from all clients via manager
        for client in set(lsp_manager._ext_map.values()):
            client.diagnostics.connect(self._on_lsp_diagnostics)

        # Also wire any servers that start later
        lsp_manager.server_ready.connect(self._on_new_server_ready)

        self._lsp_sync_open()

        self._lsp_change_timer = QTimer(self)
        self._lsp_change_timer.setSingleShot(True)
        self._lsp_change_timer.setInterval(300)
        self._lsp_change_timer.timeout.connect(self._lsp_sync_change)
        self.textChanged.connect(self._lsp_change_timer.start)

        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        
        self._setup_completion()
        self.textChanged.connect(self._on_text_changed_for_completion)
    
    def teardown_lsp(self):
        if not hasattr(self, "_lsp_manager"):
            return
        try:
            self._lsp_manager.server_ready.disconnect(self._on_new_server_ready)
        except (RuntimeError, TypeError):
            pass
        for client in set(self._lsp_manager._ext_map.values()):
            try:
                client.diagnostics.disconnect(self._on_lsp_diagnostics)
            except (RuntimeError, TypeError):
                pass
        if getattr(self, "file_path", None):
            self._lsp_manager.close_file(self.file_path)
        self.lsp_selections = []
        self.update_extra_selections()

    def _on_new_server_ready(self, name: str):
        """Wire diagnostics from a server that became ready after setup."""
        for client in set(self._lsp_manager._ext_map.values()):
            try:
                client.diagnostics.disconnect(self._on_lsp_diagnostics)
            except (RuntimeError, TypeError):
                pass
            client.diagnostics.connect(self._on_lsp_diagnostics)
        # Open current file with the new server if it supports it
        self._lsp_sync_open()

    # ─────────────────────────────────────────────────────────────
    # Document sync
    # ─────────────────────────────────────────────────────────────

    def _lsp_sync_open(self):
        if not self._lsp_active():
            return
        self._lsp_manager.open_file(self.file_path, self.toPlainText())

    def _lsp_sync_change(self):
        if not self._lsp_active():
            return
        self._lsp_manager.change_file(self.file_path, self.toPlainText())

    def _lsp_active(self) -> bool:
        return (
            hasattr(self, "_lsp_manager")
            and self._lsp_manager is not None
            and self._lsp_manager.is_supported(getattr(self, "file_path", "") or "")
        )

    # ─────────────────────────────────────────────────────────────
    # Ctrl+Click → go-to-definition
    # ─────────────────────────────────────────────────────────────

    def mousePressEvent(self, event: QMouseEvent):
        # Multi-cursor: Alt+Click
        if hasattr(self, "multi_cursor"):
            if self.multi_cursor.handle_alt_click(event):
                return
        if (event.modifiers() & Qt.KeyboardModifier.ControlModifier
                and event.button() == Qt.MouseButton.LeftButton
                and self._lsp_active()):
            line, col = self._lsp_pos_from_viewport(event.pos())
            self._lsp_manager.definition(
                self.file_path, line, col,
                callback=self._on_lsp_definition,
            )
            event.accept()
            return
        super().mousePressEvent(event)

    def _on_lsp_definition(self, result):
        if not result:
            return
        locations = result if isinstance(result, list) else [result]
        if not locations:
            return
        loc       = locations[0]
        file_path = uri_to_path(loc.get("uri", ""))
        start     = loc.get("range", {}).get("start", {})
        line      = start.get("line", 0)
        col       = start.get("character", 0)
        if file_path == getattr(self, "file_path", None):
            self.lsp_jump_to(line, col)
        else:
            self.goto_file_requested.emit(file_path, line, col)

    def lsp_jump_to(self, line: int, col: int):
        block = self.document().findBlockByLineNumber(line)
        if not block.isValid():
            return
        cursor = QTextCursor(block)
        cursor.movePosition(
            QTextCursor.MoveOperation.Right,
            QTextCursor.MoveMode.MoveAnchor, col,
        )
        self.setTextCursor(cursor)
        self.centerCursor()

    # ─────────────────────────────────────────────────────────────
    # Hover tooltip
    # ─────────────────────────────────────────────────────────────

    def mouseMoveEvent(self, event: QMouseEvent):
        super().mouseMoveEvent(event)
        if not self._lsp_active():
            return
        self._last_hover_pos = event.pos()
        self._hover_timer.start()

    def leaveEvent(self, event):
        super().leaveEvent(event)
        if hasattr(self, "_hover_timer"):
            self._hover_timer.stop()
        QToolTip.hideText()

    def _lsp_request_hover(self):
        if not self._lsp_active():
            return
        line, col = self._lsp_pos_from_viewport(self._last_hover_pos)
        self._lsp_manager.hover(
            self.file_path, line, col, callback=self._on_lsp_hover
        )

    def _on_lsp_hover(self, result):
        if not result:
            return
    
        contents = result.get("contents", "")
        if isinstance(contents, dict):
            text = contents.get("value", "").strip()
            kind = contents.get("kind", "markdown")
        elif isinstance(contents, list):
            parts = []
            for c in contents:
                if isinstance(c, dict):
                    parts.append(c.get("value", ""))
                else:
                    parts.append(str(c))
            text = "\n".join(parts).strip()
            kind = "markdown"
        else:
            text = str(contents).strip()
            kind = "plaintext"
    
        if not text:
            return
    
        global_pos = self.viewport().mapToGlobal(self._last_hover_pos)
        _show_hover_popup(self, text, global_pos)
        
    # ─────────────────────────────────────────────────────────────
    # Rename symbol
    # ─────────────────────────────────────────────────────────────

    def trigger_rename(self):
        """Show the inline rename popup at the cursor."""
        if not self._lsp_active():
            return
 
        # Dismiss hover popup if showing
        from ui.lsp_editor import _HoverPopup
        _HoverPopup.dismiss() 
 
        # Get the word under the cursor as the default name
        cursor     = self.textCursor()
        cursor.select(cursor.SelectionType.WordUnderCursor)
        word       = cursor.selectedText().strip()
        if not word:
            return
 
        from ui.rename_dialog import RenamePopup
        popup = RenamePopup(self, word)
        popup.rename_confirmed.connect(self._do_rename)
        popup.cancelled.connect(self.setFocus)
        popup.show_at_cursor()
 
    def _do_rename(self, new_name: str):
        """Send the rename request to the LSP server."""
        if not self._lsp_active() or not self.file_path:
            return
 
        cursor = self.textCursor()
        line   = cursor.blockNumber()
        col    = cursor.positionInBlock()
 
        self._lsp_manager.rename(
            self.file_path, line, col, new_name,
            callback=self._apply_workspace_edit
        )
 
    def _apply_workspace_edit(self, workspace_edit):
        """Apply a WorkspaceEdit returned by textDocument/rename."""
        if not workspace_edit:
            return

        from ai.lsp_client import uri_to_path
        from PyQt6.QtGui import QTextCursor as _QTC
 
        # WorkspaceEdit has either 'changes' (uri → [TextEdit])
        # or 'documentChanges' ([TextDocumentEdit])
        changes = {}
 
        if "changes" in workspace_edit:
            changes = workspace_edit["changes"]
 
        elif "documentChanges" in workspace_edit:
            for doc_change in workspace_edit["documentChanges"]:
                uri   = doc_change.get("textDocument", {}).get("uri", "")
                edits = doc_change.get("edits", [])
                if uri:
                    changes[uri] = edits
 
        if not changes:
            return
 
        # Apply edits to each affected file
        # Sort URIs so the current file is applied last (preserves cursor)
        current_uri = f"file://{self.file_path}" if self.file_path else ""
        sorted_uris = sorted(
            changes.keys(),
            key=lambda u: (1 if u == current_uri else 0)
        )
 
        for uri in sorted_uris:
            edits     = changes[uri]
            file_path = uri_to_path(uri)
 
            # Find if this file is already open in an editor
            editor = self._find_open_editor(file_path)
 
            if editor is None:
                # File not open — apply edits directly to disk
                self._apply_edits_to_file(file_path, edits)
            else:
                # File is open — apply to the editor document
                self._apply_edits_to_editor(editor, edits)
 
        # Status message
        total_edits = sum(len(v) for v in changes.values())
        total_files = len(changes)
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(0, lambda: self._show_rename_status(
            total_edits, total_files
        ))
 
    def _show_rename_status(self, edits: int, files: int):
        """Show rename result in the main window status bar."""
        try:
            window = self.window()
            if hasattr(window, 'statusBar'):
                window.statusBar().showMessage(
                    f"Renamed: {edits} occurrence(s) across {files} file(s)",
                    4000
                )
        except RuntimeError:
            pass
 
    def _find_open_editor(self, file_path: str):
        """Search all open panes for an editor with this file path."""
        try:
            window = self.window()
            if hasattr(window, 'split_container'):
                for _, editor in window.split_container.all_editors():
                    if getattr(editor, 'file_path', None) == file_path:
                        return editor
        except RuntimeError:
            pass
        return None
 
    def _apply_edits_to_editor(self, editor, edits: list):
        from PyQt6.QtGui import QTextCursor
    
        doc = editor.document()
    
        def lsp_to_offset(line: int, char: int) -> int:
            block = doc.findBlockByLineNumber(line)
            if not block.isValid():
                return doc.characterCount() - 1
            return block.position() + min(char, max(0, block.length() - 1))
    
        prepared = []
        for edit in edits:
            rng      = edit.get("range", {})
            new_text = edit.get("newText", "")
            start    = rng.get("start", {})
            end      = rng.get("end",   {})
    
            s_line = start.get("line", 0)
            s_char = start.get("character", 0)
            e_line = end.get("line",   0)
            e_char = end.get("character", 0)
    
            s_offset = lsp_to_offset(s_line, s_char)
    
            # When e_char == 0, the range ends at the START of e_line.
            # pylsp sends the full file content in newText but doesn't
            # include e_line in the range — so we must extend the range
            # to cover e_line entirely, then strip it from the replacement.
            e_block = doc.findBlockByLineNumber(e_line)
            if e_char == 0 and e_block.isValid() and e_block.length() > 1:
                # Extend range to end of e_line (include the \n)
                e_offset = e_block.position() + e_block.length() - 1
                # Strip the duplicate from newText — newText already
                # contains the content of e_line at its end
            else:
                e_offset = lsp_to_offset(e_line, e_char)
    
            prepared.append((s_offset, e_offset, new_text))
    
        prepared.sort(key=lambda x: x[0], reverse=True)
    
        cursor = QTextCursor(doc)
        cursor.beginEditBlock()
    
        for s_offset, e_offset, new_text in prepared:
            cursor.setPosition(s_offset)
            cursor.setPosition(e_offset, QTextCursor.MoveMode.KeepAnchor)
            cursor.insertText(new_text)
    
        cursor.endEditBlock()
        editor.setTextCursor(cursor)
 
    def _apply_edits_to_file(self, file_path: str, edits: list):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
    
            # Work on the raw string rather than line-by-line
            # Convert LSP line/char positions to string offsets
            lines = content.split('\n')
    
            sorted_edits = sorted(
                edits,
                key=lambda e: (
                    e.get("range", {}).get("start", {}).get("line", 0),
                    e.get("range", {}).get("start", {}).get("character", 0),
                ),
                reverse=True,
            )
    
            for edit in sorted_edits:
                rng      = edit.get("range", {})
                new_text = edit.get("newText", "")
                start    = rng.get("start", {})
                end      = rng.get("end",   {})
    
                s_line = start.get("line", 0)
                s_char = start.get("character", 0)
                e_line = end.get("line", 0)
                e_char = end.get("character", 0)
    
                # Convert to flat string offsets
                s_offset = sum(len(lines[i]) + 1 for i in range(s_line)) + s_char
                e_offset = sum(len(lines[i]) + 1 for i in range(e_line)) + e_char
    
                # Clamp to content length
                s_offset = min(s_offset, len(content))
                e_offset = min(e_offset, len(content))
    
                content = content[:s_offset] + new_text + content[e_offset:]
    
                # Rebuild lines for subsequent edits (reverse order so this is fine)
                lines = content.split('\n')
    
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
    
        except Exception as e:
            print(f"[rename] failed to apply edits to {file_path}: {e}")

    # ─────────────────────────────────────────────────────────────
    # Diagnostic squiggles
    # ─────────────────────────────────────────────────────────────

    def _on_lsp_diagnostics(self, file_path: str, diags: list):
        if file_path != getattr(self, "file_path", None):
            return
        self._apply_lsp_squiggles(diags)

    def _apply_lsp_squiggles(self, diags: list):
        self.lsp_selections = []
        doc = self.document()

        for diag in diags:
            severity   = diag.get("severity", 4)
            color      = QColor(_SEVERITY_COLOR.get(severity, "#a89984"))
            rng        = diag.get("range", {})
            start_info = rng.get("start", {})
            end_info   = rng.get("end",   {})

            start_block = doc.findBlockByLineNumber(start_info.get("line", 0))
            end_block   = doc.findBlockByLineNumber(end_info.get("line",   0))
            if not start_block.isValid() or not end_block.isValid():
                continue

            cursor = QTextCursor(start_block)
            cursor.movePosition(
                QTextCursor.MoveOperation.Right,
                QTextCursor.MoveMode.MoveAnchor,
                start_info.get("character", 0),
            )
            cursor.setPosition(
                end_block.position() + end_info.get("character", 0),
                QTextCursor.MoveMode.KeepAnchor,
            )

            fmt = QTextCharFormat()
            fmt.setUnderlineStyle(QTextCharFormat.UnderlineStyle.SpellCheckUnderline)
            fmt.setUnderlineColor(color)
            fmt.setToolTip(diag.get("message", ""))

            sel        = QTextEdit.ExtraSelection()
            sel.cursor = cursor
            sel.format = fmt
            self.lsp_selections.append(sel)

        self.update_extra_selections()

    # ─────────────────────────────────────────────────────────────
    # Utility
    # ─────────────────────────────────────────────────────────────

    def _lsp_pos_from_viewport(self, viewport_pos: QPoint) -> tuple[int, int]:
        cursor = self.cursorForPosition(viewport_pos)
        return cursor.blockNumber(), cursor.positionInBlock()

    def cursor_lsp_position(self) -> tuple[int, int]:
        cursor = self.textCursor()
        return cursor.blockNumber(), cursor.positionInBlock()

    # ── Completion ────────────────────────────────────────────────────────
 
    # Trigger characters that auto-show completion for most languages
    _TRIGGER_CHARS = set('.(:,@>')
 
    def _setup_completion(self):
        """Call from setup_lsp() after existing timer setup."""
        self._completion_timer = QTimer(self)
        self._completion_timer.setSingleShot(True)
        self._completion_timer.setInterval(400)   # 400ms auto-trigger delay
        self._completion_timer.timeout.connect(self._request_completion)
        self._last_trigger_char = None
        # Dismiss popup when editor scrolls
        self.verticalScrollBar().valueChanged.connect(
            lambda: CompletionPopup.close_current()
        )
 
    def _on_text_changed_for_completion(self):
        if getattr(self, '_accepting_completion', False):
            return
        if not self._lsp_active():
            return
    
        cursor = self.textCursor()
        col    = cursor.positionInBlock()
        text   = cursor.block().text()
    
        if col == 0:
            CompletionPopup.close_current()
            return
    
        char = text[col - 1] if col > 0 else ""
    
        # Auto-trigger on trigger characters
        if char in self._TRIGGER_CHARS:
            self._last_trigger_char = char
            self._completion_timer.start(50)
            return
    
        # Auto-trigger if we're in the middle of a word (3+ chars)
        start = col
        while start > 0 and (text[start - 1].isalnum() or text[start - 1] == '_'):
            start -= 1
        word = text[start:col]
    
        if len(word) >= 3:
            self._last_trigger_char = None
            self._completion_timer.start(400)
        else:
            # Word too short — close popup if open
            self._completion_timer.stop()
            if len(word) == 0:
                CompletionPopup.close_current()
 
    def request_completion_now(self):
        """Manual trigger — Ctrl+Space."""
        if not self._lsp_active():
            return
        self._last_trigger_char = None
        self._completion_timer.stop()
        self._request_completion(trigger_kind=1)
 
    def _request_completion(self, trigger_kind=None):
        if not self._lsp_active():
            return
        from ui.completion_popup import CompletionPopup
        # Don't re-request if popup is already showing with content
        # (let existing popup stand; it'll re-request on next keystroke)
 
        line, col = self._lsp_pos_from_viewport(self._last_hover_pos)
        # Use actual cursor position, not hover position
        cursor = self.textCursor()
        line   = cursor.blockNumber()
        col    = cursor.positionInBlock()
 
        char = self._last_trigger_char
        kind = trigger_kind if trigger_kind else (2 if char else 1)
 
        self._lsp_manager.completion(
            self.file_path, line, col,
            trigger_kind=kind,
            trigger_char=char,
            callback=self._on_completion_result,
        )
 
    def _on_completion_result(self, items: list):
        if not items:
            CompletionPopup.close_current()
            return
 
        # Filter out items with no label
        items = [i for i in items if i.get("label", "").strip()]
        if not items:
            CompletionPopup.close_current()
            return
 
        # Prefix-filter against current word
        cursor      = self.textCursor()
        block_text  = cursor.block().text()
        col         = cursor.positionInBlock()
        # Walk left to find start of current word
        start = col
        while start > 0 and (block_text[start - 1].isalnum()
                              or block_text[start - 1] in '_'):
            start -= 1
        prefix = block_text[start:col].lower()
 
        if prefix:
            filtered = [i for i in items
                        if i.get("label", "").lower().startswith(prefix)]
            if not filtered:
                # Fuzzy fallback — any item containing prefix
                filtered = [i for i in items
                            if prefix in i.get("label", "").lower()]
            items = filtered if filtered else items
 
        if not items:
            CompletionPopup.close_current()
            return
 
        # Close existing and show new
        CompletionPopup.close_current()
        popup = CompletionPopup(self, items)
        popup.item_accepted.connect(self._on_completion_accepted)
        popup.position_at_cursor()
        popup.show()
        popup.raise_()
        
        # Silence re-trigger for 500ms after accepting
        self._completion_timer.stop()
        self._last_trigger_char = None
        self._accepting_completion = True
        QTimer.singleShot(500, self._clear_accepting_flag)
    
    def _clear_accepting_flag(self):
        self._accepting_completion = False
 
    def _on_completion_accepted(self, item: dict):
        """Insert the selected completion item into the editor."""
        cursor = self.textCursor()
 
        # Determine insert text
        insert_text = (item.get("insertText")
                       or item.get("label", ""))
 
        # If LSP provides a textEdit, use that range
        text_edit = item.get("textEdit")
        if text_edit:
            rng   = text_edit.get("range", {})
            start = rng.get("start", {})
            end   = rng.get("end",   {})
            doc   = self.document()
            s_block = doc.findBlockByLineNumber(start.get("line", 0))
            e_block = doc.findBlockByLineNumber(end.get("line", 0))
            if s_block.isValid() and e_block.isValid():
                s_pos = s_block.position() + start.get("character", 0)
                e_pos = e_block.position() + end.get("character", 0)
                cursor.setPosition(s_pos)
                cursor.setPosition(e_pos, cursor.MoveMode.KeepAnchor)
                insert_text = text_edit.get("newText", insert_text)
        else:
            # No textEdit — replace current word prefix
            block_text = cursor.block().text()
            col        = cursor.positionInBlock()
            start_col  = col
            while start_col > 0 and (block_text[start_col - 1].isalnum()
                                     or block_text[start_col - 1] in '_'):
                start_col -= 1
            if start_col < col:
                cursor.setPosition(
                    cursor.block().position() + start_col
                )
                cursor.setPosition(
                    cursor.block().position() + col,
                    cursor.MoveMode.KeepAnchor,
                )
 
        # Strip snippet placeholders ($0, $1, ${1:placeholder})
        insert_text = _strip_snippet_markers(insert_text)
 
        cursor.insertText(insert_text)
        self.setTextCursor(cursor)
        self.clear_ghost_text()
        
        # Silence re-trigger for 600ms after accepting
        self._accepting_completion = True
        self._completion_timer.stop()
        QTimer.singleShot(600, self._clear_accepting_flag)
    
    def _clear_accepting_flag(self):
        self._accepting_completion = False
    
    def _on_text_changed_for_completion(self):
        if getattr(self, '_accepting_completion', False):
            return