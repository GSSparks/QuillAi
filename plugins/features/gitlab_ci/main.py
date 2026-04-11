"""
plugins/features/gitlab_ci/main.py

GitLab CI feature plugin — pipeline viewer, job log fetcher,
and live CI context injection into AI chat.
"""
from __future__ import annotations

from core.plugin_base import FeaturePlugin
from core.events import EVT_FILE_OPENED
from PyQt6.QtCore import Qt


class GitLabCIPlugin(FeaturePlugin):
    name    = "gitlab_ci"
    enabled = True

    @classmethod
    def should_show(cls, project_root: str) -> bool:
        """Show only when the project has a .gitlab-ci.yml or .gitlab dir."""
        import os
        return (
            os.path.exists(os.path.join(project_root, '.gitlab-ci.yml'))
            or os.path.exists(os.path.join(project_root, '.gitlab'))
        )

    def activate(self):
        from plugins.features.gitlab_ci.panel import GitLabPanel
        from PyQt6.QtWidgets import QDockWidget

        self.dock = GitLabPanel(
            client_fn=self._make_client,
            parent=self.app,
        )
        self.app.addDockWidget(
            Qt.DockWidgetArea.RightDockWidgetArea, self.dock
        )
        self.app.gitlab_dock = self.dock
        self.app.plugin_manager.register_dock(
            "GitLab CI", "gitlab_dock"
        )

        # Wire send_to_chat signal → chat panel
        self.dock.send_to_chat.connect(self._on_send_to_chat)

        # Auto-refresh when a .gitlab-ci.yml is opened
        self.on(EVT_FILE_OPENED, self._on_file_opened)

    def _make_client(self):
        """Build a GitLabClient from per-project settings."""
        ps = getattr(self.app, 'project_settings', None)
        if not ps or not ps.has_gitlab():
            return None
        from plugins.features.gitlab_ci.client import GitLabClient
        return GitLabClient(
            ps.get_gitlab_url(),
            ps.get_gitlab_token(),
            ps.get_gitlab_project_id(),
        )

    def _on_send_to_chat(self, context: str):
        """Inject CI log context into the chat panel."""
        if hasattr(self.app, "chat_panel"):
            self.app.chat_panel.switch_to_chat()
            # Prepend context to the chat input as a quoted block
            existing = self.app.chat_panel.chat_input.toPlainText()
            separator = "\n\n" if existing else ""
            self.app.chat_panel.chat_input.setPlainText(
                f"<gitlab_ci_context>\n{context}\n</gitlab_ci_context>"
                f"{separator}{existing}"
            )
            self.app.chat_panel.chat_input.setFocus()

    def _on_file_opened(self, path=None, **kwargs):
        """Auto-refresh pipeline list when .gitlab-ci.yml is opened."""
        if path and ".gitlab-ci.yml" in str(path):
            if hasattr(self, "dock"):
                from PyQt6.QtCore import QTimer
                QTimer.singleShot(500, self.dock._fetch_pipelines)

    def deactivate(self):
        if hasattr(self, "dock"):
            self.dock.close()
            self.app.gitlab_dock = None