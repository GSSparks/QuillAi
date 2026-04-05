# plugins/features/terminal/main.py

from PyQt6.QtCore import Qt
from core.plugin_base import FeaturePlugin
from core.events import EVT_PROJECT_OPENED
from plugins.features.terminal.terminal import TerminalDock


class TerminalPlugin(FeaturePlugin):
    name = "terminal"
    description = "Embedded terminal dock (Ctrl+`)"
    enabled = True

    def activate(self):
        self.dock = TerminalDock(self.app)
        self.app.terminal_dock = self.dock
        self.app.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.dock)
        self.dock.hide()

        self.app.plugin_manager.register_dock("Terminal", "terminal_dock", "Ctrl+`")
        self.bind_key("Ctrl+`", self._toggle)
        self.on(EVT_PROJECT_OPENED, self._on_project_opened)

    def _toggle(self):
        if self.dock.isVisible():
            self.dock.hide()
        else:
            self.dock.show()
            self.dock.raise_()
            terminal = self.dock._terminal
            if hasattr(terminal, 'input_line'):
                terminal.input_line.setFocus()

    def _on_project_opened(self, project_root: str = None, **kwargs):
        if project_root:
            self.dock.set_cwd(project_root)

    def deactivate(self):
        self.dock.close()
        self.app.terminal_dock = None