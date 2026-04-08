"""
editor_dialog.py

Inline job editor dialog — appears when double-clicking a job card.
Edits are written back to the YAML file surgically.
"""

import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QComboBox, QCheckBox, QPushButton,
    QLabel, QTextEdit, QDialogButtonBox, QWidget,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

from ui.theme import get_theme, theme_signals


# ── Stylesheet ────────────────────────────────────────────────────────────────

def _build_stylesheet(t: dict) -> str:
    return f"""
        QDialog, QWidget {{
            background: {t['bg1']};
            color: {t['fg1']};
        }}
        QLabel {{
            background: {t['bg1']};
            color: {t['fg4']};
            font-size: 9pt;
        }}
        QLabel#jobEditorTitle {{
            background: {t['bg1']};
            color: {t['yellow']};
            font-size: 11pt;
            padding: 4px 0;
        }}
        QLabel#sectionLabel {{
            background: {t['bg1']};
            color: {t['green']};
            font-size: 9pt;
            font-weight: bold;
            padding-top: 4px;
        }}
        QLineEdit, QComboBox {{
            background: {t['bg2']};
            color: {t['fg1']};
            border: 1px solid {t['bg3']};
            border-radius: 3px;
            padding: 3px 6px;
            font-size: 9pt;
        }}
        QLineEdit:focus, QComboBox:focus {{
            border-color: {t['yellow']};
        }}
        QTextEdit {{
            background: {t['bg0']};
            color: {t['aqua']};
            border: 1px solid {t['bg3']};
            border-radius: 3px;
            padding: 4px 6px;
            font-family: monospace;
            font-size: 9pt;
        }}
        QTextEdit:focus {{
            border-color: {t['yellow']};
        }}
        QComboBox::drop-down {{
            border: none;
            width: 20px;
        }}
        QCheckBox {{
            background: {t['bg1']};
            color: {t['fg1']};
            font-size: 9pt;
        }}
        QCheckBox::indicator {{
            width: 14px;
            height: 14px;
            border: 1px solid {t['bg3']};
            border-radius: 2px;
            background: {t['bg2']};
        }}
        QCheckBox::indicator:checked {{
            background: {t['yellow']};
            border-color: {t['yellow']};
        }}
        QPushButton {{
            background: {t['bg2']};
            color: {t['fg1']};
            border: 1px solid {t['bg3']};
            border-radius: 3px;
            padding: 4px 16px;
            font-size: 9pt;
            min-width: 64px;
        }}
        QPushButton:hover {{
            background: {t['bg3']};
            border-color: {t['fg4']};
        }}
        QPushButton:pressed {{
            background: {t['bg4']};
        }}
        QPushButton:default {{
            border-color: {t['yellow']};
            color: {t['yellow']};
        }}
        QPushButton:default:hover {{
            background: {t['bg3']};
        }}
        QFormLayout QLabel {{
            background: {t['bg1']};
            color: {t['fg4']};
        }}
    """


# ── Dialog ────────────────────────────────────────────────────────────────────

