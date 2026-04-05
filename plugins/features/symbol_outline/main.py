from PyQt6.QtCore import Qt
from core.plugin_base import FeaturePlugin
from plugins.features.symbol_outline.symbol_outline import SymbolOutlineDock


class SymbolOutlinePlugin(FeaturePlugin):
    name = "symbol_outline"
    description = "LSP-powered symbol outline panel"
    enabled = True

    def activate(self):
        self.dock = SymbolOutlineDock(self.app)
        self.app.symbol_dock = self.dock
        self.app.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.dock)

        # Tabify with sidebar if it exists
        if hasattr(self.app, 'sidebar_dock'):
            self.app.tabifyDockWidget(self.app.sidebar_dock, self.dock)

        self.dock.hide()
        self.app.plugin_manager.register_dock("Outline", "symbol_dock")

        self.on("file_opened", self._on_file_opened)
        self.on("file_saved", self._on_file_saved)

    def _on_file_opened(self, path: str = None, editor=None, **kwargs):
        if editor is None:
            editor = self.app.current_editor()
        if editor and hasattr(self.app, 'lsp_manager'):
            self.dock.set_editor(editor, self.app.lsp_manager)

    def _on_file_saved(self, path: str = None, **kwargs):
        if path:
            self.dock.refresh_for_path(path)

    def deactivate(self):
        self.dock.close()
        self.app.symbol_dock = None