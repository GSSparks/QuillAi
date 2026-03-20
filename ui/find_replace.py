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
        # Match QuillAI's deep, modern styling
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

        self.case_checkbox = QCheckBox("Aa")
        self.case_checkbox.setToolTip("Match Case")
        self.word_checkbox = QCheckBox("ab|")
        self.word_checkbox.setToolTip("Match Whole Word")

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
            # Wrap around to the start/end of the document if we hit the limit
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

    def replace_all(self):
        editor = self.main_window.current_editor()
        if not editor: return

        query = self.find_input.text()
        if not query: return

        # Reset cursor to the top
        cursor = editor.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        editor.setTextCursor(cursor)

        count = 0
        options = self.get_search_options()
        
        # Group operations into one block so a single 'Undo' reverts all replacements
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

    def focus_find(self):
        self.find_input.selectAll()
        self.find_input.setFocus()