class JobEditorDialog(QDialog):
    """
    Floating editor for a single pipeline job.
    Emits job_changed with a dict of {field: new_value} on accept.
    """

    job_changed = pyqtSignal(str, dict)   # job_name, changes

    def __init__(self, job, stages: list,
                 all_jobs: list = None, parent=None):
        super().__init__(parent)
        self.job      = job
        self.stages   = stages
        self.all_jobs = [j for j in (all_jobs or []) if j != job.name]
        self._orig    = {}

        self.setWindowTitle(f"Edit job: {job.name}")
        self.setWindowFlags(
            Qt.WindowType.Dialog |
            Qt.WindowType.FramelessWindowHint
        )
        self.setModal(True)
        self.setMinimumWidth(400)

        self._build_ui()
        self.setStyleSheet(_build_stylesheet(get_theme()))
        theme_signals.theme_changed.connect(
            lambda t: self.setStyleSheet(_build_stylesheet(t))
        )

    # ── UI ────────────────────────────────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        # Title
        title = QLabel(f"  ✎  {self.job.name}")
        title.setObjectName("jobEditorTitle")
        font = QFont()
        font.setPointSize(11)
        font.setBold(True)
        title.setFont(font)
        layout.addWidget(title)

        # Divider
        divider = QWidget()
        divider.setFixedHeight(1)
        divider.setStyleSheet("background: transparent;")
        layout.addWidget(divider)

        # Form
        form = QFormLayout()
        form.setSpacing(7)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow
        )

        # Job name
        self._name = QLineEdit(self.job.name)
        self._orig['name'] = self.job.name
        form.addRow("Name:", self._name)

        # Stage
        self._stage = QComboBox()
        for s in self.stages:
            self._stage.addItem(s)
        idx = self._stage.findText(self.job.stage)
        if idx >= 0:
            self._stage.setCurrentIndex(idx)
        self._orig['stage'] = self.job.stage
        form.addRow("Stage:", self._stage)

        # Image
        self._image = QLineEdit(self.job.image)
        self._image.setPlaceholderText("e.g. python:3.11-slim")
        self._orig['image'] = self.job.image
        form.addRow("Image:", self._image)

        # When
        self._when = QComboBox()
        for w in ['on_success', 'manual', 'always', 'never', 'on_failure']:
            self._when.addItem(w)
        idx = self._when.findText(self.job.when)
        if idx >= 0:
            self._when.setCurrentIndex(idx)
        self._orig['when'] = self.job.when
        form.addRow("When:", self._when)

        # Environment
        self._env = QLineEdit(self.job.environment)
        self._env.setPlaceholderText("e.g. production")
        self._orig['environment'] = self.job.environment
        form.addRow("Environment:", self._env)

        # Allow failure
        self._allow_failure = QCheckBox()
        self._allow_failure.setChecked(self.job.allow_failure)
        self._orig['allow_failure'] = self.job.allow_failure
        form.addRow("Allow failure:", self._allow_failure)

        layout.addLayout(form)

        # Needs section
        if self.all_jobs:
            from PyQt6.QtWidgets import QListWidget, QListWidgetItem
            needs_label = QLabel("Needs:")
            needs_label.setObjectName("sectionLabel")
            layout.addWidget(needs_label)

            self._needs_list = QListWidget()
            self._needs_list.setMaximumHeight(100)
            self._needs_list.setSelectionMode(
                QListWidget.SelectionMode.MultiSelection
            )
            self._needs_list.setStyleSheet(f"""
                QListWidget {{
                    background: {get_theme()['bg0']};
                    color: {get_theme()['fg1']};
                    border: 1px solid {get_theme()['bg3']};
                    border-radius: 3px;
                    font-size: 9pt;
                }}
                QListWidget::item:selected {{
                    background: {get_theme()['bg3']};
                    color: {get_theme()['aqua']};
                }}
            """)
            for jname in self.all_jobs:
                item = QListWidgetItem(jname)
                self._needs_list.addItem(item)
                if jname in (self.job.needs or []):
                    item.setSelected(True)
            self._orig['needs'] = list(self.job.needs or [])
            layout.addWidget(self._needs_list)

            needs_hint = QLabel(
                "Ctrl+click to select multiple. "
                "Or drag ports on the canvas."
            )
            needs_hint.setStyleSheet("font-size: 8pt;")
            layout.addWidget(needs_hint)
        else:
            self._needs_list = None

        # Script section
        script_label = QLabel("Script:")
        script_label.setObjectName("sectionLabel")
        layout.addWidget(script_label)

        self._script = QTextEdit()
        self._script.setFont(QFont("monospace", 9))
        self._script.setPlaceholderText(
            "One command per line…\n"
            "e.g.\n"
            "  echo \"Hello\"\n"
            "  python -m pytest"
        )
        self._script.setMinimumHeight(120)
        self._script.setMaximumHeight(240)

        if self.job.script:
            self._script.setPlainText('\n'.join(self.job.script))
        self._orig['script'] = '\n'.join(self.job.script)

        layout.addWidget(self._script)

        # Script hint
        hint = QLabel("One command per line. Each line becomes a list item.")
        hint.setStyleSheet("font-size: 8pt;")
        layout.addWidget(hint)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        ok_btn = QPushButton("Apply")
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self._on_accept)
        btn_layout.addWidget(ok_btn)

        layout.addLayout(btn_layout)

    # ── Accept ────────────────────────────────────────────────────────────

    def _on_accept(self):
        changes = {}

        name = self._name.text().strip()
        if name and name != self._orig['name']:
            changes['name'] = name

        stage = self._stage.currentText()
        if stage != self._orig['stage']:
            changes['stage'] = stage

        image = self._image.text().strip()
        if image != self._orig['image']:
            changes['image'] = image

        when = self._when.currentText()
        if when != self._orig['when']:
            changes['when'] = when

        env = self._env.text().strip()
        if env != self._orig['environment']:
            changes['environment'] = env

        af = self._allow_failure.isChecked()
        if af != self._orig['allow_failure']:
            changes['allow_failure'] = af

        script = self._script.toPlainText().strip()
        if script != self._orig.get('script', ''):
            changes['script'] = script

        if self._needs_list is not None:
            new_needs = [
                self._needs_list.item(i).text()
                for i in range(self._needs_list.count())
                if self._needs_list.item(i).isSelected()
            ]
            if new_needs != self._orig.get('needs', []):
                changes['needs'] = new_needs

        if changes:
            self.job_changed.emit(self.job.name, changes)

        self.accept()

    # ── Cleanup ───────────────────────────────────────────────────────────

    def closeEvent(self, event):
        try:
            theme_signals.theme_changed.disconnect()
        except (RuntimeError, TypeError):
            pass
        super().closeEvent(event)