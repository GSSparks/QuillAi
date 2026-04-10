"""
ui/log_viewer.py

Generic log viewer dock — used by GitLab CI, run analyzer,
terminal stderr capture, and any other plugin that needs to
display scrollable log output with syntax highlighting.

Usage:
    from ui.log_viewer import LogViewerDock
    self.log_viewer = LogViewerDock(parent=self.app)
    self.app.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea,
                           self.log_viewer)
    self.log_viewer.show_log("Job: build", log_text, source="gitlab")
"""
from __future__ import annotations

import re
from PyQt6.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QPlainTextEdit, QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import (
    QTextCharFormat, QColor, QFont, QTextCursor,
    QSyntaxHighlighter,
)
from ui.theme import get_theme, theme_signals, build_dock_stylesheet


# ── Log syntax highlighter ────────────────────────────────────────────────────

class _LogHighlighter(QSyntaxHighlighter):
    """Highlights errors, warnings, timestamps, and section headers."""

    def __init__(self, doc, theme: dict):
        super().__init__(doc)
        self._t = theme
        self._build_rules()

    def _fmt(self, color_key: str, bold=False) -> QTextCharFormat:
        f = QTextCharFormat()
        f.setForeground(QColor(self._t.get(color_key, '#ebdbb2')))
        if bold:
            font = QFont()
            font.setBold(True)
            f.setFont(font)
        return f

    def _build_rules(self):
        t = self._t
        self._rules = [
            # Errors
            (re.compile(r'(?i)(error|fatal|failed|failure|exception|traceback)',
                        re.IGNORECASE),
             self._fmt('red', bold=True)),
            # Warnings
            (re.compile(r'(?i)(warning|warn|deprecated)', re.IGNORECASE),
             self._fmt('yellow')),
            # Success
            (re.compile(r'(?i)(success|passed|ok\b|done\b|complete)',
                        re.IGNORECASE),
             self._fmt('green')),
            # Section headers (GitLab CI section markers)
            (re.compile(r'^section_(start|end):\d+:\S+', re.MULTILINE),
             self._fmt('bg4')),
            # Timestamps
            (re.compile(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}'),
             self._fmt('fg4')),
            # Job/stage names in brackets
            (re.compile(r'\[[\w\-:]+\]'),
             self._fmt('aqua')),
            # File paths
            (re.compile(r'[\w./\-]+\.(?:py|rb|yml|yaml|sh|tf|go|rs)\b'),
             self._fmt('blue')),
            # Line numbers
            (re.compile(r'\bline \d+\b', re.IGNORECASE),
             self._fmt('orange')),
        ]

    def highlightBlock(self, text: str):
        for pattern, fmt in self._rules:
            for m in pattern.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), fmt)

    def rehighlight_theme(self, theme: dict):
        self._t = theme
        self._build_rules()
        self.rehighlight()


# ── Log viewer dock ───────────────────────────────────────────────────────────

