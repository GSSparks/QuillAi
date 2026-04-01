"""
ui/lsp_editor.py

LspEditorMixin — add to GhostEditor to get:
  - Ctrl+Click  → go-to-definition
  - Hover       → tooltip with signature/docstring
  - Squiggles   → diagnostic underlines that coexist with lint/bracket selections

Design notes for GhostEditor compatibility:
  - GhostEditor owns update_extra_selections() which merges three lists:
        current_line_selection + lint_selections + bracket_selections
    We add a fourth: lsp_selections. _apply_lsp_squiggles() populates it and
    calls update_extra_selections() — never setExtraSelections() directly.
  - mousePressEvent/mouseMoveEvent call super() so GhostEditor's own
    handlers (color swatch, etc.) still fire.
  - The LSP sync timer is separate from GhostEditor's diff_timer/lint_timer.
  - leaveEvent is not defined on GhostEditor so no collision there.
  - goto_file_requested signal must be declared on GhostEditor itself
    (Qt signals can't live on a plain Python mixin).
"""

from PyQt6.QtCore    import Qt, QTimer, QPoint
from PyQt6.QtGui     import QTextCharFormat, QColor, QTextCursor, QMouseEvent
from PyQt6.QtWidgets import QTextEdit, QToolTip

from ai.lsp_client import uri_to_path


# ─────────────────────────────────────────────────────────────────────────────
# Severity → underline colour  (Gruvbox palette)
# ─────────────────────────────────────────────────────────────────────────────

_SEVERITY_COLOR = {
    1: "#fb4934",   # Error   — red
    2: "#fabd2f",   # Warning — yellow
    3: "#83a598",   # Info    — blue
    4: "#a89984",   # Hint    — grey
}


class LspEditorMixin:
    """
    Mixin for GhostEditor (QPlainTextEdit subclass).

    Assumes the host class provides:
        self.file_path                  — str | None
        self.lsp_selections             — list  (declared in GhostEditor.__init__)
        self.update_extra_selections()  — merges all selection lists
        self.goto_file_requested        — pyqtSignal(str, int, int)
    """

    def setup_lsp(self, lsp_client):
        """
        Wire up LSP. Call once the editor has a file_path and
        the LSP client has emitted initialized.
        """
        self._lsp            = lsp_client
        self._hover_timer    = QTimer(self)
        self._hover_timer.setSingleShot(True)
        self._hover_timer.setInterval(450)
        self._hover_timer.timeout.connect(self._lsp_request_hover)

        self._last_hover_pos = QPoint()

        # Diagnostic push from server → update squiggles
        self._lsp.diagnostics.connect(self._on_lsp_diagnostics)

        # Sync document to LSP immediately
        self._lsp_sync_open()

        # Debounced full-text sync on every edit (300 ms)
        self._lsp_change_timer = QTimer(self)
        self._lsp_change_timer.setSingleShot(True)
        self._lsp_change_timer.setInterval(300)
        self._lsp_change_timer.timeout.connect(self._lsp_sync_change)
        self.textChanged.connect(self._lsp_change_timer.start)

        # Mouse tracking for hover tooltip
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)

    def teardown_lsp(self):
        """Call when the tab closes."""
        if not hasattr(self, "_lsp"):
            return
        try:
            self._lsp.diagnostics.disconnect(self._on_lsp_diagnostics)
        except RuntimeError:
            pass
        if getattr(self, "file_path", None):
            self._lsp.close_file(self.file_path)
        self.lsp_selections = []
        self.update_extra_selections()

    # ─────────────────────────────────────────────────────────────
    # Document sync
    # ─────────────────────────────────────────────────────────────

    def _lsp_sync_open(self):
        if not self._lsp_active():
            return
        self._lsp.open_file(self.file_path, self.toPlainText())

    def _lsp_sync_change(self):
        if not self._lsp_active():
            return
        self._lsp.change_file(self.file_path, self.toPlainText())

    def _lsp_active(self) -> bool:
        return (
            hasattr(self, "_lsp")
            and self._lsp is not None
            and self._lsp.is_ready
            and getattr(self, "file_path", None) is not None
            and self.file_path.endswith(".py")
        )

    # ─────────────────────────────────────────────────────────────
    # Ctrl+Click → go-to-definition
    # ─────────────────────────────────────────────────────────────

    def mousePressEvent(self, event: QMouseEvent):
        if (event.modifiers() & Qt.KeyboardModifier.ControlModifier
                and event.button() == Qt.MouseButton.LeftButton
                and self._lsp_active()):
            line, col = self._lsp_pos_from_viewport(event.pos())
            self._lsp.definition(
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
        uri       = loc.get("uri", "")
        file_path = uri_to_path(uri)
        start     = loc.get("range", {}).get("start", {})
        line      = start.get("line", 0)
        col       = start.get("character", 0)
        if file_path == getattr(self, "file_path", None):
            self.lsp_jump_to(line, col)
        else:
            self.goto_file_requested.emit(file_path, line, col)

    def lsp_jump_to(self, line: int, col: int):
        """Jump cursor to 0-indexed (line, col) and centre view."""
        block = self.document().findBlockByLineNumber(line)
        if not block.isValid():
            return
        cursor = QTextCursor(block)
        cursor.movePosition(
            QTextCursor.MoveOperation.Right,
            QTextCursor.MoveMode.MoveAnchor,
            col,
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
        self._lsp.hover(self.file_path, line, col, callback=self._on_lsp_hover)

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
        """
        Populate self.lsp_selections and call update_extra_selections().
        Never calls setExtraSelections() directly — that would clobber
        GhostEditor's lint/bracket/current-line selections.
        """
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