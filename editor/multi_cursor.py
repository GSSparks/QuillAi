"""
editor/multi_cursor.py

MultiCursorManager — all multi-cursor logic for GhostEditor.

Triggers:
    Ctrl+D          — add cursor at next occurrence of word/selection
                      (press again to remove last added cursor)
    Ctrl+Shift+L    — add cursors at ALL occurrences
    Ctrl+Alt+Up/Down — add cursor on line above/below (column mode)
    Alt+Click       — add cursor at click position (toggle)
    Escape          — clear all secondary cursors

Undo: all cursor edits wrapped in a single editBlock — one Ctrl+Z
      undoes all cursors' changes atomically.

Rendering: secondary cursors as tinted ExtraSelections merged into
           GhostEditor.update_extra_selections() via mc_selections.
"""

import re
from PyQt6.QtCore import Qt
from PyQt6.QtGui  import (QTextCursor, QTextCharFormat, QColor,
                           QMouseEvent, QTextDocument)
from PyQt6.QtWidgets import QTextEdit

# Convenient aliases
_FIND_CASE  = QTextDocument.FindFlag.FindCaseSensitively
_FIND_WHOLE = QTextDocument.FindFlag.FindWholeWords
_MOVE       = QTextCursor.MoveMode.MoveAnchor
_KEEP       = QTextCursor.MoveMode.KeepAnchor
_Op         = QTextCursor.MoveOperation


