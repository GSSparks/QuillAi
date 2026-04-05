"""
terminal_dock.py

QDockWidget wrapper for TerminalView.
Replaces the old TerminalDock from ui/terminal.py.
"""

from PyQt6.QtWidgets import QDockWidget
from PyQt6.QtCore import pyqtSignal

from ui.theme import get_theme, theme_signals, build_dock_stylesheet
from plugins.features.terminal.terminal_view import TerminalView


class TerminalDock(QDockWidget):

    # Forwarded from TerminalView — used by the run analyzer
    data_received = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__('Terminal', parent)
        self.setObjectName('terminal_dock')

        cwd = self._infer_cwd(parent)
        clean = self._read_clean_shell(parent)

        self._terminal = TerminalView(cwd=cwd, clean_shell=clean, parent=self)
        self._terminal.data_received.connect(self.data_received)
        self.setWidget(self._terminal)

        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable  |
            QDockWidget.DockWidgetFeature.DockWidgetMovable   |
            QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )

        self.apply_styles(get_theme())
        theme_signals.theme_changed.connect(self._on_theme)

    def _infer_cwd(self, mw) -> str:
        if mw and hasattr(mw, 'git_dock') and mw.git_dock.repo_path:
            return mw.git_dock.repo_path
        if mw and hasattr(mw, 'file_model') and hasattr(mw, 'tree_view'):
            root = mw.file_model.filePath(mw.tree_view.rootIndex())
            if root:
                import os
                if os.path.isdir(root):
                    return root
        import os
        return os.getcwd()

    def _read_clean_shell(self, mw) -> bool:
        if mw and hasattr(mw, 'settings_manager'):
            return bool(mw.settings_manager.get('terminal_clean_shell'))
        return False

    def _on_theme(self, t: dict):
        self.apply_styles(t)

    def apply_styles(self, t: dict):
        self.setStyleSheet(build_dock_stylesheet(t))
        self._terminal.apply_styles(t)

    def set_cwd(self, path: str):
        self._terminal.set_cwd(path)

    def restart(self):
        self._terminal.restart()

    def closeEvent(self, event):
        try:
            theme_signals.theme_changed.disconnect(self._on_theme)
        except (RuntimeError, TypeError):
            pass
        super().closeEvent(event)