from PyQt6.QtCore import Qt
from core.plugin_base import FeaturePlugin
from plugins.features.import_graph.import_graph import GraphDockWidget


class ImportGraphPlugin(FeaturePlugin):
    name = "import_graph"
    description = "Import/dependency graph panel"
    enabled = True

    def activate(self):
        self.dock = GraphDockWidget(self.app)
        self.app.graph_dock = self.dock
        self.app.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock)
        self.dock.hide()

        self.app.plugin_manager.register_dock("Import Graph", "graph_dock")

        # Hook into file open and project load events
        self.on("file_opened", self._on_file_opened)
        self.on("project_opened", self._on_project_opened)

    def _on_file_opened(self, path: str = None, **kwargs):
        if path:
            self.dock.set_active_file(path)

    def _on_project_opened(self, project_root: str = None, **kwargs):
        if project_root:
            self.dock.load_project(
                project_root,
                open_cb=self.app.open_file_in_tab
            )

    def deactivate(self):
        self.dock.close()
        self.app.graph_dock = None