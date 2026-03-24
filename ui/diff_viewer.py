import subprocess
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QPushButton, QHBoxLayout
from PyQt6.QtGui import QFont, QColor, QTextCharFormat, QTextCursor
from PyQt6.QtCore import Qt

class DiffViewerDialog(QDialog):
    def __init__(self, file_path, parent=None):
        super().__init__(parent)
        self.file_path = file_path
        self.repo_path = repo_path
        self.setWindowTitle(f"Git Diff: {file_path}")
        self.resize(800, 600)
        self.setup_ui()
        self.load_diff()

    def setup_ui(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #252526;
                color: #CCCCCC;
            }
            QPushButton {
                background-color: #3E3E42;
                color: white;
                border-radius: 4px;
                padding: 6px 16px;
                font-family: 'Inter', sans-serif;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #4E4E52; }
        """)

        layout = QVBoxLayout(self)
        
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setFont(QFont("JetBrains Mono", 10))
        self.text_edit.setStyleSheet("""
            QTextEdit {
                background-color: #1E1E1E; 
                color: #CCCCCC; 
                border: 1px solid #3E3E42;
                border-radius: 4px;
                padding: 5px;
            }
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
            # Run git diff against the last commit (HEAD)
            result = subprocess.run(
                ['git', 'diff', 'HEAD', '--', self.file_path],
                cwd=self.repo_path if self.repo_path else QDir.currentPath(),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True
            )
            diff_text = result.stdout
            
            if not diff_text:
                self.text_edit.setPlainText("No differences found, or the file is untracked (new).\nTo view untracked files, open them directly in the editor.")
                return
            
            self.format_diff(diff_text)
            
        except subprocess.CalledProcessError as e:
            self.text_edit.setPlainText(f"Error loading diff: {e.stderr}")
        except FileNotFoundError:
            self.text_edit.setPlainText("Git is not installed or found in PATH.")

    def format_diff(self, diff_text):
        self.text_edit.clear()
        cursor = self.text_edit.textCursor()
        
        # Define our color formats
        format_add = QTextCharFormat()
        format_add.setBackground(QColor(35, 75, 35)) # Dark green background
        format_add.setForeground(QColor("#4CAF50"))  # Bright green text
        
        format_rem = QTextCharFormat()
        format_rem.setBackground(QColor(81, 35, 35)) # Dark red background
        format_rem.setForeground(QColor("#F44336"))  # Bright red text
        
        format_hunk = QTextCharFormat()
        format_hunk.setForeground(QColor("#569CD6")) # Cyan for line numbers (@@ -1,4 +1,5 @@)
        
        format_normal = QTextCharFormat()
        format_normal.setForeground(QColor("#CCCCCC"))

        for line in diff_text.split('\n'):
            if line.startswith('+') and not line.startswith('+++'):
                cursor.setCharFormat(format_add)
            elif line.startswith('-') and not line.startswith('---'):
                cursor.setCharFormat(format_rem)
            elif line.startswith('@@'):
                cursor.setCharFormat(format_hunk)
            else:
                cursor.setCharFormat(format_normal)
                
            cursor.insertText(line + '\n')
            
        # Scroll to top
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        self.text_edit.setTextCursor(cursor)