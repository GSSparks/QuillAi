from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, 
                             QPushButton, QCheckBox)
from PyQt6.QtGui import QTextDocument, QTextCursor
from PyQt6.QtCore import Qt

class FindReplaceWidget(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.setup_ui()

    def setup_ui(self):
        self.setStyleSheet("""
            QWidget {
                background-color: #252526;
                color: #CCCCCC;
                font-family: 'Inter', 'SF Pro Text', 'Segoe UI', sans-serif;
                font-size: 10pt;
            }
            QLineEdit {
                background-color: #3C3C3C;
                color: #FFFFFF;
                border: 1px solid #3E3E42;
                border-radius: 4px;
                padding: 4px 8px;
            }
            QLineEdit:focus { border: 1px solid #0E639C; }
            QLineEdit[state="match"] {
                background-color: #1A3D1A;
                border: 1px solid #4CAF50;
                color: #FFFFFF;
            }
            QLineEdit[state="no_match"] {
                background-color: #3D1A1A;
                border: 1px solid #F44336;
                color: #FFFFFF;
            }
            QPushButton {
                background-color: #3E3E42;
                color: white;
                border-radius: 4px;
                padding: 4px 12px;
                border: none;
            }
            QPushButton:hover { background-color: #4E4E52; }
            QPushButton:pressed { background-color: #0E639C; }
            QPushButton#closeBtn {
                background-color: transparent;
                font-weight: bold;
                padding: 4px 8px;
            }
            QPushButton#closeBtn:hover { background-color: #F44336; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        # --- Row 1: Find ---
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
        self.match_label.setStyleSheet("QPushButton { color: #888888; background: transparent; border: none; padding: 0 4px; min-width: 60px; }")

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

        # --- Row 2: Replace ---
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

    def set_find_state(self, state):
        """Sets the visual state of the find input: 'match', 'no_match', or '' (neutral)."""
        self.find_input.setProperty("state", state)
        # Force Qt to re-evaluate the stylesheet for this widget
        self.find_input.style().unpolish(self.find_input)
        self.find_input.style().polish(self.find_input)

    def count_matches(self, query):
        """Counts all occurrences of query in the current editor without moving the cursor."""
        editor = self.main_window.current_editor()
        if not editor or not query:
            return 0

        options = self.get_search_options()
        document = editor.document()
        count = 0
        cursor = QTextCursor(document)

        while True:
            cursor = document.find(query, cursor, options) if options else document.find(query, cursor)
            if cursor.isNull():
                break
            count += 1

        return count

    def on_search_text_changed(self):
        query = self.find_input.text()

        if not query:
            self.set_find_state("")
            self.match_label.setText("")
            # Clear any active selection in the editor without jumping
            editor = self.main_window.current_editor()
            if editor:
                cursor = editor.textCursor()
                cursor.clearSelection()
                editor.setTextCursor(cursor)
            return

        # Jump to the first match from the current position
        editor = self.main_window.current_editor()
        if not editor:
            return

        # Save position, try to find forward, wrap if needed
        saved_cursor = editor.textCursor()
        options = self.get_search_options()
        found = editor.find(query, options) if options else editor.find(query)

        if not found:
            # Try from the top before declaring no match
            top_cursor = QTextCursor(editor.document())
            editor.setTextCursor(top_cursor)
            found = editor.find(query, options) if options else editor.find(query)

        if found:
            total = self.count_matches(query)
            self.match_label.setText(f"{total} found")
            self.set_find_state("match")
        else:
            # Restore cursor position so the user's place isn't lost
            editor.setTextCursor(saved_cursor)
            self.match_label.setText("no match")
            self.set_find_state("no_match")

    # --- Search Engine Logic ---
    def get_search_options(self, backward=False):
        options = None
        if self.case_checkbox.isChecked():
            options = QTextDocument.FindFlag.FindCaseSensitively
        if self.word_checkbox.isChecked():
            options = options | QTextDocument.FindFlag.FindWholeWords if options else QTextDocument.FindFlag.FindWholeWords
        if backward:
            options = options | QTextDocument.FindFlag.FindBackward if options else QTextDocument.FindFlag.FindBackward
        return options

    def do_find(self, backward=False):
        editor = self.main_window.current_editor()
        if not editor: return False

        query = self.find_input.text()
        if not query: return False

        options = self.get_search_options(backward)
        found = editor.find(query, options) if options is not None else editor.find(query)

        if not found:
            cursor = editor.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End if backward else QTextCursor.MoveOperation.Start)
            editor.setTextCursor(cursor)
            found = editor.find(query, options) if options is not None else editor.find(query)

        return found

    def find_next(self):
        self.do_find(backward=False)

    def find_prev(self):
        self.do_find(backward=True)

    def replace(self):
        editor = self.main_window.current_editor()
        if not editor: return

        cursor = editor.textCursor()
        if cursor.hasSelection():
            cursor.insertText(self.replace_input.text())

        self.find_next()
        # Refresh the match count after a replacement
        self.on_search_text_changed()

    def replace_all(self):
        editor = self.main_window.current_editor()
        if not editor: return

        query = self.find_input.text()
        if not query: return

        cursor = editor.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        editor.setTextCursor(cursor)

        count = 0
        options = self.get_search_options()

        cursor.beginEditBlock()
        while True:
            found = editor.find(query, options) if options is not None else editor.find(query)
            if not found:
                break
            editor.textCursor().insertText(self.replace_input.text())
            count += 1
        cursor.endEditBlock()

        if count > 0:
            self.main_window.statusBar().showMessage(f"Replaced {count} occurrences.", 4000)

        # Refresh state after replacing everything
        self.on_search_text_changed()

    def focus_find(self):
        self.find_input.selectAll()
        self.find_input.setFocus()