class LogViewerDock(QDockWidget):

    send_to_chat = pyqtSignal(str)  # emits log text for chat injection

    def __init__(self, parent=None):
        super().__init__("Log Viewer", parent)
        self.setObjectName("log_viewer_dock")
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable  |
            QDockWidget.DockWidgetFeature.DockWidgetMovable   |
            QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        self._t           = get_theme()
        self._current_log = ""
        self._source      = ""

        self._build_ui()
        self._apply_theme(self._t)
        theme_signals.theme_changed.connect(self._apply_theme)

    # ── UI ────────────────────────────────────────────────────────────────

    def _build_ui(self):
        container = QWidget()
        layout    = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toolbar
        toolbar = QWidget()
        toolbar.setFixedHeight(32)
        tl = QHBoxLayout(toolbar)
        tl.setContentsMargins(8, 0, 8, 0)
        tl.setSpacing(6)

        self._title_label = QLabel("No log loaded")
        self._title_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred
        )
        tl.addWidget(self._title_label)

        self._chat_btn = QPushButton("💬 Send to Chat")
        self._chat_btn.setFixedHeight(22)
        self._chat_btn.setToolTip("Send log to AI chat for analysis")
        self._chat_btn.clicked.connect(self._send_to_chat)
        self._chat_btn.setEnabled(False)
        tl.addWidget(self._chat_btn)

        self._jump_btn = QPushButton("⤵ Jump to Error")
        self._jump_btn.setFixedHeight(22)
        self._jump_btn.setToolTip("Jump to first error in log")
        self._jump_btn.clicked.connect(self._jump_to_error)
        self._jump_btn.setEnabled(False)
        tl.addWidget(self._jump_btn)

        clear_btn = QPushButton("✕")
        clear_btn.setFixedSize(22, 22)
        clear_btn.setToolTip("Clear log")
        clear_btn.clicked.connect(self.clear)
        tl.addWidget(clear_btn)

        layout.addWidget(toolbar)

        # Log text area
        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        font = QFont("monospace")
        font.setPointSize(9)
        self._log.setFont(font)
        layout.addWidget(self._log)

        # Highlighter
        self._highlighter = _LogHighlighter(self._log.document(), self._t)

        self.setWidget(container)

    # ── Public API ────────────────────────────────────────────────────────

    def show_log(self, title: str, text: str, source: str = ""):
        """
        Display a log. Strips ANSI codes, highlights, scrolls to first error.
        source: optional tag for chat context (e.g. "gitlab", "ansible")
        """
        self._current_log = text
        self._source      = source
        self.setWindowTitle(f"Log — {title}")
        self._title_label.setText(title)

        # Strip ANSI escape codes
        clean = re.sub(r'\x1b\[[0-9;]*[mGKHF]', '', text)
        # Strip GitLab CI section markers
        clean = re.sub(r'section_(start|end):\d+:[^\r\n]+\r?', '', clean)

        self._log.setPlainText(clean)
        self._chat_btn.setEnabled(True)
        self._jump_btn.setEnabled(True)

        # Auto-scroll to first error
        self._jump_to_error()
        self.show()
        self.raise_()

    def append_log(self, text: str):
        """Append text to the current log (for streaming output)."""
        clean = re.sub(r'\x1b\[[0-9;]*[mGKHF]', '', text)
        self._log.moveCursor(QTextCursor.MoveOperation.End)
        self._log.insertPlainText(clean)
        self._log.moveCursor(QTextCursor.MoveOperation.End)
        self._current_log += clean

    def clear(self):
        self._log.clear()
        self._current_log = ""
        self._title_label.setText("No log loaded")
        self._chat_btn.setEnabled(False)
        self._jump_btn.setEnabled(False)

    # ── Actions ───────────────────────────────────────────────────────────

    def _jump_to_error(self):
        """Scroll to first ERROR/FATAL/Traceback line."""
        doc  = self._log.document()
        text = doc.toPlainText()
        for pattern in [r'(?im)^.*\b(error|fatal|traceback|failed)\b.*$']:
            m = re.search(pattern, text)
            if m:
                cursor = self._log.textCursor()
                cursor.setPosition(m.start())
                self._log.setTextCursor(cursor)
                self._log.centerCursor()
                return
        # No error found — scroll to end
        self._log.moveCursor(QTextCursor.MoveOperation.End)

    def _send_to_chat(self):
        if not self._current_log:
            return
        source_tag = f"[{self._source}] " if self._source else ""
        title      = self._title_label.text()
        context    = (
            f"{source_tag}Log: {title}\n"
            f"---\n"
            f"{self._current_log[-6000:]}"  # last 6000 chars
        )
        self.send_to_chat.emit(context)

    # ── Theme ─────────────────────────────────────────────────────────────

    def _apply_theme(self, t: dict):
        self._t = t
        self.setStyleSheet(build_dock_stylesheet(t))
        self._log.setStyleSheet(f"""
            QPlainTextEdit {{
                background: {t.get('bg0_hard', '#1d2021')};
                color: {t.get('fg1', '#ebdbb2')};
                border: none;
                font-family: monospace;
                font-size: 9pt;
                selection-background-color: {t.get('bg3', '#665c54')};
            }}
            QScrollBar:vertical {{
                background: {t.get('bg1', '#3c3836')};
                width: 8px; border: none;
            }}
            QScrollBar::handle:vertical {{
                background: {t.get('bg3', '#665c54')};
                border-radius: 4px; min-height: 20px;
            }}
            QScrollBar:horizontal {{
                background: {t.get('bg1', '#3c3836')};
                height: 8px; border: none;
            }}
            QScrollBar::handle:horizontal {{
                background: {t.get('bg3', '#665c54')};
                border-radius: 4px; min-width: 20px;
            }}
            QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
        """)
        self._title_label.setStyleSheet(f"""
            QLabel {{
                color: {t.get('fg1', '#ebdbb2')};
                font-size: 9pt; font-weight: bold;
                background: transparent;
            }}
        """)
        toolbar_style = f"""
            QWidget {{
                background: {t.get('bg2', '#504945')};
                border-bottom: 1px solid {t.get('bg3', '#665c54')};
            }}
        """
        self.widget().layout().itemAt(0).widget().setStyleSheet(toolbar_style)

        btn_style = f"""
            QPushButton {{
                background: {t.get('bg3', '#665c54')};
                color: {t.get('fg1', '#ebdbb2')};
                border: none; border-radius: 3px;
                padding: 2px 8px; font-size: 8pt;
            }}
            QPushButton:hover {{
                background: {t.get('bg4', '#7c6f64')};
            }}
            QPushButton:disabled {{
                color: {t.get('bg4', '#7c6f64')};
            }}
        """
        for btn in self.widget().findChildren(QPushButton):
            btn.setStyleSheet(btn_style)

        if hasattr(self, '_highlighter'):
            self._highlighter.rehighlight_theme(t)

    def closeEvent(self, event):
        try:
            theme_signals.theme_changed.disconnect(self._apply_theme)
        except (RuntimeError, TypeError):
            pass
        super().closeEvent(event)