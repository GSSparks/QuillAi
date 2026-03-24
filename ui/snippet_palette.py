import json
import os
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLineEdit,
                             QPushButton, QListWidget, QListWidgetItem,
                             QLabel, QSplitter, QPlainTextEdit, QWidget)
from PyQt6.QtCore import Qt, pyqtSignal, QEvent
from PyQt6.QtGui import QColor, QKeySequence, QShortcut

CATEGORY_COLORS = {
    "Python":  "#4B8BBE",
    "Ansible": "#EE0000",
    "Nix":     "#7EBAE4",
    "Bash":    "#4CAF50",
    "General": "#888888",
}

DEFAULT_SNIPPETS = [
    # Python
    {"name": "for loop",            "category": "Python",  "code": "for i in range():\n    pass"},
    {"name": "if statement",        "category": "Python",  "code": "if condition:\n    pass"},
    {"name": "def function",        "category": "Python",  "code": "def function_name(arg):\n    \"\"\"Docstring.\"\"\"\n    pass"},
    {"name": "class definition",    "category": "Python",  "code": "class ClassName:\n    def __init__(self):\n        pass"},
    {"name": "try/except",          "category": "Python",  "code": "try:\n    pass\nexcept Exception as e:\n    print(e)"},
    {"name": "main block",          "category": "Python",  "code": "if __name__ == '__main__':\n    main()"},
    {"name": "list comprehension",  "category": "Python",  "code": "[x for x in items if condition]"},
    {"name": "dict comprehension",  "category": "Python",  "code": "{k: v for k, v in items.items()}"},
    {"name": "with open (read)",    "category": "Python",  "code": "with open('filename.txt', 'r', encoding='utf-8') as f:\n    content = f.read()"},
    {"name": "with open (write)",   "category": "Python",  "code": "with open('filename.txt', 'w', encoding='utf-8') as f:\n    f.write(content)"},
    {"name": "dataclass",           "category": "Python",  "code": "from dataclasses import dataclass\n\n@dataclass\nclass MyClass:\n    field: str\n    value: int = 0"},
    {"name": "argparse",            "category": "Python",  "code": "import argparse\n\nparser = argparse.ArgumentParser(description='')\nparser.add_argument('--foo', type=str, help='')\nargs = parser.parse_args()"},
    # Ansible
    {"name": "ansible task",        "category": "Ansible", "code": "- name: Task Name\n  ansible.builtin.module:\n    key: value"},
    {"name": "ansible apt",         "category": "Ansible", "code": "- name: Install package\n  apt:\n    name: package_name\n    state: present"},
    {"name": "ansible template",    "category": "Ansible", "code": "- name: Deploy template\n  ansible.builtin.template:\n    src: template.j2\n    dest: /etc/app/config\n    owner: root\n    mode: '0644'"},
    {"name": "ansible loop",        "category": "Ansible", "code": "- name: Task with loop\n  ansible.builtin.debug:\n    msg: \"{{ item }}\"\n  loop:\n    - value1\n    - value2"},
    # Nix
    {"name": "nix flake",           "category": "Nix",     "code": "{\n  description = \"\";\n\n  inputs = {\n    nixpkgs.url = \"github:NixOS/nixpkgs/nixos-unstable\";\n  };\n\n  outputs = { self, nixpkgs }:\n    let\n      system = \"x86_64-linux\";\n      pkgs = nixpkgs.legacyPackages.${system};\n    in\n    {\n      # Config here\n    };\n}"},
    {"name": "nix package",         "category": "Nix",     "code": "environment.systemPackages = with pkgs; [\n  \n];"},
    {"name": "nix shell",           "category": "Nix",     "code": "{ pkgs ? import <nixpkgs> {} }:\npkgs.mkShell {\n  buildInputs = with pkgs; [\n    python3\n  ];\n}"},
    # Bash
    {"name": "bash shebang",        "category": "Bash",    "code": "#!/usr/bin/env bash\nset -euo pipefail\n"},
    {"name": "bash for loop",       "category": "Bash",    "code": "for item in \"${array[@]}\"; do\n    echo \"$item\"\ndone"},
    {"name": "bash if file exists", "category": "Bash",    "code": "if [[ -f \"$FILE\" ]]; then\n    echo \"exists\"\nfi"},
    {"name": "bash function",       "category": "Bash",    "code": "my_function() {\n    local arg=\"$1\"\n    echo \"$arg\"\n}"},
]

SNIPPETS_FILE = os.path.join(os.path.expanduser("~"), ".config", "quillai", "snippets.json")


