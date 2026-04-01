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

from PyQt6.QtCore    import Qt, QTimer, QPoint
from PyQt6.QtGui     import QTextCharFormat, QColor, QTextCursor, QMouseEvent
from PyQt6.QtWidgets import QTextEdit, QToolTip

from ai.lsp_client import uri_to_path


_SEVERITY_COLOR = {
    1: "#fb4934",   # Error   — Gruvbox red
    2: "#fabd2f",   # Warning — Gruvbox yellow
    3: "#83a598",   # Info    — Gruvbox blue
    4: "#a89984",   # Hint    — Gruvbox grey
}


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
        elif isinstance(contents, list):
            text = "\n".join(
                c.get("value", c) if isinstance(c, dict) else str(c)
                for c in contents
            ).strip()
        else:
            text = str(contents).strip()
        if text:
            global_pos = self.viewport().mapToGlobal(self._last_hover_pos)
            QToolTip.showText(global_pos, text, self)

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