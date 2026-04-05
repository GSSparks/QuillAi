"""
ui/rename_dialog.py

Inline rename popup for LSP textDocument/rename.

Appears just below the cursor, pre-filled with the current symbol name.
Enter confirms, Escape cancels.

Usage:
    dialog = RenamePopup(editor, current_name)
    dialog.rename_confirmed.connect(lambda new_name: ...)
    dialog.show_at_cursor()
"""

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLineEdit, QLabel
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent

from ui.theme import get_theme, theme_signals, build_rename_dialog_stylesheet, FONT_UI, FONT_CODE


class RenamePopup(QWidget):
    """
    Small floating input that appears below the cursor for symbol rename.
    Never steals permanent focus — dismisses cleanly on Escape or focus loss.
    """

    rename_confirmed = pyqtSignal(str)   # new name
    cancelled        = pyqtSignal()

    def __init__(self, editor, current_name: str):
        super().__init__(editor.viewport())
        self.setObjectName("RenamePopup")
        self.setWindowFlags(Qt.WindowType.Widget)

        self._editor = editor
        self._current_name = current_name

        t = get_theme()
        self._build_ui(t)
        self._apply_theme(t)
        theme_signals.theme_changed.connect(self._apply_theme)

    def _build_ui(self, t: dict):
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(6)

        self._label = QLabel("Rename:")
        self._label.setObjectName("renameLabel")
        layout.addWidget(self._label)

        self._input = QLineEdit()
        self._input.setObjectName("renameInput")
        self._input.setText(self._current_name)
        self._input.selectAll()
        self._input.setMinimumWidth(180)
        self._input.returnPressed.connect(self._confirm)
        self._input.installEventFilter(self)
        layout.addWidget(self._input)

        self._hint = QLabel("↵ rename  esc cancel")
        self._hint.setObjectName("renameHint")
        layout.addWidget(self._hint)

        self.adjustSize()

    def _apply_theme(self, t: dict):
        bg     = t.get("bg1",      "#3c3836")
        fg     = t.get("fg1",      "#ebdbb2")
        fg_dim = t.get("fg4",      "#a89984")
        border = t.get("border_focus", "#fabd2f")
        input_bg = t.get("bg0_hard", "#1d2021")
        accent   = t.get("accent",   "#fabd2f")

        self.setStyleSheet(f"""
            QWidget#RenamePopup {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 5px;
            }}
            QLabel#renameLabel {{
                color: {fg_dim};
                font-family: {FONT_UI};
                font-size: 9pt;
                background: transparent;
            }}
            QLineEdit#renameInput {{
                background-color: {input_bg};
                color: {fg};
                border: 1px solid {border};
                border-radius: 3px;
                font-family: {FONT_CODE};
                font-size: 10pt;
                padding: 3px 7px;
            }}
            QLabel#renameHint {{
                color: {fg_dim};
                font-family: {FONT_UI};
                font-size: 8pt;
                background: transparent;
            }}
        """)

    # ── Positioning ───────────────────────────────────────────────────────

    def show_at_cursor(self):
        """Position below cursor in viewport coords and show."""
        editor      = self._editor
        cursor_rect = editor.cursorRect()
        vp          = editor.viewport()

        x = cursor_rect.left()
        y = cursor_rect.bottom() + 4

        self.adjustSize()

        # Keep within viewport
        if x + self.width() > vp.width():
            x = max(0, vp.width() - self.width())
        if y + self.height() > vp.height():
            y = cursor_rect.top() - self.height() - 4
        y = max(0, y)

        self.move(x, y)
        self.show()
        self.raise_()
        self._input.setFocus()

    # ── Event handling ────────────────────────────────────────────────────

    def eventFilter(self, obj, event):
        if obj is self._input and event.type() == event.Type.KeyPress:
            if event.key() == Qt.Key.Key_Escape:
                self._cancel()
                return True
        return super().eventFilter(obj, event)

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        # Small delay so clicking the editor doesn't double-fire
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(100, self._cancel)

    def _confirm(self):
        new_name = self._input.text().strip()
        if new_name and new_name != self._current_name:
            self.rename_confirmed.emit(new_name)
        else:
            self.cancelled.emit()
        self._dismiss()

    def _cancel(self):
        self.cancelled.emit()
        self._dismiss()

    def _dismiss(self):
        try:
            self.hide()
            self.deleteLater()
        except RuntimeError:
            pass