# plugins/features/terminal/main.py

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence
from core.plugin_base import FeaturePlugin
from .terminal import TerminalDock

class TerminalPlugin(FeaturePlugin):
    name = "terminal"
    description = "Embedded terminal dock (Ctrl+`)"
    enabled = True

    def activate(self):
        self.dock = TerminalDock(self.app)
        self.app.terminal_dock = self.dock
        self.app.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.dock)
        self.dock.hide()
        self.bind_key("Ctrl+`", self._toggle)
        self.app.plugin_manager.register_dock("Terminal", "terminal_dock", "Ctrl+`")

    def _toggle(self):
        if self.dock.isVisible():
            self.dock.hide()
        else:
            self.dock.show()
            self.dock.raise_()
            # Focus the input line if using fallback terminal
            terminal = self.dock._terminal
            if hasattr(terminal, 'input_line'):
                terminal.input_line.setFocus()

    def deactivate(self):
        self.dock.close()
        self.app.terminal_dock = None