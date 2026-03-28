import os
import importlib.util
import inspect
from PyQt6.QtGui import QSyntaxHighlighter, QTextCharFormat, QColor, QFont
from PyQt6.QtCore import QRegularExpression


# ─────────────────────────────────────────────────────────────────────────────
# 1. Theme Engine
# ─────────────────────────────────────────────────────────────────────────────

def create_format(color_hex, style=''):
    """Helper to create a QTextCharFormat with color and optional style."""
    fmt = QTextCharFormat()
    fmt.setForeground(QColor(color_hex))
    if 'bold' in style:
        fmt.setFontWeight(QFont.Weight.Bold)
    if 'italic' in style:
        fmt.setFontItalic(True)
    return fmt


# Monokai-inspired dark theme shared across all language plugins
THEME = {
    'keyword':   create_format('#F92672', 'bold'),
    'builtin':   create_format('#66D9EF', 'italic'),
    'string':    create_format('#E6DB74'),
    'comment':   create_format('#75715E', 'italic'),
    'number':    create_format('#AE81FF'),
    'class_def': create_format('#A6E22E', 'bold'),
    'func_def':  create_format('#A6E22E', 'bold'),
    'tag':       create_format('#F92672', 'bold'),
    'attribute': create_format('#A6E22E'),
}


# ─────────────────────────────────────────────────────────────────────────────
# 2. Base Plugin Classes
# ─────────────────────────────────────────────────────────────────────────────

class LanguagePlugin:
    """
    Base class for syntax highlighting plugins.

    To create a new language plugin:
      1. Subclass LanguagePlugin
      2. Set EXTENSIONS = ['.xyz']
      3. Add rules in __init__ using self.add_rule() or self.rules.append()
      4. Drop the file in plugins/languages/
      5. That's it — auto-registered on startup, no main.py changes needed.
    """

    EXTENSIONS = []

    def __init__(self):
        self.rules = []

        # Optional multiline support (e.g. block comments, docstrings)
        self.multiline_start = QRegularExpression()
        self.multiline_end = QRegularExpression()
        self.multiline_format = QTextCharFormat()

    def add_rule(self, pattern: str, format_name: str):
        """Add a highlighting rule using a theme color key."""
        if format_name in THEME:
            self.rules.append((QRegularExpression(pattern), THEME[format_name]))

    def add_rule_fmt(self, pattern: str, fmt: QTextCharFormat):
        """Add a highlighting rule with a custom QTextCharFormat."""
        self.rules.append((QRegularExpression(pattern), fmt))


class FeaturePlugin:
    """
    Base class for plugins that add IDE functionality beyond syntax highlighting.

    To create a new feature plugin:
      1. Subclass FeaturePlugin
      2. Set NAME and DESCRIPTION
      3. Implement activate() to wire up your feature (add docks, menus, etc.)
      4. Implement deactivate() to clean up
      5. Drop the file in plugins/features/
      6. It will be discovered and passed the main window on startup.

    Example:
        class MyPlugin(FeaturePlugin):
            NAME = "My Feature"
            DESCRIPTION = "Does something cool"

            def activate(self):
                self.window.menuBar().addMenu("My Menu")
    """

    NAME = ""
    DESCRIPTION = ""

    def __init__(self, main_window):
        self.window = main_window

    def activate(self):
        """Called once when the plugin is loaded. Wire up your feature here."""
        pass

    def deactivate(self):
        """Called when the plugin is disabled or the app closes."""
        pass


# ─────────────────────────────────────────────────────────────────────────────
# 3. Universal Highlighting Engine
# ─────────────────────────────────────────────────────────────────────────────

class UniversalHighlighter(QSyntaxHighlighter):
    """
    Drives any LanguagePlugin — applies its rules to each text block.
    Handles both single-line and multiline patterns.
    """

    def __init__(self, document, plugin: LanguagePlugin):
        super().__init__(document)
        self.plugin = plugin

    def highlightBlock(self, text):
        # Single-line rules
        for regex, fmt in self.plugin.rules:
            iterator = regex.globalMatch(text)
            while iterator.hasNext():
                match = iterator.next()
                self.setFormat(match.capturedStart(), match.capturedLength(), fmt)

        # Multiline rules (block comments, docstrings, etc.)
        self.setCurrentBlockState(0)

        if not self.plugin.multiline_start.pattern():
            return

        start_index = 0
        if self.previousBlockState() != 1:
            m = self.plugin.multiline_start.match(text)
            start_index = m.capturedStart() if m.hasMatch() else -1

        while start_index >= 0:
            end_match = self.plugin.multiline_end.match(text, start_index)
            if end_match.hasMatch():
                end_index = end_match.capturedStart()
                length = end_index - start_index + end_match.capturedLength()
            else:
                self.setCurrentBlockState(1)
                length = len(text) - start_index

            self.setFormat(start_index, length, self.plugin.multiline_format)

            next_match = self.plugin.multiline_start.match(text, start_index + length)
            start_index = next_match.capturedStart() if next_match.hasMatch() else -1


