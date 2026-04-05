"""
plugins/features/run_analyzer/main.py

Run Analyzer plugin — watches terminal output for Ansible and
Terraform/OpenTofu runs, surfaces errors and file hints inline.
"""

from PyQt6.QtCore import Qt
from core.plugin_base import FeaturePlugin
from core.events import EVT_TERMINAL_OUTPUT, EVT_PROJECT_OPENED
from plugins.features.run_analyzer.analyzer import RunAnalyzer
from plugins.features.run_analyzer.panel import RunAnalyzerPanel


class RunAnalyzerPlugin(FeaturePlugin):
    name = "run_analyzer"
    description = "Parses Ansible/Terraform output and surfaces errors with file links"
    enabled = True

    def activate(self):
        self._panel   = RunAnalyzerPanel(self.app)
        self.app.run_analyzer_dock = self._panel
        self.app.addDockWidget(
            Qt.DockWidgetArea.BottomDockWidgetArea, self._panel
        )
        self._panel.hide()

        self.app.plugin_manager.register_dock(
            "Run Analyzer", "run_analyzer_dock"
        )

        self._analyzer = RunAnalyzer(on_event=self._on_run_event)
        self._panel.jump_requested.connect(self._on_jump_requested)

        self.on(EVT_TERMINAL_OUTPUT, self._on_terminal_output)
        self.on(EVT_PROJECT_OPENED,  self._on_project_opened)

    def _on_terminal_output(self, text: str = "", **kwargs):
        self._analyzer.feed(text)

    def _on_run_event(self, event):
        # Called from analyzer — may be on any thread, use invokeMethod
        from PyQt6.QtCore import QMetaObject, Qt as _Qt
        from PyQt6.QtCore import Q_ARG
        # Safe: panel.add_event is called on the GUI thread via lambda + QTimer
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(0, lambda e=event: self._panel.add_event(e))

    def _on_project_opened(self, project_root: str = None, **kwargs):
        # New project — reset the analyzer state
        self._analyzer.reset()
        self._panel.clear()

    def _on_jump_requested(self, hint: str):
        """
        Try to find a file matching the hint and open it.
        Falls back to the find-in-files search if no exact match.
        """
        import os
        project_root = self._get_project_root()
        if not project_root:
            return

        # Walk project looking for files containing the hint in their path
        hint_lower = hint.lower()
        candidates = []
        skip = {'__pycache__', 'node_modules', '.git', '.terraform'}

        for dirpath, dirnames, filenames in os.walk(project_root):
            dirnames[:] = [d for d in dirnames if d not in skip]
            for fn in filenames:
                if fn.endswith(('.yml', '.yaml', '.tf', '.nix', '.py')):
                    full = os.path.join(dirpath, fn)
                    rel  = os.path.relpath(full, project_root).lower()
                    if hint_lower in rel:
                        candidates.append(full)

        if candidates:
            # Open the best match — prefer tasks/main.yml for ansible hints
            best = sorted(candidates, key=lambda p: (
                0 if 'tasks' in p and 'main' in p else
                1 if 'tasks' in p else
                2
            ))[0]
            self.app.open_file_in_tab(best)
        else:
            # Fall back to find-in-files search
            if hasattr(self.app, 'search_dock'):
                self.app.search_dock.show()
                self.app.search_dock.raise_()
                if hasattr(self.app, 'find_in_files_widget'):
                    self.app.find_in_files_widget.set_search_text(hint)
                    self.app.find_in_files_widget.focus_search()

    def _get_project_root(self) -> str:
        if hasattr(self.app, 'git_dock') and self.app.git_dock.repo_path:
            return self.app.git_dock.repo_path
        if hasattr(self.app, 'file_model') and hasattr(self.app, 'tree_view'):
            root = self.app.file_model.filePath(self.app.tree_view.rootIndex())
            if root:
                return root
        return ""

    def deactivate(self):
        self._panel.close()
        self.app.run_analyzer_dock = None