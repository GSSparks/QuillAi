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

    def get_search_options(self, backward=False):
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

    # ── Find / replace actions ────────────────────────────────────────────

    def do_find(self, backward=False) -> bool:
        editor = self.main_window.current_editor()
        if not editor:
            return False
        query = self.find_input.text()
        if not query:
            return False

        options = self.get_search_options(backward)
        found = (editor.find(query, options)
                 if options is not None else editor.find(query))

        if not found:
            cursor = editor.textCursor()
            cursor.movePosition(
                QTextCursor.MoveOperation.End
                if backward else QTextCursor.MoveOperation.Start
            )
            editor.setTextCursor(cursor)
            found = (editor.find(query, options)
                     if options is not None else editor.find(query))
        return found

    def find_next(self):
        self.do_find(backward=False)

    def find_prev(self):
        self.do_find(backward=True)

    def replace(self):
        editor = self.main_window.current_editor()
        if not editor:
            return
        cursor = editor.textCursor()
        if cursor.hasSelection():
            cursor.insertText(self.replace_input.text())
        self.find_next()
        self.on_search_text_changed()

    def replace_all(self):
        editor = self.main_window.current_editor()
        if not editor:
            return
        query = self.find_input.text()
        if not query:
            return

        cursor = editor.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        editor.setTextCursor(cursor)

        count = 0
        options = self.get_search_options()

        cursor.beginEditBlock()
        while True:
            found = (editor.find(query, options)
                     if options is not None else editor.find(query))
            if not found:
                break
            editor.textCursor().insertText(self.replace_input.text())
            count += 1
        cursor.endEditBlock()

        if count > 0:
            self.main_window.statusBar().showMessage(
                f"Replaced {count} occurrences.", 4000
            )
        self.on_search_text_changed()

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