import subprocess
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QPushButton, QHBoxLayout
from PyQt6.QtGui import QFont, QColor, QTextCharFormat, QTextCursor
from PyQt6.QtCore import Qt, QDir

from ui.theme import get_theme


class DiffViewerDialog(QDialog):
    def __init__(self, file_path, repo_path=None, parent=None):
        super().__init__(parent)
        self.file_path = file_path
        self.repo_path = repo_path
        self.setWindowTitle(f"Git Diff: {file_path}")
        self.resize(800, 600)

        # Get theme from parent window if available
        theme_name = None
        if parent and hasattr(parent, 'settings_manager'):
            theme_name = parent.settings_manager.get('theme')
        elif (parent and hasattr(parent, 'parent_window') and
              hasattr(parent.parent_window, 'settings_manager')):
            theme_name = parent.parent_window.settings_manager.get('theme')
        self._t = get_theme(theme_name)

        self.setup_ui()
        self.load_diff()

    def setup_ui(self):
        t = self._t
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {t['bg1']};
                color: {t['fg1']};
            }}
            QPushButton {{
                background-color: {t['bg2']};
                color: {t['fg1']};
                border-radius: 4px;
                padding: 6px 16px;
                font-family: 'Inter', sans-serif;
                font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {t['bg3']}; }}
        """)

        layout = QVBoxLayout(self)

        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setFont(QFont("JetBrains Mono", 10))
        self.text_edit.setStyleSheet(f"""
            QTextEdit {{
                background-color: {t['bg0_hard']};
                color: {t['fg1']};
                border: 1px solid {t['border']};
                border-radius: 4px;
                padding: 5px;
            }}
        """)
        self.text_edit.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)

        btn_layout = QHBoxLayout()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_layout.addStretch()
        btn_layout.addWidget(close_btn)

        layout.addWidget(self.text_edit)
        layout.addLayout(btn_layout)

    def load_diff(self):
        try:
            result = subprocess.run(
                ['git', 'diff', 'HEAD', '--', self.file_path],
                cwd=self.repo_path if self.repo_path else QDir.currentPath(),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                check=True
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

    def format_diff(self, diff_text):
        t = self._t
        self.text_edit.clear()
        cursor = self.text_edit.textCursor()

        format_add = QTextCharFormat()
        format_add.setBackground(QColor(t['green_dim']))
        format_add.setForeground(QColor(t['green']))

        format_rem = QTextCharFormat()
        format_rem.setBackground(QColor(t['red_dim']))
        format_rem.setForeground(QColor(t['red']))

        format_hunk = QTextCharFormat()
        format_hunk.setForeground(QColor(t['blue']))

        format_header = QTextCharFormat()
        format_header.setForeground(QColor(t['yellow']))

        format_normal = QTextCharFormat()
        format_normal.setForeground(QColor(t['fg1']))

        for line in diff_text.split('\n'):
            if line.startswith('+') and not line.startswith('+++'):
                cursor.setCharFormat(format_add)
            elif line.startswith('-') and not line.startswith('---'):
                cursor.setCharFormat(format_rem)
            elif line.startswith('@@'):
                cursor.setCharFormat(format_hunk)
            elif line.startswith(('---', '+++', 'diff', 'index')):
                cursor.setCharFormat(format_header)
            else:
                cursor.setCharFormat(format_normal)

            cursor.insertText(line + '\n')

        cursor.movePosition(QTextCursor.MoveOperation.Start)
        self.text_edit.setTextCursor(cursor)