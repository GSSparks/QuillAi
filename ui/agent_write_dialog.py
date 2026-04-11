"""
ui/agent_write_dialog.py

Confirmation dialog for agent write operations.
Shows all pending write ops with checkboxes, lets user
accept/skip each one, then applies on confirm.
"""

import os
import subprocess
from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QScrollArea, QWidget, QCheckBox, QFrame,
)
from PyQt6.QtCore import Qt
from ui.theme import get_theme, theme_signals, build_diff_apply_dialog_stylesheet


class AgentWriteDialog(QDialog):
    """
    Review and confirm agent-proposed write operations.
    ops: [{"name": str, "attrs": dict, "description": str}, ...]
    """

    def __init__(self, ops: list, project_root: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Agent: Review Changes")
        self.setMinimumSize(600, 400)
        self._ops          = ops
        self._project_root = project_root
        self.applied_paths: list[str] = []
        self._checkboxes: list[QCheckBox] = []

        self._t = get_theme()
        self._setup_ui()
        self.setStyleSheet(build_diff_apply_dialog_stylesheet(self._t))
        theme_signals.theme_changed.connect(self._on_theme)

    def _on_theme(self, t: dict):
        self._t = t
        self.setStyleSheet(build_diff_apply_dialog_stylesheet(t))

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(8)

        t = self._t

        header = QLabel(
            f"The agent wants to make {len(self._ops)} change"
            f"{'s' if len(self._ops) != 1 else ''}. "
            "Review and uncheck any you want to skip."
        )
        header.setStyleSheet(
            f"color: {t.get('fg1','#ebdbb2')}; font-size: 9pt;"
        )
        header.setWordWrap(True)
        layout.addWidget(header)

        # Scrollable op list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        inner  = QWidget()
        inner_layout = QVBoxLayout(inner)
        inner_layout.setSpacing(6)
        inner_layout.setContentsMargins(0, 0, 0, 0)

        for op in self._ops:
            row = QFrame()
            row.setStyleSheet(
                f"QFrame {{ background: {t.get('bg1','#3c3836')};"
                f" border-radius: 4px; }}"
            )
            rl = QHBoxLayout(row)
            rl.setContentsMargins(10, 8, 10, 8)

            cb = QCheckBox()
            cb.setChecked(True)
            self._checkboxes.append(cb)
            rl.addWidget(cb)

            icon = "✏️" if op["name"] in ("patch_file", "write_file") else "⚙"
            lbl  = QLabel(f"{icon}  {op['description']}")
            lbl.setStyleSheet(
                f"color: {t.get('fg1','#ebdbb2')}; font-size: 9pt;"
                " background: transparent;"
            )
            lbl.setWordWrap(True)
            rl.addWidget(lbl, stretch=1)
            inner_layout.addWidget(row)

        inner_layout.addStretch()
        scroll.setWidget(inner)
        layout.addWidget(scroll, stretch=1)

        # Buttons
        btn_layout = QHBoxLayout()
        cancel_btn = QPushButton("✕  Cancel")
        cancel_btn.clicked.connect(self.reject)
        apply_btn  = QPushButton("✓  Apply Selected")
        apply_btn.clicked.connect(self._apply)
        btn_layout.addStretch()
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(apply_btn)
        layout.addLayout(btn_layout)

    def _apply(self):
        from ai.tools import run_tool
        for i, (op, cb) in enumerate(zip(self._ops, self._checkboxes)):
            if not cb.isChecked():
                continue
            name  = op["name"]
            attrs = op["attrs"]
            self._execute_write_op(name, attrs)
        self.accept()

    def _execute_write_op(self, name: str, attrs: dict):
        root = self._project_root
        try:
            if name == "patch_file":
                path    = attrs.get("path", "")
                old     = attrs.get("old", "")
                new     = attrs.get("new", "")
                abs_path = str((Path(root) / path).resolve())
                content  = Path(abs_path).read_text(encoding="utf-8")
                if old not in content:
                    print(f"[AgentWrite] patch_file: old text not found in {path}")
                    return
                Path(abs_path).write_text(
                    content.replace(old, new, 1), encoding="utf-8"
                )
                self.applied_paths.append(abs_path)

            elif name == "write_file":
                path     = attrs.get("path", "")
                content  = attrs.get("content", "")
                abs_path = str((Path(root) / path).resolve())
                Path(abs_path).parent.mkdir(parents=True, exist_ok=True)
                Path(abs_path).write_text(content, encoding="utf-8")
                self.applied_paths.append(abs_path)

            elif name == "shell_write":
                command = attrs.get("command", "")
                result  = subprocess.run(
                    command, shell=True, cwd=root,
                    capture_output=True, text=True, timeout=30,
                )
                if result.returncode != 0:
                    print(f"[AgentWrite] shell_write failed: {result.stderr[:200]}")
                else:
                    # Try to detect which files changed
                    if " " in command:
                        parts = command.split()
                        for part in parts:
                            candidate = Path(root) / part
                            if candidate.exists() and candidate.is_file():
                                self.applied_paths.append(str(candidate))

        except Exception as e:
            print(f"[AgentWrite] {name} error: {e}")