class SnippetPalette(QDialog):
    snippet_selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Insert Snippet")
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.resize(640, 380)
        self.snippets = self._load_snippets()
        self.filtered = list(self.snippets)
        self.setup_ui()
        self._populate(self.filtered)
        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)
            self._update_preview(0)

    def _load_snippets(self):
        if os.path.exists(SNIPPETS_FILE):
            try:
                with open(SNIPPETS_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return DEFAULT_SNIPPETS

    def save_snippets(self):
        os.makedirs(os.path.dirname(SNIPPETS_FILE), exist_ok=True)
        with open(SNIPPETS_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.snippets, f, indent=2)

    def setup_ui(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #252526;
                border: 1px solid #3E3E42;
                border-radius: 8px;
            }
            QLineEdit {
                background-color: #1E1E1E;
                color: #FFFFFF;
                border: none;
                border-bottom: 1px solid #3E3E42;
                border-radius: 0;
                padding: 10px 14px;
                font-family: 'Inter', 'Segoe UI', sans-serif;
                font-size: 13pt;
            }
            QListWidget {
                background-color: #252526;
                color: #CCCCCC;
                border: none;
                outline: none;
                font-family: 'Inter', 'Segoe UI', sans-serif;
                font-size: 10pt;
            }
            QListWidget::item {
                padding: 6px 12px;
                border-radius: 0;
            }
            QListWidget::item:selected {
                background-color: #37373D;
                color: #FFFFFF;
            }
            QListWidget::item:hover:!selected {
                background-color: #2A2D2E;
            }
            QPlainTextEdit {
                background-color: #1E1E1E;
                color: #D4D4D4;
                border: none;
                font-family: 'JetBrains Mono', 'Hack', monospace;
                font-size: 10pt;
                padding: 10px;
            }
            QPushButton {
                border-radius: 4px;
                padding: 5px 16px;
                font-family: 'Inter', 'Segoe UI', sans-serif;
                font-weight: bold;
                font-size: 10pt;
                border: none;
            }
            QLabel {
                color: #888888;
                font-family: 'Inter', 'Segoe UI', sans-serif;
                font-size: 9pt;
                padding: 4px 12px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # --- Search Bar ---
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search snippets...")
        self.search_input.textChanged.connect(self._on_search)
        self.search_input.installEventFilter(self)
        layout.addWidget(self.search_input)

        # --- Splitter: list + preview ---
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setStyleSheet("QSplitter::handle { background-color: #3E3E42; }")

        # Left: snippet list
        self.list_widget = QListWidget()
        self.list_widget.currentRowChanged.connect(self._update_preview)
        self.list_widget.itemDoubleClicked.connect(self._insert)
        splitter.addWidget(self.list_widget)

        # Right: preview pane
        preview_container = QWidget()
        preview_container.setStyleSheet("background-color: #1E1E1E;")
        preview_layout = QVBoxLayout(preview_container)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(0)

        self.preview_header = QLabel("Select a snippet")
        self.preview_header.setStyleSheet("""
            QLabel {
                color: #CCCCCC;
                background-color: #252526;
                border-bottom: 1px solid #3E3E42;
                font-weight: bold;
                font-size: 10pt;
                padding: 6px 12px;
            }
        """)

        self.preview_edit = QPlainTextEdit()
        self.preview_edit.setReadOnly(True)
        self.preview_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

        preview_layout.addWidget(self.preview_header)
        preview_layout.addWidget(self.preview_edit)
        splitter.addWidget(preview_container)
        splitter.setSizes([220, 420])

        layout.addWidget(splitter)

        # --- Footer ---
        footer = QWidget()
        footer.setStyleSheet("background-color: #252526; border-top: 1px solid #3E3E42;")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(10, 6, 10, 6)

        hint = QLabel("↑↓ navigate · Enter insert · Esc close")
        hint.setStyleSheet("color: #555555; font-size: 9pt; padding: 0;")

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(
            "QPushButton { background-color: #3E3E42; color: #CCCCCC; }"
            "QPushButton:hover { background-color: #4E4E52; }"
        )
        cancel_btn.clicked.connect(self.reject)

        self.insert_btn = QPushButton("Insert")
        self.insert_btn.setStyleSheet(
            "QPushButton { background-color: #0E639C; color: white; }"
            "QPushButton:hover { background-color: #1177BB; }"
        )
        self.insert_btn.clicked.connect(self._insert)

        footer_layout.addWidget(hint)
        footer_layout.addStretch()
        footer_layout.addWidget(cancel_btn)
        footer_layout.addWidget(self.insert_btn)

        layout.addWidget(footer)

        QShortcut(QKeySequence("Return"), self, activated=self._insert)
        QShortcut(QKeySequence("Escape"), self, activated=self.reject)

    def _populate(self, snippets):
        self.list_widget.clear()
        for s in snippets:
            item = QListWidgetItem(s["name"])
            item.setForeground(QColor("#CCCCCC"))
            item.setToolTip(s["category"])
            item.setData(Qt.ItemDataRole.UserRole, s)
            self.list_widget.addItem(item)

    def _on_search(self, text):
        text = text.lower()
        self.filtered = [
            s for s in self.snippets
            if text in s["name"].lower() or text in s["category"].lower()
        ]
        self._populate(self.filtered)
        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)
            self._update_preview(0)
        else:
            self.preview_header.setText("No matches")
            self.preview_edit.clear()

    def _update_preview(self, row):
        if row < 0 or row >= self.list_widget.count():
            return
        item = self.list_widget.item(row)
        if not item:
            return
        data = item.data(Qt.ItemDataRole.UserRole)
        color = CATEGORY_COLORS.get(data["category"], "#888888")
        self.preview_header.setText(
            f'{data["name"]}  <span style="color:{color};font-weight:normal;font-size:9pt">'
            f'{data["category"]}</span>'
        )
        self.preview_header.setTextFormat(Qt.TextFormat.RichText)
        self.preview_edit.setPlainText(data["code"])

    def _insert(self):
        row = self.list_widget.currentRow()
        if row < 0:
            return
        item = self.list_widget.item(row)
        if item:
            data = item.data(Qt.ItemDataRole.UserRole)
            self.snippet_selected.emit(data["code"])
            self.accept()

    def eventFilter(self, obj, event):
        if obj == self.search_input and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key == Qt.Key.Key_Down:
                row = min(self.list_widget.currentRow() + 1, self.list_widget.count() - 1)
                self.list_widget.setCurrentRow(row)
                return True
            if key == Qt.Key.Key_Up:
                row = max(self.list_widget.currentRow() - 1, 0)
                self.list_widget.setCurrentRow(row)
                return True
        return super().eventFilter(obj, event)
