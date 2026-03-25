from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
                             QLabel, QTextEdit, QSplitter, QWidget)
from PyQt6.QtGui import QTextCursor, QTextCharFormat, QColor, QFont
from PyQt6.QtCore import Qt
import difflib


class DiffApplyDialog(QDialog):
    def __init__(self, original: str, proposed: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Review AI Changes")
        self.setMinimumSize(900, 500)
        self.accepted_code = None
        self.setStyleSheet("""
            QDialog { background-color: #1E1E1E; color: #D4D4D4; }
            QLabel {
                color: #888888;
                font-family: 'Inter', sans-serif;
                font-size: 9pt;
                padding: 4px 8px;
                background-color: #252526;
            }
            QPushButton {
                border-radius: 4px;
                padding: 6px 20px;
                font-weight: bold;
                font-family: 'Inter', sans-serif;
                border: none;
            }
        """)
        self.original = original
        self.proposed = proposed
        self.setup_ui()
        self.populate()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 12)
        layout.setSpacing(0)

        # Splitter with two panes
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(2)
        splitter.setStyleSheet("QSplitter::handle { background-color: #3E3E42; }")

        # Left — original
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)
        left_label = QLabel("  Original")
        left_label.setStyleSheet(
            "background-color: #3D1A1A; color: #F44336; "
            "font-weight: bold; font-size: 9pt; padding: 4px 8px;"
        )
        self.original_view = self._make_view()
        left_layout.addWidget(left_label)
        left_layout.addWidget(self.original_view)
        splitter.addWidget(left)

        # Right — proposed
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        right_label = QLabel("  AI Rewrite")
        right_label.setStyleSheet(
            "background-color: #1A3D1A; color: #4CAF50; "
            "font-weight: bold; font-size: 9pt; padding: 4px 8px;"
        )
        self.proposed_view = self._make_view()
        right_layout.addWidget(right_label)
        right_layout.addWidget(self.proposed_view)
        splitter.addWidget(right)

        splitter.setSizes([450, 450])
        layout.addWidget(splitter)

        # Sync scrolling between panes
        self.original_view.verticalScrollBar().valueChanged.connect(
            self.proposed_view.verticalScrollBar().setValue
        )
        self.proposed_view.verticalScrollBar().valueChanged.connect(
            self.original_view.verticalScrollBar().setValue
        )

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(12, 8, 12, 0)

        hint = QLabel("Review the changes above then accept or discard.")
        hint.setStyleSheet(
            "color: #555; font-size: 9pt; background: transparent; padding: 0;"
        )

        discard_btn = QPushButton("✕  Discard")
        discard_btn.setStyleSheet(
            "QPushButton { background-color: #3E3E42; color: #CCCCCC; }"
            "QPushButton:hover { background-color: #F44336; color: white; }"
        )
        discard_btn.clicked.connect(self.reject)

        accept_btn = QPushButton("✓  Accept")
        accept_btn.setStyleSheet(
            "QPushButton { background-color: #0E639C; color: white; }"
            "QPushButton:hover { background-color: #1177BB; }"
        )
        accept_btn.clicked.connect(self._accept)

        btn_layout.addWidget(hint)
        btn_layout.addStretch()
        btn_layout.addWidget(discard_btn)
        btn_layout.addWidget(accept_btn)
        layout.addLayout(btn_layout)

    def _make_view(self):
        view = QTextEdit()
        view.setReadOnly(True)
        view.setFont(QFont("JetBrains Mono", 10))
        view.setStyleSheet("""
            QTextEdit {
                background-color: #1E1E1E;
                color: #D4D4D4;
                border: none;
                padding: 8px;
            }
        """)
        view.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        return view

    def populate(self):
        orig_lines = self.original.splitlines(keepends=True)
        prop_lines = self.proposed.splitlines(keepends=True)
        matcher = difflib.SequenceMatcher(None, orig_lines, prop_lines)

        # Formats
        removed_fmt = QTextCharFormat()
        removed_fmt.setBackground(QColor("#3D1A1A"))
        removed_fmt.setForeground(QColor("#F88070"))

        added_fmt = QTextCharFormat()
        added_fmt.setBackground(QColor("#1A3D1A"))
        added_fmt.setForeground(QColor("#80C880"))

        neutral_fmt = QTextCharFormat()
        neutral_fmt.setBackground(QColor("#1E1E1E"))
        neutral_fmt.setForeground(QColor("#D4D4D4"))

        orig_cursor = self.original_view.textCursor()
        prop_cursor = self.proposed_view.textCursor()

        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'equal':
                for line in orig_lines[i1:i2]:
                    orig_cursor.setCharFormat(neutral_fmt)
                    orig_cursor.insertText(line)
                for line in prop_lines[j1:j2]:
                    prop_cursor.setCharFormat(neutral_fmt)
                    prop_cursor.insertText(line)

            elif tag == 'replace':
                for line in orig_lines[i1:i2]:
                    orig_cursor.setCharFormat(removed_fmt)
                    orig_cursor.insertText(line)
                # Pad proposed side to keep lines aligned
                pad = len(orig_lines[i1:i2]) - len(prop_lines[j1:j2])
                for line in prop_lines[j1:j2]:
                    prop_cursor.setCharFormat(added_fmt)
                    prop_cursor.insertText(line)
                for _ in range(max(0, pad)):
                    prop_cursor.setCharFormat(neutral_fmt)
                    prop_cursor.insertText("\n")

            elif tag == 'delete':
                for line in orig_lines[i1:i2]:
                    orig_cursor.setCharFormat(removed_fmt)
                    orig_cursor.insertText(line)
                # Pad proposed side
                for _ in orig_lines[i1:i2]:
                    prop_cursor.setCharFormat(neutral_fmt)
                    prop_cursor.insertText("\n")

            elif tag == 'insert':
                # Pad original side
                for _ in prop_lines[j1:j2]:
                    orig_cursor.setCharFormat(neutral_fmt)
                    orig_cursor.insertText("\n")
                for line in prop_lines[j1:j2]:
                    prop_cursor.setCharFormat(added_fmt)
                    prop_cursor.insertText(line)

        # Scroll both to top
        self.original_view.verticalScrollBar().setValue(0)
        self.proposed_view.verticalScrollBar().setValue(0)

    def _accept(self):
        self.accepted_code = self.proposed
        self.accept()