import subprocess
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QPushButton, QHBoxLayout
from PyQt6.QtGui import QFont, QColor, QTextCharFormat, QTextCursor
from PyQt6.QtCore import Qt, QDir

from ui.theme import get_theme, build_dialog_stylesheet, theme_signals


class DiffViewerDialog(QDialog):
    def __init__(self, file_path, repo_path=None, parent=None):
        super().__init__(parent)
        self.file_path = file_path
        self.repo_path = repo_path
        self.setWindowTitle(f"Git Diff: {file_path}")
        self.resize(800, 600)

        self._t = get_theme()
        self.setup_ui()
        self.load_diff()

        # Stay in sync if the user switches themes while this dialog is open
        theme_signals.theme_changed.connect(self._on_theme_changed)

    # ── Theme handling ────────────────────────────────────────────────────────

    def _on_theme_changed(self, t: dict):
        self._t = t
        self.apply_styles(t)
        self.load_diff()   # re-render diff text with updated palette colors

    def apply_styles(self, t: dict):
        self.setStyleSheet(build_dialog_stylesheet(t))

    # ── UI Setup ──────────────────────────────────────────────────────────────

    def setup_ui(self):
        self.apply_styles(self._t)

        layout = QVBoxLayout(self)

        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setFont(QFont("JetBrains Mono, monospace", 10))
        self.text_edit.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)

        btn_layout = QHBoxLayout()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_layout.addStretch()
        btn_layout.addWidget(close_btn)

        layout.addWidget(self.text_edit)
        layout.addLayout(btn_layout)

    # ── Diff Loading ──────────────────────────────────────────────────────────

    def load_diff(self):
        try:
            result = subprocess.run(
                ['git', 'diff', 'HEAD', '--', self.file_path],
                cwd=self.repo_path if self.repo_path else QDir.currentPath(),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                check=True,
            )
            diff_text = result.stdout

            if not diff_text:
                self.text_edit.setPlainText(
                    "No differences found, or the file is untracked (new).\n"
                    "To view untracked files, open them directly in the editor."
                )
                return

            self.format_diff(diff_text)

        except subprocess.CalledProcessError as e:
            self.text_edit.setPlainText(f"Error loading diff: {e.stderr}")
        except FileNotFoundError:
            self.text_edit.setPlainText("Git is not installed or found in PATH.")

    def format_diff(self, diff_text: str):
        t = self._t
        self.text_edit.clear()
        cursor = self.text_edit.textCursor()

        fmt_add    = self._fmt(t['green'])
        fmt_rem    = self._fmt(t['red'])
        fmt_hunk   = self._fmt(t['blue'])
        fmt_header = self._fmt(t['yellow'])
        fmt_normal = self._fmt(t['fg1'])

        for line in diff_text.split('\n'):
            if line.startswith('+') and not line.startswith('+++'):
                fmt = fmt_add
            elif line.startswith('-') and not line.startswith('---'):
                fmt = fmt_rem
            elif line.startswith('@@'):
                fmt = fmt_hunk
            elif line.startswith(('---', '+++', 'diff', 'index')):
                fmt = fmt_header
            else:
                fmt = fmt_normal

            cursor.setCharFormat(fmt)
            cursor.insertText(line + '\n')

        cursor.movePosition(QTextCursor.MoveOperation.Start)
        self.text_edit.setTextCursor(cursor)

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _fmt(color: str) -> QTextCharFormat:
        """Return a QTextCharFormat with the given foreground color."""
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        return fmt

    def closeEvent(self, event):
        # Disconnect so the signal doesn't fire after the dialog is gone
        try:
            theme_signals.theme_changed.disconnect(self._on_theme_changed)
        except RuntimeError:
            pass
        super().closeEvent(event)