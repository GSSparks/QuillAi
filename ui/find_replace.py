import re
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLineEdit,
                             QPushButton, QCheckBox)
from PyQt6.QtGui import QTextDocument, QTextCursor
from PyQt6.QtCore import Qt

from ui.theme import (get_theme, theme_signals,
                      build_find_replace_stylesheet,
                      build_match_label_stylesheet)


class FindReplaceWidget(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self._t = get_theme()
        self._setup_ui()
        self.apply_styles(self._t)
        theme_signals.theme_changed.connect(self._on_theme_changed)

    # ── Theme handling ────────────────────────────────────────────────────

    def _on_theme_changed(self, t: dict):
        self._t = t
        self.apply_styles(t)

    def apply_styles(self, t: dict):
        self.setStyleSheet(build_find_replace_stylesheet(t))
        # Reset match label to neutral — state will re-apply on next search
        self.match_label.setStyleSheet(build_match_label_stylesheet(t, ''))

    # ── UI Setup ──────────────────────────────────────────────────────────

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        # ── Find row ──────────────────────────────────────────────
        find_layout = QHBoxLayout()

        self.find_input = QLineEdit()
        self.find_input.setPlaceholderText("Find...")
        self.find_input.returnPressed.connect(self.find_next)
        self.find_input.textChanged.connect(self.on_search_text_changed)

        self.case_checkbox = QCheckBox("Aa")
        self.case_checkbox.setToolTip("Match Case")
        self.case_checkbox.stateChanged.connect(self.on_search_text_changed)

        self.word_checkbox = QCheckBox("ab|")
        self.word_checkbox.setToolTip("Match Whole Word")
        self.word_checkbox.stateChanged.connect(self.on_search_text_changed)

        self.regex_checkbox = QCheckBox(".*")
        self.regex_checkbox.setToolTip("Use Regular Expression")
        self.regex_checkbox.stateChanged.connect(self.on_search_text_changed)

        self.match_label = QPushButton("")
        self.match_label.setFlat(True)
        self.match_label.setEnabled(False)

        self.prev_btn = QPushButton("↑")
        self.prev_btn.setToolTip("Previous Match")
        self.prev_btn.clicked.connect(self.find_prev)

        self.next_btn = QPushButton("↓")
        self.next_btn.setToolTip("Next Match")
        self.next_btn.clicked.connect(self.find_next)

        self.close_btn = QPushButton("✕")
        self.close_btn.setObjectName("closeBtn")
        self.close_btn.clicked.connect(self.hide)

        find_layout.addWidget(self.find_input)
        find_layout.addWidget(self.case_checkbox)
        find_layout.addWidget(self.word_checkbox)
        find_layout.addWidget(self.regex_checkbox)
        find_layout.addWidget(self.match_label)
        find_layout.addWidget(self.prev_btn)
        find_layout.addWidget(self.next_btn)
        find_layout.addWidget(self.close_btn)

        # ── Replace row ───────────────────────────────────────────
        replace_layout = QHBoxLayout()

        self.replace_input = QLineEdit()
        self.replace_input.setPlaceholderText("Replace...")
        self.replace_input.returnPressed.connect(self.replace)

        self.replace_btn = QPushButton("Replace")
        self.replace_btn.clicked.connect(self.replace)

        self.replace_all_btn = QPushButton("Replace All")
        self.replace_all_btn.clicked.connect(self.replace_all)

        replace_layout.addWidget(self.replace_input)
        replace_layout.addWidget(self.replace_btn)
        replace_layout.addWidget(self.replace_all_btn)
        replace_layout.addStretch()

        layout.addLayout(find_layout)
        layout.addLayout(replace_layout)

    # ── Search state ──────────────────────────────────────────────────────

    def set_find_state(self, state: str):
        """Update find input border and match label color. state: 'match' | 'no_match' | ''"""
        self.find_input.setProperty("state", state)
        self.find_input.style().unpolish(self.find_input)
        self.find_input.style().polish(self.find_input)
        self.match_label.setStyleSheet(build_match_label_stylesheet(self._t, state))

    def count_matches(self, query: str) -> int:
        editor = self.main_window.current_editor()
        if not editor or not query:
            return 0
        if self.is_regex():
            return len(self._regex_find_all(editor.toPlainText(), query))
        options = self.get_search_options()
        document = editor.document()
        count = 0
        cursor = QTextCursor(document)
        while True:
            cursor = (document.find(query, cursor, options)
                      if options else document.find(query, cursor))
            if cursor.isNull():
                break
            count += 1
        return count

    def on_search_text_changed(self):
        query = self.find_input.text()
        editor = self.main_window.current_editor()
        if not editor:
            return

        if not query:
            self.set_find_state("")
            self.match_label.setText("")
            cursor = editor.textCursor()
            cursor.clearSelection()
            editor.setTextCursor(cursor)
            return

        if self.is_regex():
            # Validate regex first
            try:
                re.compile(query)
            except re.error:
                self.match_label.setText("bad regex")
                self.set_find_state("no_match")
                return
            matches = self._regex_find_all(editor.toPlainText(), query)
            if matches:
                self.match_label.setText(f"{len(matches)} found")
                self.set_find_state("match")
                s, e = matches[0]
                cursor = editor.textCursor()
                cursor.setPosition(s)
                cursor.setPosition(e, QTextCursor.MoveMode.KeepAnchor)
                editor.setTextCursor(cursor)
                editor.ensureCursorVisible()
            else:
                self.match_label.setText("no match")
                self.set_find_state("no_match")
            return

        options = self.get_search_options()
        document = editor.document()
        start_cursor = QTextCursor(document)
        first_match = (document.find(query, start_cursor, options)
                       if options else document.find(query, start_cursor))

        if not first_match.isNull():
            total = self.count_matches(query)
            self.match_label.setText(f"{total} found")
            self.set_find_state("match")
            editor.setTextCursor(first_match)
            editor.ensureCursorVisible()
        else:
            self.match_label.setText("no match")
            self.set_find_state("no_match")
            cursor = editor.textCursor()
            cursor.clearSelection()
            editor.setTextCursor(cursor)

    # ── Search options ────────────────────────────────────────────────────

    def is_regex(self) -> bool:
        return self.regex_checkbox.isChecked()

    def get_search_options(self, backward=False):
        """Returns QTextDocument.FindFlag options for non-regex search."""
        options = None
        if self.case_checkbox.isChecked():
            options = QTextDocument.FindFlag.FindCaseSensitively
        if self.word_checkbox.isChecked():
            options = (options | QTextDocument.FindFlag.FindWholeWords
                       if options else QTextDocument.FindFlag.FindWholeWords)
        if backward:
            options = (options | QTextDocument.FindFlag.FindBackward
                       if options else QTextDocument.FindFlag.FindBackward)
        return options

    def get_re_flags(self) -> int:
        """Returns re module flags for regex search."""
        flags = re.MULTILINE
        if not self.case_checkbox.isChecked():
            flags |= re.IGNORECASE
        return flags

    def _regex_find_all(self, text: str, pattern: str) -> list:
        """Return list of (start, end) for all regex matches."""
        try:
            return [(m.start(), m.end()) for m in
                    re.finditer(pattern, text, self.get_re_flags())]
        except re.error:
            return []

    def _regex_find_from(self, text: str, pattern: str, pos: int,
                         backward: bool = False) -> tuple | None:
        """Return (start, end) of next/prev regex match from pos."""
        matches = self._regex_find_all(text, pattern)
        if not matches:
            return None
        if backward:
            candidates = [(s, e) for s, e in matches if e <= pos]
            return candidates[-1] if candidates else matches[-1]
        else:
            candidates = [(s, e) for s, e in matches if s >= pos]
            return candidates[0] if candidates else matches[0]

    # ── Find / replace actions ────────────────────────────────────────────

    def do_find(self, backward=False) -> bool:
        editor = self.main_window.current_editor()
        if not editor:
            return False
        query = self.find_input.text()
        if not query:
            return False

        if self.is_regex():
            text = editor.toPlainText()
            pos  = editor.textCursor().position()
            if backward:
                pos = editor.textCursor().selectionStart()
            else:
                pos = editor.textCursor().selectionEnd()
            match = self._regex_find_from(text, query, pos, backward)
            if match:
                s, e = match
                cursor = editor.textCursor()
                cursor.setPosition(s)
                cursor.setPosition(e, QTextCursor.MoveMode.KeepAnchor)
                editor.setTextCursor(cursor)
                editor.ensureCursorVisible()
                total = len(self._regex_find_all(text, query))
                self.match_label.setText(f"{total} found")
                self.set_find_state("match")
                return True
            self.set_find_state("no_match")
            return False

        options = self.get_search_options(backward)
        document = editor.document()
        cursor  = editor.textCursor()
        found   = (document.find(query, cursor, options)
                   if options else document.find(query, cursor))
        if found.isNull():
            # Wrap around
            wrap = QTextCursor(document)
            if backward:
                wrap.movePosition(QTextCursor.MoveOperation.End)
            found = (document.find(query, wrap, options)
                     if options else document.find(query, wrap))
        if not found.isNull():
            editor.setTextCursor(found)
            editor.ensureCursorVisible()
            self.set_find_state("match")
            return True
        self.set_find_state("no_match")
        return False

    def find_next(self):
        self.do_find(backward=False)

    def find_prev(self):
        self.do_find(backward=True)

    def replace(self):
        editor = self.main_window.current_editor()
        if not editor:
            return
        query       = self.find_input.text()
        replacement = self.replace_input.text()
        cursor = editor.textCursor()
        if cursor.hasSelection():
            if self.is_regex():
                try:
                    subst = re.sub(query, replacement,
                                  cursor.selectedText(),
                                  flags=self.get_re_flags())
                    cursor.insertText(subst)
                except re.error:
                    pass
            else:
                cursor.insertText(replacement)
        self.do_find()
        self.on_search_text_changed()

    def replace_all(self):
        editor = self.main_window.current_editor()
        if not editor:
            return
        query       = self.find_input.text()
        replacement = self.replace_input.text()
        if not query:
            return
        text = editor.toPlainText()
        if self.is_regex():
            try:
                new_text, count = re.subn(query, replacement, text,
                                          flags=self.get_re_flags())
            except re.error:
                self.match_label.setText("bad regex")
                return
        else:
            flags   = 0 if self.case_checkbox.isChecked() else re.IGNORECASE
            escaped = re.escape(query)
            if self.word_checkbox.isChecked():
                escaped = r"\b" + escaped + r"\b"
            new_text, count = re.subn(escaped, re.escape(replacement)
                                      .replace(r"\\", r"\\"),
                                      text, flags=flags)
            # Use literal replacement for non-regex
            new_text, count = re.subn(escaped, lambda m: replacement,
                                      text, flags=flags)
        if count:
            cursor = editor.textCursor()
            cursor.beginEditBlock()
            cursor.select(QTextCursor.SelectionType.Document)
            cursor.insertText(new_text)
            cursor.endEditBlock()
            self.match_label.setText(f"{count} replaced")
            self.set_find_state("match")
        else:
            self.match_label.setText("no match")
            self.set_find_state("no_match")

    def focus_find(self):
        self.find_input.selectAll()
        self.find_input.setFocus()

    # ── Cleanup ───────────────────────────────────────────────────────────

    def closeEvent(self, event):
        try:
            theme_signals.theme_changed.disconnect(self._on_theme_changed)
        except RuntimeError:
            pass
        super().closeEvent(event)