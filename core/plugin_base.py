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