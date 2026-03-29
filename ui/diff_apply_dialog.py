import difflib
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
                             QLabel, QTextEdit, QSplitter, QWidget)
from PyQt6.QtGui import QTextCursor, QTextCharFormat, QColor, QFont
from PyQt6.QtCore import Qt

from ui.theme import (get_theme, theme_signals,
                      build_diff_apply_dialog_stylesheet,
                      build_diff_apply_parts,
                      QFONT_CODE)


class DiffApplyDialog(QDialog):
    def __init__(self, original: str, proposed: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Review AI Changes")
        self.setMinimumSize(900, 500)
        self.accepted_code = None
        self.original  = original
        self.proposed  = proposed

        self._t = get_theme()
        self._setup_ui()
        self.apply_styles(self._t)
        self.populate()

        theme_signals.theme_changed.connect(self._on_theme_changed)

    # ── Theme handling ────────────────────────────────────────────────────

    def _on_theme_changed(self, t: dict):
        self._t = t
        self.apply_styles(t)
        # Re-render the diff with updated foreground colors
        self.original_view.clear()
        self.proposed_view.clear()
        self.populate()

    def apply_styles(self, t: dict):
        p = build_diff_apply_parts(t)
        self.setStyleSheet(build_diff_apply_dialog_stylesheet(t))
        self._splitter.setStyleSheet(p["splitter_handle"])
        self._left_label.setStyleSheet(p["left_label"])
        self._right_label.setStyleSheet(p["right_label"])
        self.original_view.setStyleSheet(p["text_view"])
        self.proposed_view.setStyleSheet(p["text_view"])
        self._hint.setStyleSheet(p["hint"])
        self._discard_btn.setStyleSheet(p["discard_btn"])
        self._accept_btn.setStyleSheet(p["accept_btn"])

    # ── UI Setup ──────────────────────────────────────────────────────────

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 12)
        layout.setSpacing(0)

        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setHandleWidth(2)

        # Left — original
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)
        self._left_label = QLabel("  Original")
        self.original_view = self._make_view()
        left_layout.addWidget(self._left_label)
        left_layout.addWidget(self.original_view)
        self._splitter.addWidget(left)

        # Right — proposed
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        self._right_label = QLabel("  AI Rewrite")
        self.proposed_view = self._make_view()
        right_layout.addWidget(self._right_label)
        right_layout.addWidget(self.proposed_view)
        self._splitter.addWidget(right)

        self._splitter.setSizes([450, 450])
        layout.addWidget(self._splitter)

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

        self._hint = QLabel("Review the changes above then accept or discard.")

        self._discard_btn = QPushButton("✕  Discard")
        self._discard_btn.clicked.connect(self.reject)

        self._accept_btn = QPushButton("✓  Accept")
        self._accept_btn.clicked.connect(self._accept)

        btn_layout.addWidget(self._hint)
        btn_layout.addStretch()
        btn_layout.addWidget(self._discard_btn)
        btn_layout.addWidget(self._accept_btn)
        layout.addLayout(btn_layout)

    @staticmethod
    def _make_view() -> QTextEdit:
        view = QTextEdit()
        view.setReadOnly(True)
        view.setFont(QFont(QFONT_CODE, 10))
        view.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        return view

    # ── Diff rendering ────────────────────────────────────────────────────

    def populate(self):
        p = build_diff_apply_parts(self._t)

        removed_fmt = QTextCharFormat()
        removed_fmt.setForeground(QColor(p["diff_removed"]))

        added_fmt = QTextCharFormat()
        added_fmt.setForeground(QColor(p["diff_added"]))

        neutral_fmt = QTextCharFormat()
        neutral_fmt.setForeground(QColor(p["diff_neutral"]))

        orig_lines = self.original.splitlines(keepends=True)
        prop_lines = self.proposed.splitlines(keepends=True)
        matcher    = difflib.SequenceMatcher(None, orig_lines, prop_lines)

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

    # ── Actions ───────────────────────────────────────────────────────────

    def _accept(self):
        self.accepted_code = self.proposed
        self.accept()

    # ── Cleanup ───────────────────────────────────────────────────────────

    def closeEvent(self, event):
        try:
            theme_signals.theme_changed.disconnect(self._on_theme_changed)
        except RuntimeError:
            pass
        super().closeEvent(event)