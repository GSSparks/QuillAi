"""
panel.py

Ansible Playbook Debugger panel — shows a live host×task execution
matrix, full verbose error detail, and AI-assisted fixes.

Layout:
  ┌─────────────────────────────────────────────────────┐
  │ ▶ Play: Deploy webservers          [3 hosts] [Clear] │
  ├────────────────────────────────────────────────────  │
  │ Task                    │ web-01 │ web-02 │ web-03   │
  │ ─────────────────────── │ ────── │ ────── │ ───────  │
  │ Gather facts            │  ✓ ok  │  ✓ ok  │  ✓ ok   │
  │ Install nginx           │  ✓ ok  │  ✗ ERR │  ✓ ok   │ ← click
  │ Start nginx             │  –     │  –     │  –       │
  ├─────────────────────────────────────────────────────┤
  │ ✗ Failed: Install nginx on web-02                   │
  │   msg: No package nginx available                   │
  │   rc: 1  stderr: ...                                │
  │                        [Compare hosts] [💡 Ask AI]  │
  └─────────────────────────────────────────────────────┘
"""

import os
from PyQt6.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QTableWidget, QTableWidgetItem, QPushButton, QLabel,
    QSizePolicy, QFrame, QTextEdit, QHeaderView, QAbstractItemView,
    QScrollArea,
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QColor, QFont, QBrush

from ui.theme import get_theme, theme_signals, build_dock_stylesheet, FONT_CODE, FONT_UI
from plugins.features.run_analyzer.parsers import RunEvent, Severity, HostResult


# Status display config: (icon, theme_color_key, sort_priority)
_STATUS_CFG = {
    "ok":          ("✓", "green",  3),
    "changed":     ("~", "yellow", 2),
    "failed":      ("✗", "red",    0),
    "unreachable": ("!", "red",    0),
    "skipped":     ("–", "fg4",    4),
    "pending":     ("·", "fg4",    5),
}


class HostTaskMatrix(QTableWidget):
    """
    Live host×task grid. Rows = tasks, columns = hosts.
    Cells are colored by status and clickable for detail.
    """
    cell_selected = pyqtSignal(object, str)  # RunEvent, host

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tasks: list[str]  = []   # ordered task names
        self._hosts: list[str]  = []   # ordered host names
        # (task, host) -> (status, RunEvent)
        self._data: dict        = {}
        self._t = get_theme()

        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.verticalHeader().setDefaultSectionSize(24)
        self.horizontalHeader().setDefaultSectionSize(72)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.setShowGrid(True)
        self.cellClicked.connect(self._on_cell_clicked)
        self._apply_theme(self._t)

    def _apply_theme(self, t: dict):
        self._t = t
        self.setStyleSheet(f"""
            QTableWidget {{
                background: {t.get('bg0', '#282828')};
                gridline-color: {t.get('bg2', '#504945')};
                color: {t.get('fg1', '#ebdbb2')};
                border: none;
                font-family: '{FONT_CODE}';
                font-size: 9pt;
            }}
            QHeaderView::section {{
                background: {t.get('bg1', '#3c3836')};
                color: {t.get('fg2', '#d5c4a1')};
                border: 1px solid {t.get('bg2', '#504945')};
                padding: 2px 6px;
                font-size: 8pt;
            }}
            QTableWidget::item:selected {{
                background: {t.get('bg3', '#665c54')};
            }}
        """)
        self._refresh_cells()

    def add_host(self, host: str):
        if host not in self._hosts:
            self._hosts.append(host)
            self._rebuild_table()

    def add_task(self, task: str):
        if task not in self._tasks:
            self._tasks.append(task)
            self._rebuild_table()

    def update_cell(self, task: str, host: str, status: str, event: RunEvent):
        self.add_host(host)
        self.add_task(task)
        self._data[(task, host)] = (status, event)
        self._refresh_cells()

    def _rebuild_table(self):
        self.setRowCount(len(self._tasks))
        self.setColumnCount(len(self._hosts))
        self.setHorizontalHeaderLabels(self._hosts)
        self.setVerticalHeaderLabels(self._tasks)
        self._refresh_cells()

    def _refresh_cells(self):
        t = self._t
        for r, task in enumerate(self._tasks):
            for c, host in enumerate(self._hosts):
                key = (task, host)
                if key in self._data:
                    status, event = self._data[key]
                else:
                    status, event = "pending", None

                icon, color_key, _ = _STATUS_CFG.get(
                    status, ("·", "fg4", 5)
                )
                color = t.get(color_key, "#a89984")

                item = QTableWidgetItem(icon)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setForeground(QBrush(QColor(color)))
                item.setData(Qt.ItemDataRole.UserRole, (task, host, status, event))

                # Background tint for errors
                if status in ("failed", "unreachable"):
                    item.setBackground(QBrush(QColor(t.get("red", "#cc241d") + "22")))
                elif status == "changed":
                    item.setBackground(QBrush(QColor(t.get("yellow", "#d79921") + "22")))
                elif status == "ok":
                    item.setBackground(QBrush(QColor(t.get("bg0", "#282828"))))

                self.setItem(r, c, item)

    def _on_cell_clicked(self, row: int, col: int):
        item = self.item(row, col)
        if not item:
            return
        data = item.data(Qt.ItemDataRole.UserRole)
        if data:
            task, host, status, event = data
            if event:
                self.cell_selected.emit(event, host)

    def clear_all(self):
        self._tasks.clear()
        self._hosts.clear()
        self._data.clear()
        self.setRowCount(0)
        self.setColumnCount(0)


