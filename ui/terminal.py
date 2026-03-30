"""
ui/terminal.py
──────────────
Embedded terminal dock for QuillAI.

Tries to use qtermwidget (full PTY-based terminal with ANSI support).
Falls back to a QProcess-driven interactive shell widget if qtermwidget
is not installed — still functional but without full ANSI rendering.

Installation (qtermwidget):
    pip install pyqtermwidget          # Linux/macOS
    apt install python3-qtermwidget    # Debian/Ubuntu

Usage (in main.py):
    from ui.terminal import TerminalDock
    self.terminal_dock = TerminalDock(self)
    self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.terminal_dock)
    self.terminal_dock.hide()

Toggle with Ctrl+`:
    QShortcut(QKeySequence("Ctrl+`"), self).activated.connect(self.toggle_terminal)
"""

import os
import sys
from PyQt6.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QPlainTextEdit,
    QLineEdit, QLabel, QHBoxLayout,
)
from PyQt6.QtCore import Qt, QProcess, QProcessEnvironment
from PyQt6.QtGui import QFont, QTextCursor, QColor

from ui.theme import (
    get_theme, theme_signals,
    build_terminal_stylesheet,
    build_dock_stylesheet,
    QFONT_CODE,
)

# ─────────────────────────────────────────────────────────────────────────────
# Try to import qtermwidget
# ─────────────────────────────────────────────────────────────────────────────

try:
    from qtermwidget import QTermWidget
    HAS_QTERM = True
except ImportError:
    HAS_QTERM = False


# ─────────────────────────────────────────────────────────────────────────────
# Fallback terminal (QProcess-driven interactive shell)
# ─────────────────────────────────────────────────────────────────────────────

class FallbackTerminal(QWidget):
    """
    A simple interactive shell using QProcess.
    Not a full VTE — no ANSI cursor movement — but handles stdin/stdout/stderr
    and preserves a scrollback buffer.  Good enough for running scripts,
    git commands, pip installs, etc.
    """

    def __init__(self, cwd: str = None, parent=None):
        super().__init__(parent)
        self.setObjectName("terminalContainer")
        self._cwd = cwd or os.path.expanduser("~")
        self._history: list[str] = []
        self._history_idx: int = -1

        self._setup_ui()
        self._start_shell()

    # ── UI ────────────────────────────────────────────────────────────────

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setFont(QFont(QFONT_CODE, 10))
        self.output.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.output.setMaximumBlockCount(5000)   # limit scrollback
        layout.addWidget(self.output)

        # Input row: prompt label + line edit
        input_row = QHBoxLayout()
        input_row.setContentsMargins(0, 0, 0, 0)
        input_row.setSpacing(0)

        self.prompt_label = QLabel("$ ")
        self.prompt_label.setFont(QFont(QFONT_CODE, 10))

        self.input_line = QLineEdit()
        self.input_line.setFont(QFont(QFONT_CODE, 10))
        self.input_line.setPlaceholderText("Enter command…")
        self.input_line.returnPressed.connect(self._send_command)
        self.input_line.installEventFilter(self)

        input_row.addWidget(self.prompt_label)
        input_row.addWidget(self.input_line)

        input_widget = QWidget()
        input_widget.setLayout(input_row)
        layout.addWidget(input_widget)

    # ── Shell process ─────────────────────────────────────────────────────

    def _start_shell(self):
        self._process = QProcess(self)
        self._process.setWorkingDirectory(self._cwd)

        env = QProcessEnvironment.systemEnvironment()
        env.insert("TERM", "xterm-256color")
        self._process.setProcessEnvironment(env)

        self._process.readyReadStandardOutput.connect(self._on_stdout)
        self._process.readyReadStandardError.connect(self._on_stderr)
        self._process.finished.connect(self._on_finished)

        shell = os.environ.get("SHELL", "/bin/bash")
        # -i = interactive so aliases/functions are loaded
        # -s = read from stdin
        self._process.start(shell, ["-i", "-s"])

        self._append(f"QuillAI Terminal  ({shell})\n", "#888888")

    def _send_command(self):
        cmd = self.input_line.text()
        self.input_line.clear()

        if cmd.strip():
            self._history.insert(0, cmd)
            self._history_idx = -1

        self._append(f"$ {cmd}\n", "#aaaaaa")

        if self._process.state() == QProcess.ProcessState.Running:
            self._process.write((cmd + "\n").encode())
        else:
            self._append("[shell exited — restart with Ctrl+`]\n", "#ff6666")

    def _on_stdout(self):
        data = bytes(self._process.readAllStandardOutput()).decode("utf-8", errors="replace")
        self._append(data)

    def _on_stderr(self):
        data = bytes(self._process.readAllStandardError()).decode("utf-8", errors="replace")
        self._append(data, "#ff9966")

    def _on_finished(self, exit_code, exit_status):
        self._append(f"\n[process exited with code {exit_code}]\n", "#888888")

    def _append(self, text: str, color: str = None):
        """Append text to the output widget, stripping basic ANSI sequences."""
        import re
        # Strip ANSI escape codes — we can't render them in QPlainTextEdit
        clean = re.sub(r'\x1b\[[0-9;]*[mABCDEFGHJKSTfsu]', '', text)
        clean = re.sub(r'\x1b\][^\x07]*\x07', '', clean)   # OSC sequences
        clean = re.sub(r'\x1b[()][AB012]', '', clean)       # charset
        clean = clean.replace('\r\n', '\n').replace('\r', '\n')

        cursor = self.output.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        if color:
            fmt = cursor.charFormat()
            fmt.setForeground(QColor(color))
            cursor.setCharFormat(fmt)
        cursor.insertText(clean)
        self.output.setTextCursor(cursor)
        self.output.ensureCursorVisible()

    # ── History navigation ────────────────────────────────────────────────

    def eventFilter(self, obj, event):
        from PyQt6.QtCore import QEvent
        if obj == self.input_line and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key == Qt.Key.Key_Up:
                self._history_idx = min(
                    self._history_idx + 1, len(self._history) - 1
                )
                if self._history_idx >= 0:
                    self.input_line.setText(self._history[self._history_idx])
                return True
            if key == Qt.Key.Key_Down:
                self._history_idx = max(self._history_idx - 1, -1)
                self.input_line.setText(
                    self._history[self._history_idx]
                    if self._history_idx >= 0 else ""
                )
                return True
        return super().eventFilter(obj, event)

    # ── Public ────────────────────────────────────────────────────────────

    def set_cwd(self, path: str):
        """Change the working directory for new commands."""
        if os.path.isdir(path):
            self._cwd = path
            if self._process.state() == QProcess.ProcessState.Running:
                self._process.write(f"cd {path!r}\n".encode())

    def restart(self):
        if self._process.state() == QProcess.ProcessState.Running:
            self._process.kill()
            self._process.waitForFinished(500)
        self.output.clear()
        self._start_shell()

    def apply_styles(self, t: dict):
        self.setStyleSheet(build_terminal_stylesheet(t))
        color = t.get('fg4', '#888888')
        self.prompt_label.setStyleSheet(f"color: {color}; padding: 4px 4px 4px 8px;")


