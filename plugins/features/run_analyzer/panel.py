"""
panel.py

Results panel for the run analyzer.
Shows a live feed of parsed events with severity indicators,
clickable file hints, and a clear button.
"""

import os
from PyQt6.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QListWidget, QListWidgetItem, QPushButton, QLabel,
    QSizePolicy, QFrame,
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QColor, QFont

from ui.theme import get_theme, theme_signals, build_dock_stylesheet
from plugins.features.run_analyzer.parsers import RunEvent, Severity


_SEV_COLORS = {
    Severity.INFO:    ("fg4",    "▸"),
    Severity.SUCCESS: ("green",  "✓"),
    Severity.WARNING: ("yellow", "⚠"),
    Severity.ERROR:   ("red",    "✗"),
}


class RunAnalyzerPanel(QDockWidget):

    jump_requested    = pyqtSignal(str)       # search term
    fix_requested     = pyqtSignal(object)    # RunEvent — ask AI to fix
    chat_requested    = pyqtSignal(str, str)  # prompt, context

    def __init__(self, parent=None):
        super().__init__("Run Analyzer", parent)
        self.setObjectName("run_analyzer_dock")
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable  |
            QDockWidget.DockWidgetFeature.DockWidgetMovable   |
            QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )

        self._events: list[RunEvent] = []
        self._t = get_theme()

        self._build_ui()
        self._apply_theme(self._t)
        theme_signals.theme_changed.connect(self._apply_theme)

    def _build_ui(self):
        container = QWidget()
        layout    = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QWidget()
        header.setFixedHeight(32)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(8, 0, 4, 0)

        self._status = QLabel("Watching terminal output…")
        self._status.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        hl.addWidget(self._status)

        clear_btn = QPushButton("✕ Clear")
        clear_btn.setFixedHeight(22)
        clear_btn.clicked.connect(self.clear)
        hl.addWidget(clear_btn)

        layout.addWidget(header)

        # Inline suggestion banner — hidden until a failure occurs
        self._banner = QFrame()
        self._banner.setFrameShape(QFrame.Shape.NoFrame)
        bl = QHBoxLayout(self._banner)
        bl.setContentsMargins(8, 4, 8, 4)

        self._banner_label = QLabel("")
        self._banner_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        self._banner_label.setWordWrap(True)
        bl.addWidget(self._banner_label)

        self._fix_btn = QPushButton("💡 Ask AI to fix")
        self._fix_btn.setFixedHeight(26)
        self._fix_btn.clicked.connect(self._on_fix_clicked)
        bl.addWidget(self._fix_btn)

        self._banner_event = None
        self._banner.hide()
        layout.addWidget(self._banner)

        # Event list
        self._list = QListWidget()
        self._list.setAlternatingRowColors(False)
        self._list.setSpacing(1)
        self._list.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self._list)

        self.setWidget(container)

    def _apply_theme(self, t: dict):
        self._t = t
        self.setStyleSheet(build_dock_stylesheet(t))
        self._restyle_list()
        self._restyle_banner()

    def _restyle_list(self):
        t = self._t
        self._list.setStyleSheet(f"""
            QListWidget {{
                background: {t.get('bg0', '#282828')};
                border: none;
                outline: none;
            }}
            QListWidget::item {{
                padding: 4px 8px;
                border-bottom: 1px solid {t.get('bg1', '#3c3836')};
            }}
            QListWidget::item:selected {{
                background: {t.get('bg2', '#504945')};
            }}
        """)

    def _restyle_banner(self):
        t = self._t
        self._banner.setStyleSheet(f"""
            QFrame {{
                background: {t.get('bg1', '#3c3836')};
                border-bottom: 1px solid {t.get('bg3', '#665c54')};
            }}
        """)
        self._banner_label.setStyleSheet(
            f"color: {t.get('yellow', '#fabd2f')}; font-size: 9pt;"
        )
        self._fix_btn.setStyleSheet(f"""
            QPushButton {{
                background: {t.get('bg2', '#504945')};
                color: {t.get('fg1', '#ebdbb2')};
                border: 1px solid {t.get('bg3', '#665c54')};
                border-radius: 3px;
                padding: 2px 10px;
                font-size: 9pt;
            }}
            QPushButton:hover {{
                background: {t.get('bg3', '#665c54')};
            }}
        """)

    # ── Public API ────────────────────────────────────────────────────────

    def add_event(self, event: RunEvent):
        self._events.append(event)
        self._add_item(event)
        if event.severity == Severity.ERROR and not self.isVisible():
            self.show()
            self.raise_()
        self._update_status()

    def show_suggestion(self, event: RunEvent, past_fix: str = None):
        """Show the inline AI suggestion banner for a failure."""
        self._banner_event = event
        if past_fix:
            self._banner_label.setText(
                f"⟳  Similar failure fixed before — AI has the context"
            )
        else:
            task = event.task_name or event.title
            self._banner_label.setText(
                f"✗  Failed: {task[:60]}{'…' if len(task) > 60 else ''}"
            )
        self._banner.show()

    def hide_suggestion(self):
        self._banner.hide()
        self._banner_event = None

    def clear(self):
        self._events.clear()
        self._list.clear()
        self._banner.hide()
        self._banner_event = None
        self._status.setText("Watching terminal output…")

    # ── Banner ────────────────────────────────────────────────────────────

    def _on_fix_clicked(self):
        if self._banner_event:
            self.fix_requested.emit(self._banner_event)

    # ── Item rendering ────────────────────────────────────────────────────

    def _add_item(self, event: RunEvent):
        t          = self._t
        color_key, icon = _SEV_COLORS.get(event.severity, ("fg4", "▸"))
        color      = QColor(t.get(color_key, '#a89984'))

        tool_badge = f"[{event.tool}] " if event.tool else ""
        text       = f"{icon}  {tool_badge}{event.title}"
        if event.detail:
            first_line = event.detail.split('\n')[0]
            if len(first_line) > 80:
                first_line = first_line[:77] + "…"
            text += f"\n   {first_line}"

        item = QListWidgetItem(text)
        item.setForeground(color)
        item.setData(Qt.ItemDataRole.UserRole, event)

        if event.file_hint or event.task_name or event.resource:
            item.setToolTip(
                f"Double-click to search for: "
                f"{event.file_hint or event.task_name or event.resource}"
            )
            font = item.font()
            font.setUnderline(True)
            item.setFont(font)

        self._list.addItem(item)
        self._list.scrollToBottom()

    def _on_item_double_clicked(self, item: QListWidgetItem):
        event = item.data(Qt.ItemDataRole.UserRole)
        if not event:
            return
        hint = event.file_hint or event.task_name or event.resource
        if hint:
            self.jump_requested.emit(hint)

    def _update_status(self):
        errors   = sum(1 for e in self._events if e.severity == Severity.ERROR)
        warnings = sum(1 for e in self._events if e.severity == Severity.WARNING)
        t        = self._t
        if errors:
            self._status.setStyleSheet(f"color: {t.get('red', '#fb4934')};")
            self._status.setText(
                f"{errors} error{'s' if errors > 1 else ''}  "
                f"{warnings} warning{'s' if warnings != 1 else ''}"
            )
        elif warnings:
            self._status.setStyleSheet(f"color: {t.get('yellow', '#fabd2f')};")
            self._status.setText(
                f"{warnings} warning{'s' if warnings != 1 else ''}"
            )
        else:
            self._status.setStyleSheet(f"color: {t.get('green', '#b8bb26')};")
            self._status.setText(
                f"{len(self._events)} event{'s' if len(self._events) != 1 else ''}"
            )

    def closeEvent(self, event):
        try:
            theme_signals.theme_changed.disconnect(self._apply_theme)
        except (RuntimeError, TypeError):
            pass
        super().closeEvent(event)