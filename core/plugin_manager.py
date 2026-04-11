import importlib
import importlib.util
import inspect
import pathlib
import sys

from core.plugin_base import FeaturePlugin
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QShortcut, QKeySequence
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from main import MainWindow


class PluginManager:
    def __init__(self, app):
        self.app = app
        self._plugins = []
        self._subscribers = {}
        self.docks = {}

    def register_dock(self, label: str, dock_attr: str, shortcut: str = None):
        self.docks[label] = (dock_attr, shortcut)

    def discover_and_load(self, features_path: str) -> None:
        path = pathlib.Path(features_path)
        if not path.exists():
            print(f"[PluginManager] Features directory not found: {features_path}")
            return
    
        # Make 'plugins' importable so 'features.terminal.main' etc resolve
        plugins_dir = str(path.parent)
        if plugins_dir not in sys.path:
            sys.path.insert(0, plugins_dir)

        candidates = sorted(
            list(path.glob("*.py")) +
            [d / "main.py" for d in path.iterdir()
             if d.is_dir() and (d / "main.py").exists()]
        )

        for module_file in candidates:
            if module_file.name.startswith("_"):
                continue

            # Build a unique module name from the path relative to features/
            rel = module_file.relative_to(path)
            parts = list(rel.parts)
            if parts[-1] == "main.py":
                module_name = "features." + ".".join(parts[:-1]) + ".main"
            else:
                module_name = "features." + parts[0].replace(".py", "")

            spec = importlib.util.spec_from_file_location(module_name, module_file)
            try:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
            except Exception as e:
                print(f"[PluginManager] Failed to load {module_file}: {e}")
                continue

            for _, cls in inspect.getmembers(module, inspect.isclass):
                if not (issubclass(cls, FeaturePlugin)
                        and cls is not FeaturePlugin
                        and cls.__module__ == module_name):
                    continue

                if not getattr(cls, "enabled", True):
                    print(f"[PluginManager] Skipped (disabled): {cls.name or cls.__name__}")
                    continue

                try:
                    plugin = cls(self.app)
                    self._plugins.append(plugin)
                    plugin.activate()
                    print(f"[PluginManager] Loaded: {cls.name or cls.__name__}")
                except Exception as e:
                    print(f"[PluginManager] Failed to activate {cls.__name__}: {e}")

    def get_plugin(self, name: str):
        """Return the plugin instance with the given name, or None."""
        for plugin in self._plugins:
            if plugin.name == name:
                return plugin
        return None

    def is_enabled(self, name: str) -> bool:
        """Return True if a plugin with this name is currently active."""
        return self.get_plugin(name) is not None

    def disable_plugin(self, name: str) -> bool:
        """Deactivate a plugin and remove it from the active list."""
        plugin = self.get_plugin(name)
        if plugin is None:
            return False
        try:
            plugin.deactivate()
        except Exception as e:
            print(f"[PluginManager] deactivate error for {name}: {e}")
        self._plugins.remove(plugin)
        # Remove subscribers registered by this plugin
        for event, handlers in self._subscribers.items():
            self._subscribers[event] = [
                h for h in handlers
                if not self._handler_belongs_to(h, plugin)
            ]
        return True

    def enable_plugin(self, module_file: str) -> bool:
        """
        Load and activate a plugin from its main.py path.
        Returns True on success.
        """
        import importlib.util, inspect
        path = pathlib.Path(module_file)
        if not path.exists():
            return False
        # Derive module name
        features_path = path.parent.parent
        rel = path.relative_to(features_path)
        parts = list(rel.parts)
        if parts[-1] == "main.py":
            module_name = "features." + ".".join(parts[:-1]) + ".main"
        else:
            module_name = "features." + parts[0].replace(".py", "")
        spec = importlib.util.spec_from_file_location(module_name, path)
        try:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception as e:
            print(f"[PluginManager] Failed to reload {path}: {e}")
            return False
        for _, cls in inspect.getmembers(module, inspect.isclass):
            if not (issubclass(cls, FeaturePlugin)
                    and cls is not FeaturePlugin
                    and cls.__module__ == module_name):
                continue
            try:
                plugin = cls(self.app)
                self._plugins.append(plugin)
                plugin.activate()
                return True
            except Exception as e:
                print(f"[PluginManager] Failed to activate {cls.__name__}: {e}")
                return False
        return False

    def _handler_belongs_to(self, handler, plugin) -> bool:
        """Check if a subscriber handler is a bound method of the plugin."""
        return getattr(handler, '__self__', None) is plugin

    def register_keybinding(self, sequence: str, callback) -> None:
        sc = QShortcut(QKeySequence(sequence), self.app)
        sc.activated.connect(callback)

    def subscribe(self, event: str, handler) -> None:
        self._subscribers.setdefault(event, []).append(handler)

    def emit(self, event: str, **kwargs) -> None:
        for handler in self._subscribers.get(event, []):
            handler(**kwargs)
        # Context-aware dock visibility
        if event == "project_opened":
            project_root = kwargs.get("project_root", "")
            if project_root:
                for plugin in self._plugins:
                    try:
                        plugin._update_dock_visibility(project_root)
                    except Exception as e:
                        print(f"[PluginManager] dock visibility error "
                              f"for {plugin.name}: {e}")