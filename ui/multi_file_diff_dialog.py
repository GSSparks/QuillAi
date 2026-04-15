"""
ui/multi_file_diff_dialog.py

Multi-file diff review dialog for QuillAI agent write operations.

Matches the aesthetic of DiffApplyDialog exactly — side-by-side split
view per file, synchronized scrolling, same color scheme.

Changes come in as (path, mode, code) tuples where:
  mode = "function"      — replace a single function/class
  mode = "full"          — replace entire file content
  mode = "patch"         — patch_file op: code is (old_text, new_text)
  mode = "perl_function" — Perl function replace
"""

from __future__ import annotations

import difflib
import re
from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QSplitter,
    QPushButton, QLabel, QScrollArea, QWidget,
    QCheckBox, QFrame, QTextEdit,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QTextCharFormat, QColor, QFont

from ui.theme import (
    get_theme, theme_signals,
    build_diff_apply_dialog_stylesheet,
    build_diff_apply_parts,
    FONT_UI, QFONT_CODE,
)


# ── File content helpers ───────────────────────────────────────────────────────

def _read_file_safe(abs_path: str) -> str:
    try:
        return Path(abs_path).read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def _preview_new_content(abs_path: str, mode: str, code) -> tuple[str, str]:
    """
    Returns (old_content, new_content) for diffing.
    code may be a string or (old_text, new_text) tuple for patch mode.
    """
    old = _read_file_safe(abs_path)

    if mode == "patch":
        old_text, new_text = code
        if old and old_text in old:
            # Show full file with patch applied — gives full context
            return old, old.replace(old_text, new_text, 1)
        # File doesn't exist or snippet not found — diff the snippets directly
        return old_text, new_text

    if mode == "full":
        return old, code

    # function / perl_function
    if not old:
        return "", code

    fn_match = re.search(r"^\s*(?:def|class|sub)\s+(\w+)", code, re.MULTILINE)
    if not fn_match:
        return old, code

    fn_name = fn_match.group(1)
    pattern = re.compile(
        r"(^[ \t]*(?:def|class|sub)\s+" + re.escape(fn_name) +
        r"\b.*?)(?=^[ \t]*(?:def|class|sub)\s+\w|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    m = pattern.search(old)
    if m:
        new = old[:m.start()] + code + "\n" + old[m.end():]
    else:
        new = old + "\n\n" + code

    return old, new


# ── Per-file diff panel ────────────────────────────────────────────────────────

class FileDiffPanel(QFrame):
    """
    One panel per file — header + side-by-side diff matching DiffApplyDialog.
    """

    def __init__(self, file_path: str, mode: str, code,
                 project_root: str, parent=None):
        super().__init__(parent)
        self.file_path    = file_path
        self.mode         = mode
        self.code         = code
        self.project_root = project_root
        self._t           = get_theme()

        self.abs_path = str((Path(project_root) / file_path).resolve())
        self._old, self._new = _preview_new_content(self.abs_path, mode, code)
        self._is_new_file    = not Path(self.abs_path).exists()

        self._build_ui()
        self._populate()

    def _build_ui(self):
        t = self._t
        p = build_diff_apply_parts(t)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Header ──
        header = QFrame()
        header.setFixedHeight(34)
        header.setStyleSheet(
            f"background: {t.get('bg2', '#504945')};"
            f"border-radius: 4px 4px 0 0;"
        )
        hl = QHBoxLayout(header)
        hl.setContentsMargins(10, 0, 10, 0)
        hl.setSpacing(8)

        self.checkbox = QCheckBox()
        self.checkbox.setChecked(True)
        hl.addWidget(self.checkbox)

        # Badge
        orig_lines = self._old.splitlines()
        new_lines  = self._new.splitlines()
        matcher    = difflib.SequenceMatcher(None, orig_lines, new_lines)
        adds = removes = 0
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag in ("replace", "insert"):
                adds    += j2 - j1
            if tag in ("replace", "delete"):
                removes += i2 - i1

        if self._is_new_file:
            badge_color, badge_text = t.get("blue", "#458588"), "NEW"
        elif adds == 0 and removes == 0:
            badge_color, badge_text = t.get("fg4", "#a89984"), "NO CHANGES"
        else:
            badge_color = t.get("yellow", "#d79921")
            badge_text  = f"+{adds} \u2212{removes}"

        badge = QLabel(badge_text)
        badge.setStyleSheet(
            f"color: {badge_color}; font-family: '{QFONT_CODE}';"
            f"font-size: 8pt; font-weight: bold; background: transparent;"
        )
        hl.addWidget(badge)

        fname = QLabel(self.file_path)
        fname.setStyleSheet(
            f"color: {t.get('fg1', '#ebdbb2')}; font-family: '{QFONT_CODE}';"
            f"font-size: 9pt; font-weight: bold; background: transparent;"
        )
        hl.addWidget(fname, stretch=1)

        mode_lbl = QLabel(self.mode)
        mode_lbl.setStyleSheet(
            f"color: {t.get('fg4', '#a89984')}; font-family: '{FONT_UI}';"
            f"font-size: 8pt; background: transparent;"
        )
        hl.addWidget(mode_lbl)
        layout.addWidget(header)

        # ── Body: side-by-side diff ──
        body = QWidget()
        body.setStyleSheet(
            f"background: {t.get('bg0_hard', '#1d2021')};"
            f"border: 1px solid {t.get('border', '#504945')};"
            f"border-top: none; border-radius: 0 0 4px 4px;"
        )
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        # Column labels
        label_row = QHBoxLayout()
        label_row.setContentsMargins(0, 0, 0, 0)
        label_row.setSpacing(0)
        self._left_label  = QLabel("  Original")
        self._right_label = QLabel("  Proposed")
        self._left_label.setFixedHeight(22)
        self._right_label.setFixedHeight(22)
        self._left_label.setStyleSheet(p["left_label"])
        self._right_label.setStyleSheet(p["right_label"])
        label_row.addWidget(self._left_label)
        label_row.addWidget(self._right_label)
        body_layout.addLayout(label_row)

        # Splitter
        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setHandleWidth(2)
        self._splitter.setStyleSheet(p["splitter_handle"])

        self.original_view = self._make_view(p)
        self.proposed_view = self._make_view(p)
        self._splitter.addWidget(self.original_view)
        self._splitter.addWidget(self.proposed_view)
        self._splitter.setSizes([1, 1])

        # Sync scrolling
        self.original_view.verticalScrollBar().valueChanged.connect(
            self.proposed_view.verticalScrollBar().setValue
        )
        self.proposed_view.verticalScrollBar().valueChanged.connect(
            self.original_view.verticalScrollBar().setValue
        )

        body_layout.addWidget(self._splitter)
        layout.addWidget(body)

    @staticmethod
    def _make_view(p: dict) -> QTextEdit:
        view = QTextEdit()
        view.setReadOnly(True)
        view.setFont(QFont(QFONT_CODE, 10))
        view.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        view.setMinimumHeight(150)
        view.setMaximumHeight(400)
        view.setStyleSheet(p["text_view"])
        return view

    def _populate(self):
        p = build_diff_apply_parts(self._t)

        removed_fmt = QTextCharFormat()
        removed_fmt.setForeground(QColor(p["diff_removed"]))
        added_fmt = QTextCharFormat()
        added_fmt.setForeground(QColor(p["diff_added"]))
        neutral_fmt = QTextCharFormat()
        neutral_fmt.setForeground(QColor(p["diff_neutral"]))

        orig_lines = self._old.splitlines(keepends=True)
        prop_lines = self._new.splitlines(keepends=True)
        matcher    = difflib.SequenceMatcher(None, orig_lines, prop_lines)

        orig_cursor = self.original_view.textCursor()
        prop_cursor = self.proposed_view.textCursor()

        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                for line in orig_lines[i1:i2]:
                    orig_cursor.setCharFormat(neutral_fmt)
                    orig_cursor.insertText(line)
                for line in prop_lines[j1:j2]:
                    prop_cursor.setCharFormat(neutral_fmt)
                    prop_cursor.insertText(line)
            elif tag == "replace":
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
            elif tag == "delete":
                for line in orig_lines[i1:i2]:
                    orig_cursor.setCharFormat(removed_fmt)
                    orig_cursor.insertText(line)
                for _ in orig_lines[i1:i2]:
                    prop_cursor.setCharFormat(neutral_fmt)
                    prop_cursor.insertText("\n")
            elif tag == "insert":
                for _ in prop_lines[j1:j2]:
                    orig_cursor.setCharFormat(neutral_fmt)
                    orig_cursor.insertText("\n")
                for line in prop_lines[j1:j2]:
                    prop_cursor.setCharFormat(added_fmt)
                    prop_cursor.insertText(line)

        self.original_view.verticalScrollBar().setValue(0)
        self.proposed_view.verticalScrollBar().setValue(0)

    def update_theme(self, t: dict):
        self._t = t
        p = build_diff_apply_parts(t)
        self._left_label.setStyleSheet(p["left_label"])
        self._right_label.setStyleSheet(p["right_label"])
        self._splitter.setStyleSheet(p["splitter_handle"])
        self.original_view.setStyleSheet(p["text_view"])
        self.proposed_view.setStyleSheet(p["text_view"])
        self.original_view.clear()
        self.proposed_view.clear()
        self._populate()

    def is_checked(self) -> bool:
        return self.checkbox.isChecked()

    def apply(self) -> tuple[bool, str]:
        from core.patch_applier import apply_function, apply_full, apply_perl_function
        if self.mode == "function":
            return apply_function(self.abs_path, self.code, skip_dialog=True)
        elif self.mode == "perl_function":
            return apply_perl_function(self.abs_path, self.code, skip_dialog=True)
        elif self.mode == "patch":
            old_text, new_text = self.code
            try:
                content = Path(self.abs_path).read_text(encoding="utf-8")
                if old_text not in content:
                    return False, f"patch target not found in {self.file_path}"
                Path(self.abs_path).write_text(
                    content.replace(old_text, new_text, 1), encoding="utf-8"
                )
                return True, f"patched {self.file_path}"
            except Exception as e:
                return False, str(e)
        else:
            return apply_full(self.abs_path, self.code, skip_dialog=True)


# ── Main dialog ───────────────────────────────────────────────────────────────

class MultiFileDiffDialog(QDialog):
    """
    Review and apply changes to multiple files at once.
    Matches DiffApplyDialog aesthetics — side-by-side per file.
    """

    def __init__(self, changes: list, project_root: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Review AI Changes")
        self.setMinimumSize(900, 600)
        self.resize(1100, 750)

        self._changes      = changes
        self._project_root = project_root
        self._panels: list[FileDiffPanel] = []
        self.applied_paths: list[str]     = []

        self._t = get_theme()
        self._build_ui()
        self.apply_styles(self._t)
        theme_signals.theme_changed.connect(self._on_theme_changed)

    def apply_styles(self, t: dict):
        p = build_diff_apply_parts(t)
        self.setStyleSheet(build_diff_apply_dialog_stylesheet(t))
        self._hint.setStyleSheet(p["hint"])
        self._discard_btn.setStyleSheet(p["discard_btn"])
        self._accept_btn.setStyleSheet(p["accept_btn"])

    def _on_theme_changed(self, t: dict):
        self._t = t
        self.apply_styles(t)
        for panel in self._panels:
            panel.update_theme(t)

    def _build_ui(self):
        t = self._t
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 12)
        layout.setSpacing(0)

        # Scrollable panels
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(0, 0, 0, 0)
        inner_layout.setSpacing(12)

        for path, mode, code in self._changes:
            panel = FileDiffPanel(path, mode, code, self._project_root)
            panel.checkbox.stateChanged.connect(self._update_footer)
            self._panels.append(panel)
            inner_layout.addWidget(panel)

        inner_layout.addStretch()
        scroll.setWidget(inner)
        layout.addWidget(scroll, stretch=1)

        # Footer — matches DiffApplyDialog
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(12, 8, 12, 0)

        _btn_style = (
            f"QPushButton {{ background: {t.get('bg2','#504945')};"
            f"color: {t.get('fg4','#a89984')}; border-radius: 4px;"
            f"padding: 4px 10px; font-size: 8pt; border: none; }}"
        )
        sel_all  = QPushButton("Select All")
        sel_none = QPushButton("Select None")
        sel_all.setStyleSheet(_btn_style)
        sel_none.setStyleSheet(_btn_style)
        sel_all.clicked.connect(lambda: self._set_all(True))
        sel_none.clicked.connect(lambda: self._set_all(False))

        self._hint = QLabel(self._hint_text())

        self._discard_btn = QPushButton("✕  Discard")
        self._discard_btn.clicked.connect(self.reject)

        self._accept_btn = QPushButton(self._accept_label())
        self._accept_btn.clicked.connect(self._apply)

        btn_layout.addWidget(sel_all)
        btn_layout.addWidget(sel_none)
        btn_layout.addSpacing(12)
        btn_layout.addWidget(self._hint)
        btn_layout.addStretch()
        btn_layout.addWidget(self._discard_btn)
        btn_layout.addWidget(self._accept_btn)
        layout.addLayout(btn_layout)

    def _hint_text(self) -> str:
        checked = sum(1 for p in self._panels if p.is_checked())
        return f"{checked} of {len(self._panels)} files selected"

    def _accept_label(self) -> str:
        checked = sum(1 for p in self._panels if p.is_checked())
        return f"\u2713  Accept {checked} File{'s' if checked != 1 else ''}"

    def _update_footer(self):
        self._hint.setText(self._hint_text())
        self._accept_btn.setText(self._accept_label())
        self._accept_btn.setEnabled(
            any(p.is_checked() for p in self._panels)
        )

    def _set_all(self, checked: bool):
        for panel in self._panels:
            panel.checkbox.setChecked(checked)

    def _apply(self):
        errors = []
        for panel in self._panels:
            if not panel.is_checked():
                continue
            ok, msg = panel.apply()
            if ok:
                self.applied_paths.append(panel.abs_path)
            else:
                errors.append(f"{panel.file_path}: {msg}")

        if errors:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self, "Some Changes Failed",
                "The following changes could not be applied:\n\n" +
                "\n".join(errors)
            )

        if self.applied_paths:
            self.accept()
        else:
            self.reject()

    def closeEvent(self, event):
        try:
            theme_signals.theme_changed.disconnect(self._on_theme_changed)
        except RuntimeError:
            pass
        super().closeEvent(event)