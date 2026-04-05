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
    QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal
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

    # Emitted when user clicks a result with a file hint
    jump_requested = pyqtSignal(str)   # search term

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

    # ── UI ────────────────────────────────────────────────────────────────

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

        # Event list
        self._list = QListWidget()
        self._list.setAlternatingRowColors(False)
        self._list.setSpacing(1)
        self._list.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self._list)

        self.setWidget(container)

    # ── Theme ─────────────────────────────────────────────────────────────

    def _apply_theme(self, t: dict):
        self._t = t
        self.setStyleSheet(build_dock_stylesheet(t))
        self._restyle_list()

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

    # ── Public API ────────────────────────────────────────────────────────

    def add_event(self, event: RunEvent):
        self._events.append(event)
        self._add_item(event)
        # Auto-show on first error
        if event.severity == Severity.ERROR and not self.isVisible():
            self.show()
            self.raise_()
        self._update_status()

    def clear(self):
        self._events.clear()
        self._list.clear()
        self._status.setText("Watching terminal output…")

    # ── Item rendering ────────────────────────────────────────────────────

    def _add_item(self, event: RunEvent):
        t          = self._t
        color_key, icon = _SEV_COLORS.get(event.severity, ("fg4", "▸"))
        color      = QColor(t.get(color_key, '#a89984'))

        # Main line
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
            self._status.setText(f"{errors} error{'s' if errors > 1 else ''}  "
                                  f"{warnings} warning{'s' if warnings != 1 else ''}")
        elif warnings:
            self._status.setStyleSheet(f"color: {t.get('yellow', '#fabd2f')};")
            self._status.setText(f"{warnings} warning{'s' if warnings != 1 else ''}")
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