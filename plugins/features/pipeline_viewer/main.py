"""
plugins/features/pipeline_viewer/main.py

CI/CD Pipeline Viewer plugin.
Auto-detects .gitlab-ci.yml and .github/workflows/*.yml files
and renders them as an interactive visual graph.
"""

import os
from PyQt6.QtCore import Qt
from core.plugin_base import FeaturePlugin
from core.events import EVT_FILE_OPENED, EVT_FILE_SAVED, EVT_PROJECT_OPENED
from plugins.features.pipeline_viewer.parsers import detect_and_parse
from plugins.features.pipeline_viewer.panel import PipelineViewerPanel


_PIPELINE_FILES = {
    '.gitlab-ci.yml', '.gitlab-ci.yaml',
}


def _is_pipeline_file(path: str) -> bool:
    if not path:
        return False
    name = os.path.basename(path)
    if name in _PIPELINE_FILES:
        return True
    # GitHub Actions workflows
    if '.github' in path and 'workflows' in path:
        return path.endswith(('.yml', '.yaml'))
    return False


class PipelineViewerPlugin(FeaturePlugin):
    name        = "pipeline_viewer"
    description = "Visual CI/CD pipeline graph for GitLab CI and GitHub Actions"
    enabled     = True

    def activate(self):
        self._panel = PipelineViewerPanel(self.app)
        self.app.pipeline_viewer_dock = self._panel
        self.app.addDockWidget(
            Qt.DockWidgetArea.BottomDockWidgetArea, self._panel
        )

        # Tabify with output dock
        if hasattr(self.app, 'output_dock'):
            self.app.tabifyDockWidget(self.app.output_dock, self._panel)

        self._panel.hide()
        self.app.plugin_manager.register_dock(
            "Pipeline", "pipeline_viewer_dock"
        )

        self._panel.jump_to_job.connect(self._on_jump_to_job)
        self.on(EVT_FILE_OPENED,   self._on_file_opened)
        self.on(EVT_FILE_SAVED,    self._on_file_saved)
        self.on(EVT_PROJECT_OPENED, self._on_project_opened)

    # ── Events ────────────────────────────────────────────────────────────

    def _on_file_opened(self, path: str = None, editor=None, **kwargs):
        if path and _is_pipeline_file(path):
            self._load(path)

    def _on_file_saved(self, path: str = None, **kwargs):
        if path and _is_pipeline_file(path):
            self._load(path)

    def _on_project_opened(self, project_root: str = None, **kwargs):
        if not project_root:
            return
        # Search for pipeline files in the project
        pipeline_path = self._find_pipeline(project_root)
        if pipeline_path:
            self._load(pipeline_path)

    # ── Load ──────────────────────────────────────────────────────────────

    def _load(self, file_path: str):
        pipeline = detect_and_parse(file_path)
        if pipeline:
            self._panel.load_pipeline(pipeline, file_path)
            self._panel.show()
            self._panel.raise_()

    def _find_pipeline(self, project_root: str) -> str | None:
        """Find the first pipeline file in the project."""
        # Check root first
        for name in ('.gitlab-ci.yml', '.gitlab-ci.yaml'):
            full = os.path.join(project_root, name)
            if os.path.exists(full):
                return full

        # Check .github/workflows/
        workflows = os.path.join(project_root, '.github', 'workflows')
        if os.path.isdir(workflows):
            for fn in sorted(os.listdir(workflows)):
                if fn.endswith(('.yml', '.yaml')):
                    return os.path.join(workflows, fn)

        return None

    # ── Jump to job ───────────────────────────────────────────────────────

    def _on_jump_to_job(self, file_path: str, job_name: str):
        """Open the pipeline file and jump to the job definition."""
        self.app.open_file_in_tab(file_path)
        editor = self.app.current_editor()
        if not editor:
            return

        # Search for the job name in the file
        text  = editor.toPlainText()
        lines = text.split('\n')
        for i, line in enumerate(lines):
            # Match `job_name:` at start of line (GitLab) or
            # under `jobs:` section (GitHub)
            if line.startswith(f"{job_name}:") or \
               line.strip() == f"{job_name}:":
                from PyQt6.QtGui import QTextCursor
                block  = editor.document().findBlockByNumber(i)
                cursor = QTextCursor(block)
                editor.setTextCursor(cursor)
                editor.centerCursor()
                editor.setFocus()
                break

    def deactivate(self):
        self._panel.close()
        self.app.pipeline_viewer_dock = None