# ─────────────────────────────────────────────────────────────────────────────
# QTermWidget wrapper (full PTY terminal)
# ─────────────────────────────────────────────────────────────────────────────

class QtermWidget(QWidget):
    """Thin wrapper around QTermWidget that follows the same interface."""

    def __init__(self, cwd: str = None, parent=None):
        super().__init__(parent)
        self._cwd = cwd or os.path.expanduser("~")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._term = QTermWidget(1, self)   # 1 = start shell immediately
        self._term.setWorkingDirectory(self._cwd)
        self._term.setScrollBarPosition(QTermWidget.ScrollBarPosition.ScrollBarRight)
        self._term.setColorScheme("Linux")
        self._term.setTerminalFont(QFont(QFONT_CODE, 10))
        layout.addWidget(self._term)

    def set_cwd(self, path: str):
        if os.path.isdir(path):
            self._term.sendText(f"cd {path!r}\n")

    def restart(self):
        self._term.sendText("exit\n")

    def apply_styles(self, t: dict):
        # QTermWidget has its own colour scheme system; set background via palette
        bg = t.get('bg0_hard', '#1d2021')
        fg = t.get('fg1',      '#ebdbb2')
        # Map a handful of palette keys to the terminal colour scheme
        colors = [
            bg,           # 0  background
            t['red'],     # 1
            t['green'],   # 2
            t['yellow'],  # 3
            t['blue'],    # 4
            t['purple'],  # 5
            t['aqua'],    # 6
            fg,           # 7  foreground
            t['bg3'],     # 8  bright black
            t['red'],     # 9
            t['green'],   # 10
            t['yellow'],  # 11
            t['blue'],    # 12
            t['purple'],  # 13
            t['aqua'],    # 14
            t['fg0'],     # 15 bright white
        ]
        try:
            for i, c in enumerate(colors):
                self._term.setColorTableEntry(i, QColor(c))
            self._term.update()
        except Exception:
            pass   # some versions don't expose setColorTableEntry


# ─────────────────────────────────────────────────────────────────────────────
# Terminal Dock
# ─────────────────────────────────────────────────────────────────────────────

class TerminalDock(QDockWidget):
    """
    QDockWidget wrapping whichever terminal backend is available.
    Drop into the main window with:

        self.terminal_dock = TerminalDock(self)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea,
                           self.terminal_dock)
    """

    def __init__(self, parent=None):
        super().__init__("Terminal", parent)
        self.setObjectName("terminal_dock")
        self.parent_window = parent

        self._cwd = self._infer_cwd()

        # Pick backend
        if HAS_QTERM:
            self._terminal = QtermWidget(cwd=self._cwd, parent=self)
        else:
            self._terminal = FallbackTerminal(cwd=self._cwd, parent=self)

        self.setWidget(self._terminal)
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable |
            QDockWidget.DockWidgetFeature.DockWidgetMovable |
            QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )

        t = get_theme()
        self.apply_styles(t)
        theme_signals.theme_changed.connect(self._on_theme_changed)

    # ── Theme ─────────────────────────────────────────────────────────────

    def _on_theme_changed(self, t: dict):
        self.apply_styles(t)

    def apply_styles(self, t: dict):
        self.setStyleSheet(build_dock_stylesheet(t))
        self._terminal.apply_styles(t)

    # ── Helpers ───────────────────────────────────────────────────────────

    def _infer_cwd(self) -> str:
        """Use the git repo path or project root if available."""
        mw = self.parent_window
        if mw and hasattr(mw, 'git_dock') and mw.git_dock.repo_path:
            return mw.git_dock.repo_path
        if mw and hasattr(mw, 'file_model') and hasattr(mw, 'tree_view'):
            root = mw.file_model.filePath(mw.tree_view.rootIndex())
            if root and os.path.isdir(root):
                return root
        return os.path.expanduser("~")

    def set_cwd(self, path: str):
        """Called by the main window when the project root changes."""
        self._terminal.set_cwd(path)

    def restart(self):
        self._terminal.restart()

    @property
    def backend(self) -> str:
        return "qtermwidget" if HAS_QTERM else "fallback"

    # ── Cleanup ───────────────────────────────────────────────────────────

    def closeEvent(self, event):
        try:
            theme_signals.theme_changed.disconnect(self._on_theme_changed)
        except RuntimeError:
            pass
        super().closeEvent(event)