class DetailPane(QWidget):
    """Shows full error detail for a selected host+task."""
    fix_requested     = pyqtSignal(object)   # RunEvent
    compare_requested = pyqtSignal(object)   # RunEvent (compare host vars)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._event: RunEvent | None = None
        self._host:  str             = ""
        self._t = get_theme()
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Title bar
        title_bar = QFrame()
        title_bar.setFixedHeight(28)
        tl = QHBoxLayout(title_bar)
        tl.setContentsMargins(8, 0, 8, 0)

        self._title = QLabel("Select a failed cell for details")
        self._title.setStyleSheet(f"font-family: '{FONT_UI}'; font-size: 9pt;")
        tl.addWidget(self._title, stretch=1)

        self._compare_btn = QPushButton("⚖ Compare hosts")
        self._compare_btn.setFixedHeight(22)
        self._compare_btn.setVisible(False)
        self._compare_btn.clicked.connect(self._on_compare)
        tl.addWidget(self._compare_btn)

        self._fix_btn = QPushButton("💡 Ask AI")
        self._fix_btn.setFixedHeight(22)
        self._fix_btn.setVisible(False)
        self._fix_btn.clicked.connect(self._on_fix)
        tl.addWidget(self._fix_btn)

        layout.addWidget(title_bar)

        # Detail text
        self._detail = QTextEdit()
        self._detail.setReadOnly(True)
        self._detail.setFont(QFont(FONT_CODE, 9))
        self._detail.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        layout.addWidget(self._detail)

        self._apply_theme(self._t)

    def _apply_theme(self, t: dict):
        self._t = t
        self._detail.setStyleSheet(f"""
            QTextEdit {{
                background: {t.get('bg0_hard', '#1d2021')};
                color: {t.get('fg1', '#ebdbb2')};
                border: none;
                border-top: 1px solid {t.get('border', '#504945')};
                padding: 6px;
                font-family: '{FONT_CODE}';
            }}
        """)
        title_bar = self.layout().itemAt(0).widget()
        title_bar.setStyleSheet(
            f"background: {t.get('bg1', '#3c3836')};"
            f"border-top: 1px solid {t.get('border', '#504945')};"
        )
        for btn in (self._compare_btn, self._fix_btn):
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {t.get('bg2', '#504945')};
                    color: {t.get('fg1', '#ebdbb2')};
                    border: 1px solid {t.get('bg3', '#665c54')};
                    border-radius: 3px;
                    padding: 2px 8px;
                    font-size: 8pt;
                }}
                QPushButton:hover {{
                    background: {t.get('accent', '#689d6a')};
                    color: {t.get('bg0_hard', '#1d2021')};
                }}
            """)

    def show_result(self, event: RunEvent, host: str):
        self._event = event
        self._host  = host
        t = self._t

        hr: HostResult | None = event.host_results.get(host)

        # Title
        sev_color = t.get("red", "#cc241d") if event.severity == Severity.ERROR else t.get("fg1", "#ebdbb2")
        self._title.setText(f"<span style='color:{sev_color}'>"
                            f"✗ {event.task_name or event.title}</span>"
                            f" — <b>{host}</b>")
        self._title.setTextFormat(Qt.TextFormat.RichText)

        # Detail text
        lines = []
        if hr:
            if hr.msg:
                lines.append(f"msg:    {hr.msg}")
            if hr.rc != 0:
                lines.append(f"rc:     {hr.rc}")
            if hr.stdout and hr.stdout.strip():
                lines.append(f"\nstdout:\n{hr.stdout.strip()}")
            if hr.stderr and hr.stderr.strip():
                lines.append(f"\nstderr:\n{hr.stderr.strip()}")
            # Show other hosts' status for comparison
            other_hosts = {
                h: r for h, r in event.host_results.items()
                if h != host
            }
            if other_hosts:
                lines.append("\nOther hosts:")
                for h, r in other_hosts.items():
                    icon = "✓" if r.status == "ok" else "✗" if r.status == "failed" else "~"
                    lines.append(f"  {icon} {h}: {r.status}"
                                  + (f" — {r.msg[:60]}" if r.msg else ""))
        else:
            lines.append(event.detail or "No detail available")

        self._detail.setPlainText("\n".join(lines))

        # Show buttons
        self._fix_btn.setVisible(True)
        # Show compare button only if multiple hosts have different outcomes
        failed_hosts = [h for h, r in event.host_results.items()
                        if r.status in ("failed", "unreachable")]
        ok_hosts     = [h for h, r in event.host_results.items()
                        if r.status in ("ok", "changed")]
        self._compare_btn.setVisible(bool(failed_hosts and ok_hosts))

    def clear(self):
        self._event = None
        self._host  = ""
        self._title.setText("Select a failed cell for details")
        self._detail.clear()
        self._fix_btn.setVisible(False)
        self._compare_btn.setVisible(False)

    def _on_fix(self):
        if self._event:
            self.fix_requested.emit(self._event)

    def _on_compare(self):
        if self._event:
            self.compare_requested.emit(self._event)


class RunAnalyzerPanel(QDockWidget):
    """
    Ansible Playbook Debugger — host×task matrix + detail pane.
    """

    jump_requested    = pyqtSignal(str)       # search term → open file
    fix_requested     = pyqtSignal(object)    # RunEvent → AI fix
    compare_requested = pyqtSignal(object)    # RunEvent → host var compare

    def __init__(self, parent=None):
        super().__init__("Playbook Debugger", parent)
        self.setObjectName("run_analyzer_dock")
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable  |
            QDockWidget.DockWidgetFeature.DockWidgetMovable   |
            QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )

        self._events: list[RunEvent] = []
        self._t = get_theme()
        self._current_play = ""

        self._build_ui()
        self._apply_theme(self._t)
        theme_signals.theme_changed.connect(self._apply_theme)

    def _build_ui(self):
        container = QWidget()
        main_layout = QVBoxLayout(container)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Header ────────────────────────────────────────────────
        header = QFrame()
        header.setFixedHeight(30)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(8, 0, 8, 0)

        self._play_label = QLabel("Watching for ansible-playbook…")
        self._play_label.setStyleSheet(
            f"font-family: '{FONT_UI}'; font-size: 9pt; font-weight: bold;"
        )
        hl.addWidget(self._play_label, stretch=1)

        self._host_count = QLabel("")
        self._host_count.setStyleSheet(
            f"font-family: '{FONT_UI}'; font-size: 8pt; color: gray;"
        )
        hl.addWidget(self._host_count)

        self._verbose_hint = QLabel("")
        self._verbose_hint.setStyleSheet(
            f"font-family: '{FONT_UI}'; font-size: 8pt;"
        )
        hl.addWidget(self._verbose_hint)

        clear_btn = QPushButton("✕")
        clear_btn.setFixedSize(22, 22)
        clear_btn.setFlat(True)
        clear_btn.clicked.connect(self.clear)
        hl.addWidget(clear_btn)

        main_layout.addWidget(header)

        # ── Splitter: matrix top, detail bottom ───────────────────
        self._splitter = QSplitter(Qt.Orientation.Vertical)

        self._matrix = HostTaskMatrix()
        self._matrix.cell_selected.connect(self._on_cell_selected)
        self._splitter.addWidget(self._matrix)

        self._detail = DetailPane()
        self._detail.fix_requested.connect(self.fix_requested)
        self._detail.compare_requested.connect(self.compare_requested)
        self._splitter.addWidget(self._detail)

        self._splitter.setSizes([200, 120])
        main_layout.addWidget(self._splitter, stretch=1)

        self.setWidget(container)

    def _apply_theme(self, t: dict):
        self._t = t
        self.setStyleSheet(build_dock_stylesheet(t))
        header = self.widget().layout().itemAt(0).widget()
        header.setStyleSheet(
            f"background: {t.get('bg1', '#3c3836')};"
            f"border-bottom: 1px solid {t.get('border', '#504945')};"
        )
        self._matrix._apply_theme(t)
        self._detail._apply_theme(t)

    # ── Public API ────────────────────────────────────────────────

    def add_event(self, event: RunEvent):
        self._events.append(event)

        if event.title.startswith("Play:"):
            self._current_play = event.title[6:].strip()
            self._play_label.setText(f"▶  {self._current_play}")
            if not self.isVisible():
                self.show()
                self.raise_()
            return

        if event.title.startswith("Recap:"):
            self._update_host_count()
            return

        # Task result — update matrix
        task = event.task_name or event.title
        if event.host_results:
            for host, hr in event.host_results.items():
                self._matrix.add_host(host)
                self._matrix.update_cell(task, host, hr.status, event)
        elif event.severity == Severity.ERROR:
            # Non-verbose error — extract host from detail
            host = self._extract_host(event.detail)
            if host:
                self._matrix.add_host(host)
                self._matrix.update_cell(task, host, "failed", event)

        if event.severity == Severity.ERROR:
            if not self.isVisible():
                self.show()
                self.raise_()
            # Suggest verbose mode if no stdout/stderr captured
            hr_list = list(event.host_results.values())
            if hr_list and not any(r.stdout or r.stderr for r in hr_list):
                self._verbose_hint.setText(
                    "💡 Re-run with <b>-v</b> for full error detail"
                )
                self._verbose_hint.setTextFormat(Qt.TextFormat.RichText)
                self._verbose_hint.setStyleSheet(
                    f"color: {self._t.get('yellow', '#d79921')};"
                    f"font-size: 8pt;"
                )

        self._update_host_count()

    def show_suggestion(self, event: RunEvent, past_fix: str = None):
        """Legacy API compatibility — show detail pane for the failed event."""
        failed_hosts = [h for h, r in event.host_results.items()
                        if r.status in ("failed", "unreachable")]
        host = failed_hosts[0] if failed_hosts else ""
        if host:
            self._detail.show_result(event, host)

    def hide_suggestion(self):
        pass  # detail pane stays visible

    def clear(self):
        self._events.clear()
        self._matrix.clear_all()
        self._detail.clear()
        self._current_play = ""
        self._play_label.setText("Watching for ansible-playbook…")
        self._host_count.setText("")
        self._verbose_hint.setText("")

    # ── Internal ──────────────────────────────────────────────────

    def _on_cell_selected(self, event: RunEvent, host: str):
        self._detail.show_result(event, host)
        hint = event.file_hint or event.task_name or ""
        if hint and event.severity == Severity.ERROR:
            self.jump_requested.emit(hint)

    def _update_host_count(self):
        n = self._matrix.columnCount()
        if n > 0:
            self._host_count.setText(
                f"{n} host{'s' if n != 1 else ''}"
            )

    @staticmethod
    def _extract_host(detail: str) -> str:
        """Extract host name from 'Host: web-01\n...' style detail."""
        for line in detail.splitlines():
            if line.startswith("Host:"):
                return line[5:].strip()
        return ""

    def closeEvent(self, event):
        try:
            theme_signals.theme_changed.disconnect(self._apply_theme)
        except (RuntimeError, TypeError):
            pass
        super().closeEvent(event)