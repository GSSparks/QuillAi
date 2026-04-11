"""
ui/multi_file_diff_dialog.py

Multi-file diff review dialog for QuillAI AI-suggested changes.

Shows a file list on the left, a side-by-side editable diff on the right.
User can accept/skip each file individually, edit the proposed code,
then click "Apply Selected" to write all accepted changes to disk.
"""

import difflib
import os
from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTextEdit, QSplitter, QWidget, QListWidget, QListWidgetItem,
    QAbstractItemView,
)
from PyQt6.QtGui import QTextCursor, QTextCharFormat, QColor, QFont
from PyQt6.QtCore import Qt

from ui.theme import (
    get_theme, theme_signals,
    build_diff_apply_dialog_stylesheet,
    build_diff_apply_parts,
    QFONT_CODE,
)


class MultiFileDiffDialog(QDialog):
    """
    Review AI-proposed changes across multiple files.

    changes: [(rel_path, mode, proposed_code), ...]
    project_root: absolute path to resolve rel_path against
    """

    def __init__(self, changes: list, project_root: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Review AI Changes")
        self.setMinimumSize(1100, 620)

        self._project_root = project_root
        self._t            = get_theme()

        # Build per-file state:
        #   {rel_path: {"mode": str, "original": str, "proposed": str,
        #               "accepted": bool, "abs_path": str}}
        self._files = {}
        for rel_path, mode, proposed in changes:
            abs_path = str((Path(project_root) / rel_path).resolve())
            try:
                original = Path(abs_path).read_text(encoding="utf-8")
            except Exception:
                original = ""
            self._files[rel_path] = {
                "mode":     mode,
                "original": original,
                "proposed": proposed,
                "accepted": True,   # default: all accepted
                "abs_path": abs_path,
            }

        self.applied_paths: list[str] = []   # filled on accept

        self._setup_ui()
        self._apply_styles(self._t)
        theme_signals.theme_changed.connect(self._on_theme_changed)

        # Select first file
        if self._file_list.count() > 0:
            self._file_list.setCurrentRow(0)

    # ── Theme ─────────────────────────────────────────────────────────────

    def _on_theme_changed(self, t: dict):
        self._t = t
        self._apply_styles(t)
        self._render_current()

    def _apply_styles(self, t: dict):
        p = build_diff_apply_parts(t)
        self.setStyleSheet(build_diff_apply_dialog_stylesheet(t))
        self._splitter.setStyleSheet(p["splitter_handle"])
        self._diff_splitter.setStyleSheet(p["splitter_handle"])
        self._left_label.setStyleSheet(p["left_label"])
        self._right_label.setStyleSheet(p["right_label"])
        self._orig_view.setStyleSheet(p["text_view"])
        self._prop_view.setStyleSheet(p["text_view"])
        self._hint.setStyleSheet(p["hint"])
        self._discard_btn.setStyleSheet(p["discard_btn"])
        self._apply_btn.setStyleSheet(p["accept_btn"])

        t2 = get_theme()
        self._file_list.setStyleSheet(f"""
            QListWidget {{
                background: {t2.get('bg1', '#3c3836')};
                border: none;
                border-right: 1px solid {t2.get('border', '#504945')};
                font-family: '{QFONT_CODE}', monospace;
                font-size: 9pt;
                outline: none;
            }}
            QListWidget::item {{
                padding: 6px 10px;
                color: {t2.get('fg1', '#ebdbb2')};
                border-bottom: 1px solid {t2.get('bg2', '#504945')};
            }}
            QListWidget::item:selected {{
                background: {t2.get('bg3', '#665c54')};
                color: {t2.get('yellow', '#fabd2f')};
            }}
            QListWidget::item:hover {{
                background: {t2.get('bg2', '#504945')};
            }}
        """)
        self._toggle_btn.setStyleSheet(f"""
            QPushButton {{
                background: {t2.get('bg2', '#504945')};
                color: {t2.get('fg4', '#a89984')};
                border: 1px solid {t2.get('border', '#504945')};
                border-radius: 3px;
                padding: 3px 10px;
                font-size: 8pt;
            }}
            QPushButton:hover {{
                background: {t2.get('bg3', '#665c54')};
                color: {t2.get('fg1', '#ebdbb2')};
            }}
        """)

    # ── UI Setup ──────────────────────────────────────────────────────────

    def _setup_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 12)
        root_layout.setSpacing(0)

        # ── Main horizontal splitter: file list | diff ────────────────
        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setHandleWidth(2)

        # ── Left: file list ───────────────────────────────────────────
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        files_label = QLabel("  Files")
        files_label.setFixedHeight(28)
        left_layout.addWidget(files_label)

        self._file_list = QListWidget()
        self._file_list.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        for rel_path in self._files:
            fname = os.path.basename(rel_path)
            item  = QListWidgetItem(f"✓  {fname}")
            item.setData(Qt.ItemDataRole.UserRole, rel_path)
            item.setToolTip(rel_path)
            self._file_list.addItem(item)

        self._file_list.currentRowChanged.connect(self._on_file_selected)
        left_layout.addWidget(self._file_list)

        # Toggle accept/skip button
        self._toggle_btn = QPushButton("Skip this file")
        self._toggle_btn.setFixedHeight(28)
        self._toggle_btn.clicked.connect(self._toggle_current_file)
        left_layout.addWidget(self._toggle_btn)

        self._splitter.addWidget(left_panel)

        # ── Right: side-by-side diff ──────────────────────────────────
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        self._diff_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._diff_splitter.setHandleWidth(2)

        # Original (read-only)
        orig_widget = QWidget()
        orig_layout = QVBoxLayout(orig_widget)
        orig_layout.setContentsMargins(0, 0, 0, 0)
        orig_layout.setSpacing(0)
        self._left_label = QLabel("  Original")
        self._left_label.setFixedHeight(28)
        self._orig_view = self._make_view(editable=False)
        orig_layout.addWidget(self._left_label)
        orig_layout.addWidget(self._orig_view)
        self._diff_splitter.addWidget(orig_widget)

        # Proposed (editable)
        prop_widget = QWidget()
        prop_layout = QVBoxLayout(prop_widget)
        prop_layout.setContentsMargins(0, 0, 0, 0)
        prop_layout.setSpacing(0)
        self._right_label = QLabel("  AI Rewrite  (editable)")
        self._right_label.setFixedHeight(28)
        self._prop_view = self._make_view(editable=True)
        self._prop_view.textChanged.connect(self._on_proposed_edited)
        prop_layout.addWidget(self._right_label)
        prop_layout.addWidget(self._prop_view)
        self._diff_splitter.addWidget(prop_widget)

        self._diff_splitter.setSizes([500, 500])
        right_layout.addWidget(self._diff_splitter)
        self._splitter.addWidget(right_panel)

        self._splitter.setSizes([200, 900])
        root_layout.addWidget(self._splitter)

        # Sync scrolling between orig and proposed
        self._orig_view.verticalScrollBar().valueChanged.connect(
            self._prop_view.verticalScrollBar().setValue
        )
        self._prop_view.verticalScrollBar().valueChanged.connect(
            self._orig_view.verticalScrollBar().setValue
        )

        # ── Footer ────────────────────────────────────────────────────
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(12, 8, 12, 0)

        accepted_count = sum(1 for f in self._files.values() if f["accepted"])
        self._hint = QLabel(
            f"Review changes across {len(self._files)} files. "
            f"Edit the right panel to adjust proposed code."
        )

        self._discard_btn = QPushButton("✕  Cancel")
        self._discard_btn.clicked.connect(self.reject)

        self._apply_btn = QPushButton(
            f"✓  Apply {accepted_count} of {len(self._files)} files"
        )
        self._apply_btn.clicked.connect(self._apply_accepted)

        btn_layout.addWidget(self._hint)
        btn_layout.addStretch()
        btn_layout.addWidget(self._discard_btn)
        btn_layout.addWidget(self._apply_btn)
        root_layout.addLayout(btn_layout)

    @staticmethod
    def _make_view(editable: bool) -> QTextEdit:
        view = QTextEdit()
        view.setReadOnly(not editable)
        view.setFont(QFont(QFONT_CODE, 10))
        view.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        return view

    # ── File list interaction ─────────────────────────────────────────────

    def _on_file_selected(self, row: int):
        if row < 0:
            return
        item     = self._file_list.item(row)
        rel_path = item.data(Qt.ItemDataRole.UserRole)
        self._current_rel = rel_path
        self._render_current()
        accepted = self._files[rel_path]["accepted"]
        self._toggle_btn.setText("Skip this file" if accepted else "Accept this file")

    def _toggle_current_file(self):
        rel_path = getattr(self, '_current_rel', None)
        if not rel_path:
            return
        self._files[rel_path]["accepted"] = not self._files[rel_path]["accepted"]
        accepted = self._files[rel_path]["accepted"]

        # Update list item label
        row  = self._file_list.currentRow()
        item = self._file_list.item(row)
        fname = os.path.basename(rel_path)
        t = get_theme()
        if accepted:
            item.setText(f"✓  {fname}")
            item.setForeground(QColor(t.get('fg1', '#ebdbb2')))
            self._toggle_btn.setText("Skip this file")
        else:
            item.setText(f"–  {fname}")
            item.setForeground(QColor(t.get('fg4', '#a89984')))
            self._toggle_btn.setText("Accept this file")

        self._update_apply_button()

    def _update_apply_button(self):
        accepted_count = sum(1 for f in self._files.values() if f["accepted"])
        self._apply_btn.setText(
            f"✓  Apply {accepted_count} of {len(self._files)} files"
        )

    # ── Diff rendering ────────────────────────────────────────────────────

    def _render_current(self):
        rel_path = getattr(self, '_current_rel', None)
        if not rel_path:
            return

        info = self._files[rel_path]
        p    = build_diff_apply_parts(self._t)

        removed_fmt = QTextCharFormat()
        removed_fmt.setForeground(QColor(p["diff_removed"]))
        added_fmt = QTextCharFormat()
        added_fmt.setForeground(QColor(p["diff_added"]))
        neutral_fmt = QTextCharFormat()
        neutral_fmt.setForeground(QColor(p["diff_neutral"]))

        orig_lines = info["original"].splitlines(keepends=True)
        prop_lines = info["proposed"].splitlines(keepends=True)
        matcher    = difflib.SequenceMatcher(None, orig_lines, prop_lines)

        # Block signals while populating to avoid _on_proposed_edited firing
        self._prop_view.blockSignals(True)
        self._orig_view.clear()
        self._prop_view.clear()

        orig_cursor = self._orig_view.textCursor()
        prop_cursor = self._prop_view.textCursor()

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

        self._orig_view.verticalScrollBar().setValue(0)
        self._prop_view.verticalScrollBar().setValue(0)
        self._prop_view.blockSignals(False)

    def _on_proposed_edited(self):
        """Save edits back to the file state as the user types."""
        rel_path = getattr(self, '_current_rel', None)
        if rel_path and rel_path in self._files:
            self._files[rel_path]["proposed"] = self._prop_view.toPlainText()

    # ── Apply ─────────────────────────────────────────────────────────────

    def _apply_accepted(self):
        """Apply all accepted files and close."""
        from core.patch_applier import apply_function, apply_full, apply_perl_function

        self.applied_paths = []
        errors = []

        for rel_path, info in self._files.items():
            if not info["accepted"]:
                continue
            abs_path = info["abs_path"]
            mode     = info["mode"]
            code     = info["proposed"]

            if mode == "function":
                ok, msg = apply_function(abs_path, code)
            elif mode == "perl_function":
                ok, msg = apply_perl_function(abs_path, code)
            else:
                # Write directly — user already reviewed in this dialog
                try:
                    Path(abs_path).write_text(code, encoding="utf-8")
                    ok, msg = True, f"Written: {rel_path}"
                except Exception as e:
                    ok, msg = False, str(e)

            if ok:
                self.applied_paths.append(abs_path)
            else:
                errors.append(f"{rel_path}: {msg}")

        if errors:
            self._hint.setText(f"⚠ {len(errors)} error(s) — see status bar")
        else:
            self.accept()