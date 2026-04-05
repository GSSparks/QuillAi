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

    def register_keybinding(self, sequence: str, callback) -> None:
        sc = QShortcut(QKeySequence(sequence), self.app)
        sc.activated.connect(callback)

    def subscribe(self, event: str, handler) -> None:
        self._subscribers.setdefault(event, []).append(handler)

    def emit(self, event: str, **kwargs) -> None:
        for handler in self._subscribers.get(event, []):
            handler(**kwargs)