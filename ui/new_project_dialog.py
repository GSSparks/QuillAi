import os
import re
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                              QLineEdit, QPushButton, QComboBox, QFileDialog,
                              QCheckBox, QMessageBox, QGroupBox)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from ui.theme import get_theme, theme_signals, build_new_project_dialog_stylesheet, QFONT_UI


PROJECT_TYPES = {
    "Python": {
        "files": {
            "main.py": '#!/usr/bin/env python3\n\n\ndef main():\n    pass\n\n\nif __name__ == "__main__":\n    main()\n',
            "README.md": "# {name}\n\nA Python project.\n\n## Installation\n\n```bash\npip install -r requirements.txt\n```\n\n## Usage\n\n```bash\npython main.py\n```\n",
            "requirements.txt": "",
            ".gitignore": "__pycache__/\n*.pyc\n*.pyo\n.venv/\nvenv/\n*.egg-info/\ndist/\nbuild/\n.env\n",
        },
        "open": "main.py",
    },
    "Python Package": {
        "files": {
            "{name}/__init__.py": '"""{name} package."""\n\n__version__ = "0.1.0"\n',
            "{name}/main.py": "def main():\n    pass\n",
            "tests/__init__.py": "",
            "tests/test_main.py": 'from {name}.main import main\n\n\ndef test_main():\n    assert main() is None\n',
            "README.md": "# {name}\n\n## Installation\n\n```bash\npip install -e .\n```\n",
            "requirements.txt": "",
            "setup.py": 'from setuptools import setup, find_packages\n\nsetup(\n    name="{name}",\n    version="0.1.0",\n    packages=find_packages(),\n)\n',
            ".gitignore": "__pycache__/\n*.pyc\n.venv/\nvenv/\n*.egg-info/\ndist/\nbuild/\n",
        },
        "open": "{name}/main.py",
    },
    "FastAPI": {
        "files": {
            "main.py": 'from fastapi import FastAPI\n\napp = FastAPI()\n\n\n@app.get("/")\ndef root():\n    return {"message": "Hello World"}\n',
            "requirements.txt": "fastapi\nuvicorn[standard]\n",
            "README.md": "# {name}\n\nA FastAPI project.\n\n## Run\n\n```bash\nuvicorn main:app --reload\n```\n",
            ".gitignore": "__pycache__/\n*.pyc\n.venv/\nvenv/\n.env\n",
        },
        "open": "main.py",
    },
    "Ansible Role": {
        "files": {
            "tasks/main.yml": "---\n- name: Example task\n  debug:\n    msg: \"Hello from {name}\"\n",
            "defaults/main.yml": "---\n# Default variables for {name}\n",
            "vars/main.yml": "---\n# Variables for {name}\n",
            "handlers/main.yml": "---\n# Handlers for {name}\n",
            "templates/.gitkeep": "",
            "files/.gitkeep": "",
            "meta/main.yml": "---\ngalaxy_info:\n  role_name: {name}\n  author: your_name\n  description: \"\"\n  min_ansible_version: \"2.9\"\n",
            "README.md": "# {name}\n\nAn Ansible role.\n\n## Requirements\n\nNone.\n\n## Role Variables\n\nSee `defaults/main.yml`.\n\n## Example Playbook\n\n```yaml\n- hosts: all\n  roles:\n    - {name}\n```\n",
        },
        "open": "tasks/main.yml",
    },
    "Bash Script": {
        "files": {
            "{name}.sh": "#!/usr/bin/env bash\nset -euo pipefail\n\n# {name}\n# Description: \n\nmain() {{\n    echo \"Hello from {name}\"\n}}\n\nmain \"$@\"\n",
            "README.md": "# {name}\n\nA bash script.\n\n## Usage\n\n```bash\nbash {name}.sh\n```\n",
            ".gitignore": "*.log\n*.tmp\n",
        },
        "open": "{name}.sh",
    },
    "Blank": {
        "files": {
            "README.md": "# {name}\n\n",
            ".gitignore": "",
        },
        "open": "README.md",
    },
}


class NewProjectDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Project")
        self.setFixedSize(520, 420)
        self.result_path = None
        self.result_open_file = None

        self._t = get_theme()
        self._setup_ui()
        self.apply_styles(self._t)

        theme_signals.theme_changed.connect(self._on_theme_changed)

    # ── Theme handling ────────────────────────────────────────────────────

    def _on_theme_changed(self, t: dict):
        self._t = t
        self.apply_styles(t)

    def apply_styles(self, t: dict):
        self.setStyleSheet(build_new_project_dialog_stylesheet(t))
        # Title label sits outside the QDialog selector scope so needs
        # its own nudge — fg0 gives it the brightest foreground.
        self._title_label.setStyleSheet(f"color: {t['fg0']}; font-size: 14pt;")

    # ── UI Setup ──────────────────────────────────────────────────────────

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Title
        self._title_label = QLabel("New Project")
        self._title_label.setFont(QFont(QFONT_UI, 14, QFont.Weight.Bold))
        layout.addWidget(self._title_label)

        # Project name
        layout.addWidget(QLabel("Project name"))
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("my_project")
        layout.addWidget(self.name_input)

        # Project type
        layout.addWidget(QLabel("Project type"))
        self.type_combo = QComboBox()
        for ptype in PROJECT_TYPES:
            self.type_combo.addItem(ptype)
        layout.addWidget(self.type_combo)

        # Location
        layout.addWidget(QLabel("Location"))
        loc_layout = QHBoxLayout()
        self.loc_input = QLineEdit()
        self.loc_input.setPlaceholderText(os.path.expanduser("~/projects"))
        self.loc_input.setText(os.path.expanduser("~/projects"))
        browse_btn = QPushButton("Browse")
        browse_btn.setFixedWidth(80)
        browse_btn.clicked.connect(self._browse_location)
        loc_layout.addWidget(self.loc_input)
        loc_layout.addWidget(browse_btn)
        layout.addLayout(loc_layout)

        # Options group
        options_group = QGroupBox("Options")
        options_layout = QVBoxLayout(options_group)
        options_layout.setSpacing(8)

        self.git_check = QCheckBox("Initialize git repository")
        self.git_check.setChecked(True)
        options_layout.addWidget(self.git_check)

        self.venv_check = QCheckBox("Create virtual environment (.venv)")
        self.venv_check.setChecked(False)
        options_layout.addWidget(self.venv_check)

        layout.addWidget(options_group)
        layout.addStretch()

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("cancel")
        cancel_btn.clicked.connect(self.reject)
        create_btn = QPushButton("Create Project")
        create_btn.clicked.connect(self._create)
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(create_btn)
        layout.addLayout(btn_layout)

    # ── Actions ───────────────────────────────────────────────────────────

    def _browse_location(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Choose Location",
            self.loc_input.text() or os.path.expanduser("~")
        )
        if folder:
            self.loc_input.setText(folder)

    def _create(self):
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Missing Name", "Please enter a project name.")
            return

        safe_name = re.sub(r'[^\w\-]', '_', name)
        if safe_name != name:
            self.name_input.setText(safe_name)
            name = safe_name

        location = self.loc_input.text().strip() or os.path.expanduser("~/projects")
        project_path = os.path.join(location, name)

        if os.path.exists(project_path):
            reply = QMessageBox.question(
                self, "Folder Exists",
                f"'{project_path}' already exists. Open it anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.result_path = project_path
                self.result_open_file = None
                self.accept()
            return

        try:
            ptype = self.type_combo.currentText()
            template = PROJECT_TYPES[ptype]
            os.makedirs(project_path, exist_ok=True)

            for rel_path, content in template["files"].items():
                rel_path = rel_path.replace("{name}", name)
                content = content.replace("{name}", name)
                full_path = os.path.join(project_path, rel_path)
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                with open(full_path, "w", encoding="utf-8") as f:
                    f.write(content)

            if self.git_check.isChecked():
                import subprocess
                subprocess.run(["git", "init"], cwd=project_path, capture_output=True)
                subprocess.run(["git", "add", "."], cwd=project_path, capture_output=True)
                subprocess.run(
                    ["git", "commit", "-m", "Initial commit"],
                    cwd=project_path, capture_output=True
                )

            if self.venv_check.isChecked():
                import subprocess
                subprocess.run(
                    ["python3", "-m", "venv", ".venv"],
                    cwd=project_path, capture_output=True
                )

            open_file = template.get("open", "")
            if open_file:
                open_file = open_file.replace("{name}", name)
                self.result_open_file = os.path.join(project_path, open_file)
            else:
                self.result_open_file = None

            self.result_path = project_path
            self.accept()

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not create project:\n{e}")

    def closeEvent(self, event):
        try:
            theme_signals.theme_changed.disconnect(self._on_theme_changed)
        except RuntimeError:
            pass
        super().closeEvent(event)