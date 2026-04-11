from abc import ABC, abstractmethod
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from main import MainWindow

class FeaturePlugin(ABC):
    name: str = ""
    description: str = ""

    def __init__(self, app: "MainWindow"):
        self.app = app

    @abstractmethod
    def activate(self) -> None:
        """Called once at startup. Register panels, actions, keybindings here."""
        ...

    def deactivate(self) -> None:
        """Optional cleanup when plugin is disabled at runtime."""
        pass

    @classmethod
    def should_show(cls, project_root: str) -> bool:
        """
        Return True if this plugin's dock should be visible for the given
        project root. Override in subclasses to hide docks when irrelevant.
        Default: always show.
        """
        return True

    def _update_dock_visibility(self, project_root: str) -> None:
        """
        Called on project_opened. Shows or hides the plugin's registered
        dock based on should_show(). Plugins with multiple docks should
        override this method.
        """
        visible = self.__class__.should_show(project_root)
        for label, (dock_attr, _) in self.app.plugin_manager.docks.items():
            dock = getattr(self.app, dock_attr, None)
            if dock is not None and hasattr(self, 'dock') and dock is self.dock:
                if visible:
                    # Don't force-show — just make it available
                    dock.setEnabled(True)
                else:
                    dock.hide()
                    dock.setEnabled(False)
                return

    @classmethod
    def should_show(cls, project_root: str) -> bool:
        """
        Return True if this plugin's dock should be visible for the given
        project root. Override in subclasses to hide docks when irrelevant.
        Default: always show.
        """
        return True

    def _update_dock_visibility(self, project_root: str) -> None:
        visible = self.__class__.should_show(project_root)
        docks = []
        for attr in ('dock', '_panel', '_dock'):
            val = getattr(self, attr, None)
            if val is not None:
                docks.append(val)
        if not docks:
            for attr, val in self.__dict__.items():
                if attr.endswith('_dock') and val is not None:
                    docks.append(val)
        for dock in docks:
            if dock is None:
                continue
            if visible:
                dock.setEnabled(True)
                if getattr(self, '_dock_was_visible', False):
                    dock.show()
                    self._dock_was_visible = False
            else:
                self._dock_was_visible = dock.isVisible()
                dock.hide()
                dock.setEnabled(False)

    # Convenience helpers — plugins call these instead of reaching into MainWindow directly
    def add_panel(self, widget, title: str, area="left") -> None:
        self.app.plugin_manager.register_panel(widget, title, area)

    def add_action(self, menu: str, action) -> None:
        self.app.plugin_manager.register_action(menu, action)

    def bind_key(self, sequence: str, callback) -> None:
        self.app.plugin_manager.register_keybinding(sequence, callback)

    def on(self, event: str, handler) -> None:
        self.app.plugin_manager.subscribe(event, handler)

    def emit(self, event: str, **kwargs) -> None:
        self.app.plugin_manager.emit(event, **kwargs)