# ─────────────────────────────────────────────────────────────────────────────
# 4. Registry & Auto-Discovery
# ─────────────────────────────────────────────────────────────────────────────

class HighlighterRegistry:
    """
    Manages language plugin registration and highlighter creation.
    Supports both manual registration and automatic directory scanning.
    """

    def __init__(self):
        self._language_plugins: dict = {}
        self._feature_plugins: list = []

    # ── Language plugins ──────────────────────────────────────────

    def register(self, extension: str, plugin_class):
        """Manually register a language plugin for a file extension."""
        self._language_plugins[extension] = plugin_class

    def get_highlighter(self, document, extension: str = ".py"):
        """
        Returns a QSyntaxHighlighter for the given document and extension.
        Returns None if no plugin is registered for that extension.
        """
        plugin_class = self._language_plugins.get(extension)
        if plugin_class is None:
            return None

        # Standalone QSyntaxHighlighter subclasses (e.g. MarkdownPlugin)
        # are instantiated directly rather than wrapped
        if issubclass(plugin_class, QSyntaxHighlighter):
            return plugin_class(document)

        return UniversalHighlighter(document, plugin_class())

    def auto_register_languages(self, languages_dir: str):
        """
        Scans plugins/languages/ and registers every LanguagePlugin subclass
        that declares an EXTENSIONS list.

        To add a new language: drop a *_plugin.py file in plugins/languages/
        with EXTENSIONS = ['.xyz'] — no other changes needed.
        """
        if not os.path.isdir(languages_dir):
            print(f"Language plugins directory not found: {languages_dir}")
            return

        for filename in sorted(os.listdir(languages_dir)):
            if not filename.endswith('_plugin.py'):
                continue

            module_path = os.path.join(languages_dir, filename)
            module_name = f"plugins.languages.{filename[:-3]}"

            try:
                spec = importlib.util.spec_from_file_location(module_name, module_path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                for _, obj in inspect.getmembers(module, inspect.isclass):
                    if not inspect.isclass(obj):
                        continue
                    # Accept LanguagePlugin subclasses with EXTENSIONS
                    is_language = (
                        issubclass(obj, LanguagePlugin) and
                        obj is not LanguagePlugin and
                        obj.EXTENSIONS
                    )
                    # Also accept standalone QSyntaxHighlighter subclasses
                    # that declare EXTENSIONS (e.g. MarkdownPlugin)
                    is_standalone = (
                        issubclass(obj, QSyntaxHighlighter) and
                        not issubclass(obj, UniversalHighlighter) and
                        hasattr(obj, 'EXTENSIONS') and
                        obj.EXTENSIONS
                    )
                    if is_language or is_standalone:
                        for ext in obj.EXTENSIONS:
                            self.register(ext, obj)
                            print(f"  Registered: {ext} → {obj.__name__}")

            except Exception as e:
                print(f"Could not load language plugin '{filename}': {e}")

    # ── Feature plugins ───────────────────────────────────────────

    def auto_register_features(self, features_dir: str, main_window):
        """
        Scans plugins/features/ and activates every FeaturePlugin subclass.
        Each plugin receives the main window so it can add docks, menus, etc.
        """
        if not os.path.isdir(features_dir):
            return

        for filename in sorted(os.listdir(features_dir)):
            if not filename.endswith('_plugin.py'):
                continue

            module_path = os.path.join(features_dir, filename)
            module_name = f"plugins.features.{filename[:-3]}"

            try:
                spec = importlib.util.spec_from_file_location(module_name, module_path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                for _, obj in inspect.getmembers(module, inspect.isclass):
                    if (inspect.isclass(obj) and
                            issubclass(obj, FeaturePlugin) and
                            obj is not FeaturePlugin and
                            obj.NAME):
                        instance = obj(main_window)
                        instance.activate()
                        self._feature_plugins.append(instance)
                        print(f"  Activated feature: {obj.NAME}")

            except Exception as e:
                print(f"Could not load feature plugin '{filename}': {e}")

    def deactivate_all_features(self):
        """Call on app close to cleanly shut down all feature plugins."""
        for plugin in self._feature_plugins:
            try:
                plugin.deactivate()
            except Exception as e:
                print(f"Error deactivating {plugin.NAME}: {e}")
        self._feature_plugins.clear()

    @property
    def registered_extensions(self) -> list:
        """Returns all currently registered file extensions."""
        return sorted(self._language_plugins.keys())

    @property
    def active_features(self) -> list:
        """Returns names of all active feature plugins."""
        return [p.NAME for p in self._feature_plugins]


# Global registry instance
registry = HighlighterRegistry()