class MultiCursorManager:

    def __init__(self):
        self._editor  = None
        self._cursors: list[QTextCursor] = []

    def setup(self, editor):
        self._editor = editor

    # ─────────────────────────────────────────────────────────────
    # State
    # ─────────────────────────────────────────────────────────────

    def cursor_count(self) -> int:
        return len(self._cursors) + 1   # +1 for primary

    @property
    def active(self) -> bool:
        return bool(self._cursors)

    # ─────────────────────────────────────────────────────────────
    # Ctrl+D — next occurrence
    # ─────────────────────────────────────────────────────────────

    def add_next_occurrence(self):
        editor  = self._editor
        doc     = editor.document()
        primary = editor.textCursor()

        word, flags = self._search_term(primary)
        if not word:
            return

        # Search from end of last added cursor (or primary)
        search_from = (self._cursors[-1].selectionEnd()
                       if self._cursors else primary.selectionEnd())

        found = doc.find(word, search_from, flags)
        if found.isNull():                          # wrap around
            found = doc.find(word, 0, flags)
        if found.isNull():
            return

        # Skip if position already occupied
        occupied = {c.selectionEnd() for c in self._cursors}
        occupied.add(primary.selectionEnd())
        if found.selectionEnd() in occupied:
            return

        # Ensure primary also has a selection (select its word)
        if not primary.hasSelection():
            w = doc.find(word, primary.position() - len(word), flags)
            if not w.isNull():
                editor.setTextCursor(w)

        self._cursors.append(found)
        self._render()

    def remove_last_occurrence(self):
        if self._cursors:
            self._cursors.pop()
            self._render()

    # ─────────────────────────────────────────────────────────────
    # Ctrl+Shift+L — all occurrences
    # ─────────────────────────────────────────────────────────────

    def add_all_occurrences(self):
        editor  = self._editor
        doc     = editor.document()
        primary = editor.textCursor()

        word, flags = self._search_term(primary)
        if not word:
            return

        self._cursors.clear()
        primary_end = (primary.selectionEnd()
                       if primary.hasSelection() else primary.position())

        c = doc.find(word, 0, flags)
        while not c.isNull():
            if c.selectionEnd() != primary_end:
                self._cursors.append(QTextCursor(c))
            c = doc.find(word, c.selectionEnd(), flags)

        # Select primary's occurrence too
        if not primary.hasSelection():
            m = doc.find(word, primary.position() - len(word), flags)
            if not m.isNull():
                editor.setTextCursor(m)

        self._render()

    # ─────────────────────────────────────────────────────────────
    # Ctrl+Alt+Up / Down — column mode
    # ─────────────────────────────────────────────────────────────

    def add_cursor_above(self):
        self._add_vertical(-1)

    def add_cursor_below(self):
        self._add_vertical(1)

    def _add_vertical(self, direction: int):
        editor = self._editor
        ref    = self._cursors[-1] if self._cursors else editor.textCursor()
        col    = ref.positionInBlock()
        block  = (ref.block().next() if direction > 0
                  else ref.block().previous())
        if not block.isValid():
            return

        col = min(col, len(block.text()))
        nc  = QTextCursor(block)
        nc.movePosition(_Op.Right, _MOVE, col)

        occupied = {c.position() for c in self._cursors}
        occupied.add(editor.textCursor().position())
        if nc.position() not in occupied:
            self._cursors.append(nc)
            self._render()

    # ─────────────────────────────────────────────────────────────
    # Alt+Click
    # ─────────────────────────────────────────────────────────────

    def handle_alt_click(self, event: QMouseEvent) -> bool:
        if not (event.modifiers() & Qt.KeyboardModifier.AltModifier
                and event.button() == Qt.MouseButton.LeftButton):
            return False

        editor = self._editor
        nc     = editor.cursorForPosition(event.pos())

        # Toggle off if clicking existing secondary cursor
        for i, c in enumerate(self._cursors):
            if c.position() == nc.position():
                self._cursors.pop(i)
                self._render()
                return True

        if nc.position() != editor.textCursor().position():
            self._cursors.append(nc)
            self._render()
        return True

    # ─────────────────────────────────────────────────────────────
    # Clear
    # ─────────────────────────────────────────────────────────────

    def clear(self):
        import traceback
        print(f"[mc] clear() called with {len(self._cursors)} cursors")
        traceback.print_stack(limit=6)
        self._cursors.clear()
        self._render()

    # ─────────────────────────────────────────────────────────────
    # Keypress dispatch
    # ─────────────────────────────────────────────────────────────

    def handle_key(self, event) -> bool:
        """
        Apply edits to secondary cursors and let Qt handle the primary.

        Returns True to tell keyPressEvent to call super() immediately
        after — Qt's native handler runs for the primary cursor, and
        _apply handles all secondary cursors. This way the primary is
        never touched twice.
        """
        if not self._cursors:
            return False

        key  = event.key()
        text = event.text()
        mods = event.modifiers()

        if key == Qt.Key.Key_Escape:
            self.clear()
            return True

        # Navigation — move all cursors manually (including primary)
        # Primary movement is handled here, NOT via super()
        if key in _NAV_KEYS:
            self._navigate(key, mods)
            return True   # keyPressEvent will NOT call super() for nav

        if key == Qt.Key.Key_Backspace:
            self._apply(lambda c: self._backspace(c))
            return True   # super() handles primary backspace

        if key == Qt.Key.Key_Delete:
            self._apply(lambda c: self._delete(c))
            return True   # super() handles primary delete

        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            def insert_return(c):
                if c.hasSelection():
                    c.removeSelectedText()
                c.insertText("\n")
            self._apply(insert_return)
            return True
        
        if key == Qt.Key.Key_Tab:
            def insert_tab(c):
                if c.hasSelection():
                    c.removeSelectedText()
                c.insertText("    ")
            self._apply(insert_tab)
            return True

        if text and text.isprintable() and not mods & Qt.KeyboardModifier.ControlModifier:
            def insert_char(c, t=text):
                if c.hasSelection():
                    c.removeSelectedText()
                c.insertText(t)
            self._apply(insert_char)
            return True

        return False

    # ─────────────────────────────────────────────────────────────
    # Edit application
    # ─────────────────────────────────────────────────────────────

    def _apply(self, fn):
        """
        Apply fn(cursor) to all SECONDARY cursors in reverse document order.
    
        The primary cursor is handled by Qt (via keyPressEvent),
        so we never touch it here. This avoids double-application bugs.
        """
        editor = self._editor
        doc    = editor.document()
        p      = editor.textCursor()
    
        if not self._cursors:
            return
    
        # Snapshot positions BEFORE edits (anchor, position)
        def cursor_bounds(c):
            if c.hasSelection():
                return (c.anchor(), c.position())
            return (c.position(), c.position())
    
        bounds = [cursor_bounds(c) for c in self._cursors]
    
        # Sort by position (descending) to avoid shifting issues
        bounds.sort(key=lambda b: b[1], reverse=True)
    
        # Build fresh cursors from static positions
        def make_cursor(anchor, pos):
            c = QTextCursor(doc)
            c.setPosition(anchor)
            if pos != anchor:
                c.setPosition(pos, _KEEP)
            return c
    
        ordered_cursors = [make_cursor(a, pos) for a, pos in bounds]
    
        # Apply all edits in a single undo block (anchored on primary)
        p.beginEditBlock()
        try:
            for cursor in ordered_cursors:
                fn(cursor)
        finally:
            p.endEditBlock()
    
        # Rebuild secondary cursors from updated positions
        self._cursors = [QTextCursor(c) for c in ordered_cursors]
    
        self._render()

    @staticmethod
    def _backspace(c: QTextCursor):
        if c.hasSelection():
            c.removeSelectedText()
        else:
            c.deletePreviousChar()

    @staticmethod
    def _delete(c: QTextCursor):
        if c.hasSelection():
            c.removeSelectedText()
        else:
            c.deleteChar()

    def _navigate(self, key, mods):
        editor  = self._editor
        primary = editor.textCursor()
        keep    = bool(mods & Qt.KeyboardModifier.ShiftModifier)
        ctrl    = bool(mods & Qt.KeyboardModifier.ControlModifier)
        mode    = _KEEP if keep else _MOVE

        op = _NAV_MAP.get(key)
        if op is None:
            return

        # Ctrl+Left/Right → word jump
        if ctrl and key == Qt.Key.Key_Left:
            op = _Op.WordLeft
        elif ctrl and key == Qt.Key.Key_Right:
            op = _Op.WordRight

        primary.movePosition(op, mode)
        editor.setTextCursor(primary)
        for c in self._cursors:
            c.movePosition(op, mode)
        self._render()

    # ─────────────────────────────────────────────────────────────
    # Search helpers
    # ─────────────────────────────────────────────────────────────

    def _search_term(self, cursor: QTextCursor):
        """Return (text, FindFlags) for the current cursor state."""
        if cursor.hasSelection():
            # Use literal selection, case-sensitive
            return cursor.selectedText(), _FIND_CASE

        # Expand to word under cursor
        c = QTextCursor(cursor)
        c.select(QTextCursor.SelectionType.WordUnderCursor)
        word = c.selectedText().strip()
        if not word or not re.match(r'\w', word):
            return "", _FIND_CASE | _FIND_WHOLE

        return word, _FIND_CASE | _FIND_WHOLE

    # ─────────────────────────────────────────────────────────────
    # Rendering
    # ─────────────────────────────────────────────────────────────

    def _render(self):
        if not self._editor:
            return
        editor = self._editor
        t      = editor._t

        accent = QColor(t.get("accent", "#fabd2f"))
        sel_bg = QColor(t.get("bg3",    "#665c54"))
        sel_fg = QColor(t.get("fg0",    "#fbf1c7"))

        # Selection highlight — used when cursor has a selection
        sel_fmt = QTextCharFormat()
        sel_fmt.setBackground(sel_bg)
        sel_fmt.setForeground(sel_fg)

        # Cursor bar — 1-char selection with accent left-border tint
        # Qt doesn't support a true zero-width cursor in ExtraSelections,
        # so we highlight one character and use a distinct background.
        bar_fmt = QTextCharFormat()
        bar_fmt.setBackground(QColor(
            accent.red(), accent.green(), accent.blue(), 80
        ))
        # Underline in accent colour gives a visible caret-like indicator
        bar_fmt.setUnderlineStyle(
            QTextCharFormat.UnderlineStyle.SingleUnderline
        )
        bar_fmt.setUnderlineColor(accent)

        selections = []
        for c in self._cursors:
            sel = QTextEdit.ExtraSelection()
            if c.hasSelection():
                sel.cursor = QTextCursor(c)
                sel.format = sel_fmt
            else:
                # Highlight the character at cursor position
                bar = QTextCursor(c)
                bar.movePosition(_Op.Right, _KEEP, 1)
                sel.cursor = bar
                sel.format = bar_fmt
            selections.append(sel)

        editor.mc_selections = selections
        editor.update_extra_selections()


# ─────────────────────────────────────────────────────────────────────────────
# Navigation key maps
# ─────────────────────────────────────────────────────────────────────────────

_NAV_KEYS = {
    Qt.Key.Key_Left, Qt.Key.Key_Right,
    Qt.Key.Key_Up,   Qt.Key.Key_Down,
    Qt.Key.Key_Home, Qt.Key.Key_End,
    Qt.Key.Key_PageUp, Qt.Key.Key_PageDown,
}

_NAV_MAP = {
    Qt.Key.Key_Left:    _Op.Left,
    Qt.Key.Key_Right:   _Op.Right,
    Qt.Key.Key_Up:      _Op.Up,
    Qt.Key.Key_Down:    _Op.Down,
    Qt.Key.Key_Home:    _Op.StartOfLine,
    Qt.Key.Key_End:     _Op.EndOfLine,
    Qt.Key.Key_PageUp:  _Op.Start,
    Qt.Key.Key_PageDown:_Op.End,
}