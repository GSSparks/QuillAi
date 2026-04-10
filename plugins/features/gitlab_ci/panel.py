"""
plugins/features/gitlab_ci/panel.py

GitLab CI panel — shows recent pipelines, job status, and lets
the user fetch job logs directly into the AI chat context.
"""
from __future__ import annotations

import threading
from PyQt6.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QTreeWidget, QTreeWidgetItem,
    QComboBox, QLineEdit, QApplication, QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, pyqtSlot
from PyQt6.QtGui import QColor, QFont

from ui.theme import get_theme, theme_signals, build_dock_stylesheet
from ui.log_viewer import LogViewerDock


_STATUS_COLORS = {
    "success":  "green",
    "failed":   "red",
    "running":  "yellow",
    "pending":  "fg4",
    "canceled": "fg4",
    "skipped":  "bg4",
    "created":  "fg4",
}

_STATUS_ICONS = {
    "success":  "✓",
    "failed":   "✗",
    "running":  "⟳",
    "pending":  "…",
    "canceled": "⊘",
    "skipped":  "–",
    "created":  "·",
}


class GitLabPanel(QDockWidget):

    # Emitted when user wants to send log context to chat
    send_to_chat    = pyqtSignal(str)
    # Internal signals for thread-safe UI updates
    _pipelines_ready = pyqtSignal(object)
    _jobs_ready      = pyqtSignal(object)  # emits (item, jobs) as tuple
    _logs_ready      = pyqtSignal(str)
    _error_occurred  = pyqtSignal(str)
    _bridges_ready   = pyqtSignal(object, object)  # (parent_item, bridges)

    def __init__(self, client_fn, parent=None):
        """
        client_fn: callable() -> GitLabClient | None
        Called each time we need a client so settings changes are picked up.
        """
        super().__init__("GitLab CI", parent)
        self.setObjectName("gitlab_ci_dock")
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable  |
            QDockWidget.DockWidgetFeature.DockWidgetMovable   |
            QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        self._client_fn  = client_fn
        self._pipelines  = []
        self._t          = get_theme()
        self._log_viewer = None
        # Connect internal signals for thread-safe callbacks
        self._pipelines_ready.connect(self._on_pipelines_loaded)
        self._jobs_ready.connect(self._on_jobs_loaded)
        self._logs_ready.connect(self._on_logs_ready)
        self._error_occurred.connect(self._on_error)
        self._bridges_ready.connect(self._on_bridges_loaded)

        self._build_ui()
        self._apply_theme(self._t)
        theme_signals.theme_changed.connect(self._apply_theme)

    # ── UI ────────────────────────────────────────────────────────────────

    def _build_ui(self):
        container = QWidget()
        layout    = QVBoxLayout(container)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Toolbar
        toolbar = QHBoxLayout()

        self._ref_input = QLineEdit()
        self._ref_input.setPlaceholderText("Branch / ref (optional)")
        self._ref_input.setFixedHeight(24)
        toolbar.addWidget(self._ref_input, stretch=1)

        self._status_combo = QComboBox()
        self._status_combo.addItems(["All", "failed", "success", "running"])
        self._status_combo.setFixedHeight(24)
        self._status_combo.setFixedWidth(80)
        toolbar.addWidget(self._status_combo)

        refresh_btn = QPushButton("↻")
        refresh_btn.setFixedSize(24, 24)
        refresh_btn.setToolTip("Refresh pipelines")
        refresh_btn.clicked.connect(self._fetch_pipelines)
        toolbar.addWidget(refresh_btn)

        layout.addLayout(toolbar)

        # Status label
        self._status_label = QLabel("Not connected")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._status_label)

        # Pipeline tree
        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["Pipeline", "Status", "Ref", "Duration"])
        self._tree.setColumnWidth(0, 90)
        self._tree.setColumnWidth(1, 70)
        self._tree.setColumnWidth(2, 120)
        self._tree.setColumnWidth(3, 60)
        self._tree.setAlternatingRowColors(True)
        self._tree.itemExpanded.connect(self._on_item_expanded)
        self._tree.itemClicked.connect(self._on_item_clicked)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._on_context_menu)
        layout.addWidget(self._tree, stretch=1)

        # Action bar
        action_bar = QHBoxLayout()

        self._fetch_log_btn = QPushButton("📋 Fetch Failed Logs")
        self._fetch_log_btn.setToolTip("Fetch logs from failed jobs and send to chat")
        self._fetch_log_btn.clicked.connect(self._fetch_failed_logs)
        action_bar.addWidget(self._fetch_log_btn)

        action_bar.addStretch()

        self._open_btn = QPushButton("🔗 Open in Browser")
        self._open_btn.clicked.connect(self._open_in_browser)
        action_bar.addWidget(self._open_btn)

        layout.addLayout(action_bar)

        self.setWidget(container)
        print('[GitLab] _build_ui done')

    # ── Data fetching ─────────────────────────────────────────────────────

    def _fetch_pipelines(self):
        client = self._client_fn()
        if not client:
            self._status_label.setText("⚠ GitLab not configured")
            return

        self._status_label.setText("Fetching…")
        self._tree.clear()

        ref    = self._ref_input.text().strip() or None
        status = self._status_combo.currentText()
        if status == "All":
            status = None

        def _run():
            try:
                pipelines = client.list_pipelines(ref=ref, status=status,
                                                   per_page=15)
                self._pipelines_ready.emit(pipelines)
            except Exception as e:
                self._error_occurred.emit(str(e))

        threading.Thread(target=_run, daemon=True).start()

    @pyqtSlot(object)
    def _on_pipelines_loaded(self, pipelines: list):
        self._pipelines = pipelines
        self._tree.clear()
        t = self._t

        for pl in pipelines:
            status = pl.get("status", "?")
            icon   = _STATUS_ICONS.get(status, "?")
            color_key = _STATUS_COLORS.get(status, "fg1")
            color  = t.get(color_key, "#ebdbb2")

            item = QTreeWidgetItem([
                f"#{pl['id']}",
                f"{icon} {status}",
                pl.get("ref", "?")[:20],
                f"{pl.get('duration', '?')}s",
            ])
            item.setData(0, Qt.ItemDataRole.UserRole, pl)
            item.setForeground(1, QColor(color))
            # Add placeholder child for lazy loading
            item.addChild(QTreeWidgetItem(["Loading…"]))
            self._tree.addTopLevelItem(item)

        count = len(pipelines)
        self._status_label.setText(f"{count} pipeline{'s' if count != 1 else ''}")

    def _on_item_expanded(self, item: QTreeWidgetItem):
        """Lazy-load jobs when pipeline is expanded."""
        # Check if it's a placeholder
        if (item.childCount() == 1 and
                item.child(0).text(0) == "Loading…"):
            pl = item.data(0, Qt.ItemDataRole.UserRole)
            if not pl:
                return
            item.takeChild(0)

            def _run():
                try:
                    client = self._client_fn()
                    if not client:
                        return
                    jobs    = client.get_pipeline_jobs(pl["id"])
                    bridges = client.get_pipeline_bridges(pl["id"])
                    self._jobs_ready.emit((item, list(jobs)))
                    if bridges:
                        self._bridges_ready.emit((item, bridges))
                except Exception as e:
                    print(f"[GitLab] jobs fetch failed: {e}")

            threading.Thread(target=_run, daemon=True).start()

    @pyqtSlot(object)
    def _on_jobs_loaded(self, payload):
        parent_item, jobs = payload
        t = self._t
        for job in jobs:
            status    = job.get("status", "?")
            icon      = _STATUS_ICONS.get(status, "?")
            color_key = _STATUS_COLORS.get(status, "fg1")
            color     = t.get(color_key, "#ebdbb2")
            duration  = job.get("duration")
            dur_str   = f"{duration:.0f}s" if duration else "?"

            child = QTreeWidgetItem([
                job.get("name", "?"),
                f"{icon} {status}",
                job.get("stage", "?"),
                dur_str,
            ])
            child.setData(0, Qt.ItemDataRole.UserRole, job)
            child.setForeground(1, QColor(color))
            parent_item.addChild(child)

    @pyqtSlot(str)
    def _on_logs_ready(self, context: str):
        if context.startswith('__log_viewer__'):
            # Route to log viewer
            log_text = context[len('__log_viewer__'):]
            if self._log_viewer:
                title = self._log_viewer.windowTitle().replace('Log — ', '')
                self._log_viewer.show_log(title, log_text, source='gitlab')
        else:
            self._status_label.setText('✓ Logs fetched — sent to chat')
            self.send_to_chat.emit(context)

    def _on_error(self, msg: str):
        self._status_label.setText(f"✗ {msg[:60]}")

    # ── Log fetching ──────────────────────────────────────────────────────

    def _fetch_failed_logs(self):
        """Fetch logs from the most recent failed pipeline."""
        client = self._client_fn()
        if not client:
            self._status_label.setText('⚠ GitLab not configured')
            return
        self._status_label.setText('Fetching failed job logs…')

        def _run():
            try:
                pipelines = client.list_pipelines(status='failed', per_page=1)
                if not pipelines:
                    self._error_occurred.emit('No failed pipelines found')
                    return
                pl   = pipelines[0]
                jobs = client.get_pipeline_jobs(pl['id'])
                failed_jobs = [j for j in jobs
                               if j.get('status') == 'failed']
                print(f'[GitLab] pipeline #{pl["id"]} — '
                      f'{len(failed_jobs)} failed jobs')
                from plugins.features.gitlab_ci.client import (
                    format_pipeline_summary,
                    format_job_trace_for_context,
                )
                parts = [
                    '[GitLab CI — Failed Pipeline]\n' +
                    format_pipeline_summary(pl, jobs)
                ]
                for job in failed_jobs[:3]:
                    print(f'[GitLab] fetching trace for {job["name"]}')
                    trace = client.get_job_trace(job['id'])
                    print(f'[GitLab] trace length: {len(trace)} chars')
                    parts.append(
                        format_job_trace_for_context(
                            job, trace, max_chars=2000
                        )
                    )
                context = '\n\n---\n\n'.join(parts)
                self._logs_ready.emit(context)
            except Exception as e:
                import traceback; traceback.print_exc()
                self._error_occurred.emit(str(e))

        import threading
        threading.Thread(target=_run, daemon=True).start()

    def _fetch_pipeline_logs(self, pl: dict):
        client = self._client_fn()
        if not client:
            return
        self._status_label.setText("Fetching logs…")

        def _run():
            try:
                jobs        = client.get_pipeline_jobs(pl["id"])
                failed_jobs = [j for j in jobs if j.get("status") == "failed"]
                from plugins.features.gitlab_ci.client import (
                    format_pipeline_summary, format_job_trace_for_context
                )
                parts = ["[GitLab CI]\n" + format_pipeline_summary(pl, jobs)]
                for job in failed_jobs[:3]:
                    trace = client.get_job_trace(job["id"])
                    parts.append(format_job_trace_for_context(job, trace))
                context = "\n\n---\n\n".join(parts)
                self._logs_ready.emit(context)
            except Exception as e:
                self._error_occurred.emit(str(e))

        threading.Thread(target=_run, daemon=True).start()

    def _fetch_job_log(self, job: dict):
        client = self._client_fn()
        if not client:
            return
        self._status_label.setText("Fetching job log…")

        def _run():
            try:
                trace = client.get_job_trace(job["id"])
                from plugins.features.gitlab_ci.client import format_job_trace_for_context
                context = "[GitLab CI — Job Log]\n" + format_job_trace_for_context(
                    job, trace, max_chars=4000
                )
                self._logs_ready.emit(context)
            except Exception as e:
                self._error_occurred.emit(str(e))

        threading.Thread(target=_run, daemon=True).start()

    def _on_item_clicked(self, item, column):
        """Show log viewer when a job item is clicked."""
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data or 'stage' not in data:
            return
        # Only fetch log for finished jobs
        status = data.get('status', '')
        if status in ('created', 'pending', 'running'):
            return
        self._show_job_log(data)

    def _show_job_log(self, job: dict):
        """Fetch and display job log in the log viewer."""
        client = self._client_fn()
        if not client:
            return
        # Create log viewer if needed
        if not self._log_viewer or not self._log_viewer.isVisible():
            parent = self.parent()
            self._log_viewer = LogViewerDock(parent)
            if parent and hasattr(parent, 'addDockWidget'):
                from PyQt6.QtCore import Qt as _Qt
                parent.addDockWidget(
                    _Qt.DockWidgetArea.BottomDockWidgetArea,
                    self._log_viewer
                )
            self._log_viewer.send_to_chat.connect(
                lambda ctx: self.send_to_chat.emit(ctx)
            )
        title = f"{job.get('name','?')} [{job.get('status','?').upper()}]"
        self._log_viewer.show_log(title, 'Fetching…', source='gitlab')

        def _run():
            try:
                trace = client.get_job_trace(job['id'])
                self._logs_ready.emit(f'__log_viewer__{trace}')
            except Exception as e:
                self._logs_ready.emit(f'__log_viewer__Error: {e}')

        import threading
        threading.Thread(target=_run, daemon=True).start()

    def _on_bridges_loaded(self, payload):
        """Add child pipeline nodes under their trigger job."""
        parent_item, bridges = payload
        t = self._t
        for bridge in bridges:
            ds = bridge.get('downstream_pipeline')
            if not ds:
                continue
            status    = ds.get('status', '?')
            icon      = _STATUS_ICONS.get(status, '?')
            color_key = _STATUS_COLORS.get(status, 'fg1')
            color     = t.get(color_key, '#ebdbb2')
            child = QTreeWidgetItem([
                f"⤵ #{ds['id']}",
                f"{icon} {status}",
                bridge.get('name', '?')[:20],
                f"{ds.get('duration','?')}s",
            ])
            child.setData(0, Qt.ItemDataRole.UserRole, ds)
            child.setForeground(1, QColor(color))
            child.setToolTip(0, 'Child pipeline')
            # Add placeholder for lazy loading
            child.addChild(QTreeWidgetItem(['Loading…']))
            # Find the trigger job item and add under it
            bridge_name = bridge.get('name', '')
            placed = False
            for i in range(parent_item.childCount()):
                job_item = parent_item.child(i)
                if job_item.text(0) == bridge_name:
                    job_item.addChild(child)
                    placed = True
                    break
            if not placed:
                parent_item.addChild(child)

    def _on_context_menu(self, pos):
        from PyQt6.QtWidgets import QMenu
        item = self._tree.itemAt(pos)
        if not item:
            return
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
        menu = QMenu(self)
        t    = self._t
        menu.setStyleSheet(f"""
            QMenu {{
                background: {t.get('bg1','#3c3836')};
                color: {t.get('fg1','#ebdbb2')};
                border: 1px solid {t.get('bg3','#665c54')};
                font-size: 9pt; padding: 4px 0;
            }}
            QMenu::item {{ padding: 4px 20px; }}
            QMenu::item:selected {{
                background: {t.get('bg3','#665c54')};
                color: {t.get('yellow','#d79921')};
            }}
        """)
        # Pipeline item (has 'ref' key, not a job)
        if 'ref' in data and 'stage' not in data:
            act_logs = menu.addAction('📋 Fetch Failed Logs → Chat')
            act_copy = menu.addAction('⎘ Copy Pipeline URL')
            act_open = menu.addAction('🔗 Open in Browser')
            action = menu.exec(self._tree.viewport().mapToGlobal(pos))
            if action == act_logs:
                self._fetch_pipeline_logs(data)
            elif action == act_copy:
                from PyQt6.QtWidgets import QApplication
                QApplication.clipboard().setText(self._pipeline_url(data))
            elif action == act_open:
                from PyQt6.QtGui import QDesktopServices
                from PyQt6.QtCore import QUrl
                QDesktopServices.openUrl(QUrl(self._pipeline_url(data)))
        elif 'stage' in data:
            act_log  = menu.addAction('📋 Fetch Job Log → Chat')
            act_copy = menu.addAction('⎘ Copy Job URL')
            action = menu.exec(self._tree.viewport().mapToGlobal(pos))
            if action == act_log:
                self._fetch_job_log(data)
            elif action == act_copy:
                from PyQt6.QtWidgets import QApplication
                QApplication.clipboard().setText(self._job_url(data))

    def _pipeline_url(self, pl: dict) -> str:
        client = self._client_fn()
        if not client:
            return ''
        from urllib.parse import unquote
        proj = unquote(client.project)
        base = client.base.replace('/api/v4', '')
        return f"{base}/{proj}/-/pipelines/{pl['id']}"

    def _job_url(self, job: dict) -> str:
        client = self._client_fn()
        if not client:
            return ''
        from urllib.parse import unquote
        proj = unquote(client.project)
        base = client.base.replace('/api/v4', '')
        return f"{base}/{proj}/-/jobs/{job['id']}"

    def _open_in_browser(self):
        item = self._tree.currentItem()
        if not item:
            return
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
        from PyQt6.QtGui import QDesktopServices
        from PyQt6.QtCore import QUrl
        url = (self._job_url(data) if "stage" in data
               else self._pipeline_url(data))
        if url:
            QDesktopServices.openUrl(QUrl(url))

    # ── Theme ─────────────────────────────────────────────────────────────

    def _apply_theme(self, t: dict):
        self._t = t
        print(f'[GitLab] applying theme')
        self.setStyleSheet(build_dock_stylesheet(t))
        self._tree.setStyleSheet(f"""
            QTreeWidget {{
                background: {t.get('bg0','#282828')};
                color: {t.get('fg1','#ebdbb2')};
                border: none;
                font-size: 9pt;
                alternate-background-color: {t.get('bg1','#3c3836')};
            }}
            QTreeWidget::item:selected {{
                background: {t.get('bg3','#665c54')};
                color: {t.get('yellow','#d79921')};
            }}
            QHeaderView::section {{
                background: {t.get('bg2','#504945')};
                color: {t.get('fg4','#a89984')};
                border: none;
                padding: 2px 4px;
                font-size: 8pt;
            }}
        """)
        self._status_label.setStyleSheet(f"""
            QLabel {{
                color: {t.get('fg4','#a89984')};
                font-size: 8pt;
                padding: 2px;
                background: transparent;
            }}
        """)
        btn_style = f"""
            QPushButton {{
                background: {t.get('bg2','#504945')};
                color: {t.get('fg1','#ebdbb2')};
                border: 1px solid {t.get('bg3','#665c54')};
                border-radius: 3px;
                padding: 3px 10px;
                font-size: 9pt;
            }}
            QPushButton:hover {{
                background: {t.get('bg3','#665c54')};
            }}
        """
        for btn in self.widget().findChildren(QPushButton):
            btn.setStyleSheet(btn_style)

    def closeEvent(self, event):
        try:
            theme_signals.theme_changed.disconnect(self._apply_theme)
        except (RuntimeError, TypeError):
            pass
        super().closeEvent(event)