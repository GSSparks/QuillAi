# plugins/features/terminal/main.py

from PyQt6.QtCore import Qt, QTimer
from core.plugin_base import FeaturePlugin
from core.events import EVT_PROJECT_OPENED, EVT_TERMINAL_OUTPUT
from plugins.features.terminal.terminal_dock import TerminalDock


class TerminalPlugin(FeaturePlugin):
    name = "terminal"
    description = "Full VT100 terminal emulator"
    enabled = True

    def activate(self):
        self.dock = TerminalDock(self.app)
        self.app.terminal_dock = self.dock
        self.app.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.dock)
        self.dock.hide()

        self.app.plugin_manager.register_dock('Terminal', 'terminal_dock', 'Ctrl+`')
        self.bind_key('Ctrl+`', self._toggle)
        self.on(EVT_PROJECT_OPENED, self._on_project_opened)

        # Forward terminal output into the event bus
        self.dock.data_received.connect(
            lambda text: self.app.plugin_manager.emit(
                EVT_TERMINAL_OUTPUT, text=text
            )
        )

    def _toggle(self):
        if self.dock.isVisible():
            self.dock.hide()
        else:
            self.dock.show()
            self.dock.raise_()
            QTimer.singleShot(50, self.dock._terminal.setFocus)

    def _on_project_opened(self, project_root: str = None, **kwargs):
        if project_root:
            self.dock.set_cwd(project_root)

    def deactivate(self):
        self.dock.close()
        self.app.terminal_dock = None