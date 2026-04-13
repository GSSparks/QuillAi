# plugins/features/context_debugger/main.py

from PyQt6.QtCore import Qt
from core.plugin_base import FeaturePlugin
from .context_debugger import ContextDebuggerDock


class ContextDebuggerPlugin(FeaturePlugin):
    name = "context_debugger"
    description = "Visualize AI context + prompts"
    enabled = True

    def activate(self):
        self.dock = ContextDebuggerDock(self.app)
        self.app.context_debugger_dock = self.dock

        # Match your existing pattern
        self.app.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dock)
        self.dock.hide()

        self.app.plugin_manager.register_dock("Context Debugger", "context_debugger_dock")

        # Subscribe to our event
        self.on("context_built", self._on_context_built)
        self.on("tool_called", self._on_tool_called)
        self.on("tool_result", self._on_tool_result)

    def deactivate(self):
        if hasattr(self, "dock"):
            self.dock.close()
        self.app.context_debugger_dock = None

    def _on_context_built(self, context, prompt, **kwargs):
        self.dock.update_context(context, prompt)
        
    def _on_tool_called(self, tool, args, **kwargs):
        if hasattr(self.dock, "update_tool_call"):
            self.dock.update_tool_call(tool, args)
    
    def _on_tool_result(self, tool, result, **kwargs):
        if hasattr(self.dock, "update_tool_result"):
            self.dock.update_tool_result(tool, result)
