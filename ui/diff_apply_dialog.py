from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
                             QLabel, QTextEdit, QSplitter, QWidget)
from PyQt6.QtGui import QTextCursor, QTextCharFormat, QColor, QFont
from PyQt6.QtCore import Qt
import difflib

from ui.theme import get_theme


class DiffApplyDialog(QDialog):
    def __init__(self, original: str, proposed: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Review AI Changes")
        self.setMinimumSize(900, 500)
        self.accepted_code = None
        self.original = original
        self.proposed = proposed

        # Get theme from parent window if available
        theme_name = None
        if parent and hasattr(parent, 'settings_manager'):
            theme_name = parent.settings_manager.get('theme')
        self._t = get_theme(theme_name)

        self._apply_style()
        self.setup_ui()
        self.populate()

    def _apply_style(self):
        t = self._t
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {t['bg0']};
                color: {t['fg1']};
            }}
            QLabel {{
                color: {t['fg4']};
                font-family: 'Inter', sans-serif;
                font-size: 9pt;
                padding: 4px 8px;
                background-color: {t['bg1']};
            }}
            QPushButton {{
                border-radius: 4px;
                padding: 6px 20px;
                font-weight: bold;
                font-family: 'Inter', sans-serif;
                border: none;
            }}
        """)

    def setup_ui(self):
        t = self._t

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 12)
        layout.setSpacing(0)

        # Splitter with two panes
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(2)
        splitter.setStyleSheet(
            f"QSplitter::handle {{ background-color: {t['border']}; }}"
        )

        # Left — original
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        left_label = QLabel("  Original")
        left_label.setStyleSheet(
            f"background-color: {t['bg1']}; color: {t['red']}; "
            f"font-weight: bold; font-size: 9pt; padding: 4px 8px;"
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
            f"background-color: {t['bg1']}; color: {t['green']}; "
            f"font-weight: bold; font-size: 9pt; padding: 4px 8px;"
        )
        self.proposed_view = self._make_view()
        right_layout.addWidget(right_label)
        right_layout.addWidget(self.proposed_view)
        splitter.addWidget(right)

        splitter.setSizes([450, 450])
        layout.addWidget(splitter)

        # Sync scrolling
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
            f"color: {t['fg4']}; font-size: 9pt; "
            f"background: transparent; padding: 0;"
        )

        discard_btn = QPushButton("✕  Discard")
        discard_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {t['bg2']};
                color: {t['fg1']};
            }}
            QPushButton:hover {{
                background-color: {t['red']};
                color: {t['bg0_hard']};
            }}
        """)
        discard_btn.clicked.connect(self.reject)

        accept_btn = QPushButton("✓  Accept")
        accept_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {t['accent']};
                color: {t['bg0_hard']};
            }}
            QPushButton:hover {{ background-color: {t['yellow']}; }}
        """)
        accept_btn.clicked.connect(self._accept)

        btn_layout.addWidget(hint)
        btn_layout.addStretch()
        btn_layout.addWidget(discard_btn)
        btn_layout.addWidget(accept_btn)
        layout.addLayout(btn_layout)

    def _make_view(self):
        t = self._t
        view = QTextEdit()
        view.setReadOnly(True)
        view.setFont(QFont("JetBrains Mono", 10))
        view.setStyleSheet(f"""
            QTextEdit {{
                background-color: {t['bg0_hard']};
                color: {t['fg1']};
                border: none;
                padding: 8px;
            }}
        """)
        view.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        return view

    def populate(self):
        t = self._t

        orig_lines = self.original.splitlines(keepends=True)
        prop_lines = self.proposed.splitlines(keepends=True)
        matcher = difflib.SequenceMatcher(None, orig_lines, prop_lines)

        removed_fmt = QTextCharFormat()
        removed_fmt.setBackground(QColor(t['red_dim']))
        removed_fmt.setForeground(QColor(t['red']))

        added_fmt = QTextCharFormat()
        added_fmt.setBackground(QColor(t['green_dim']))
        added_fmt.setForeground(QColor(t['green']))

        neutral_fmt = QTextCharFormat()
        neutral_fmt.setBackground(QColor(t['bg0_hard']))
        neutral_fmt.setForeground(QColor(t['fg1']))

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
                for _ in orig_lines[i1:i2]:
                    prop_cursor.setCharFormat(neutral_fmt)
                    prop_cursor.insertText("\n")

            elif tag == 'insert':
                for _ in prop_lines[j1:j2]:
                    orig_cursor.setCharFormat(neutral_fmt)
                    orig_cursor.insertText("\n")
                for line in prop_lines[j1:j2]:
                    prop_cursor.setCharFormat(added_fmt)
                    prop_cursor.insertText(line)

        self.original_view.verticalScrollBar().setValue(0)
        self.proposed_view.verticalScrollBar().setValue(0)

    def _accept(self):
        self.accepted_code = self.proposed
        self.accept()