import os
import importlib.util
import inspect
from PyQt6.QtGui import QSyntaxHighlighter, QTextCharFormat, QColor, QFont
from PyQt6.QtCore import QRegularExpression


# ─────────────────────────────────────────────────────────────────────────────
# 1. Syntax Highlighting Color Engine
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


def build_syntax_theme(ui_theme: dict) -> dict:
    """
    Builds the syntax highlighting palette from the UI theme.
    All syntax colors come from the same palette the UI uses,
    so switching themes changes everything — UI chrome and code colors together.

    Semantic mapping:
      keywords    → red      (control flow, language keywords)
      builtins    → aqua     (built-in functions and types)
      strings     → yellow   (string literals)
      comments    → fg4      (muted — least important)
      numbers     → purple   (numeric literals)
      class/func  → green    (definitions — most important)
      tags        → red      (HTML/XML tags)
      attributes  → green    (HTML attributes, decorators)
      types       → aqua     (type annotations)
      constants   → purple   (True, False, None, etc.)
      operators   → orange   (operators, special symbols)
    """
    return {
        'keyword':   create_format(ui_theme['red'],    'bold'),
        'builtin':   create_format(ui_theme['aqua'],   'italic'),
        'string':    create_format(ui_theme['yellow']),
        'comment':   create_format(ui_theme['fg4'],    'italic'),
        'number':    create_format(ui_theme['purple']),
        'class_def': create_format(ui_theme['green'],  'bold'),
        'func_def':  create_format(ui_theme['green'],  'bold'),
        'tag':       create_format(ui_theme['red'],    'bold'),
        'attribute': create_format(ui_theme['green']),
        'decorator': create_format(ui_theme['green']),
        'type':      create_format(ui_theme['aqua'],   'italic'),
        'constant':  create_format(ui_theme['purple']),
        'operator':  create_format(ui_theme['orange']),
    }


# Bootstrap with the default theme — replaced immediately when apply_theme runs
def _bootstrap_theme() -> dict:
    from ui.theme import get_theme
    return build_syntax_theme(get_theme())


THEME: dict = {}


def refresh_syntax_theme(ui_theme: dict):
    """
    Rebuilds the global THEME dict in place from the given UI theme.
    Called by apply_theme() whenever the user switches themes.
    All subsequent highlighting passes will use the new colors.
    """
    global THEME
    THEME.clear()
    THEME.update(build_syntax_theme(ui_theme))


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

    Color keys available in add_rule():
        'keyword'   'builtin'   'string'    'comment'
        'number'    'class_def' 'func_def'  'tag'
        'attribute' 'decorator' 'type'      'constant'
        'operator'
    """

    EXTENSIONS = []

    def __init__(self):
        self.rules = []
        self.multiline_start  = QRegularExpression()
        self.multiline_end    = QRegularExpression()
        self.multiline_format = QTextCharFormat()

    def add_rule(self, pattern: str, format_name: str):
        """
        Add a highlighting rule using a semantic color key.
        Rules are applied in order — later rules take precedence.
        """
        if format_name in THEME:
            self.rules.append((QRegularExpression(pattern), THEME[format_name]))

    def add_rule_fmt(self, pattern: str, fmt: QTextCharFormat):
        """Add a highlighting rule with a fully custom QTextCharFormat."""
        self.rules.append((QRegularExpression(pattern), fmt))


class FeaturePlugin:
    """
    Base class for plugins that add IDE functionality beyond syntax highlighting.

    To create a new feature plugin:
      1. Subclass FeaturePlugin
      2. Set NAME and DESCRIPTION
      3. Implement activate() to wire up your feature (docks, menus, shortcuts)
      4. Implement deactivate() to clean up on close
      5. Drop the file in plugins/features/
      6. It will be discovered and activated automatically on startup.

    Example:
        class TodoPlugin(FeaturePlugin):
            NAME = "TODO Panel"
            DESCRIPTION = "Shows a panel of TODO comments across the project"

            def activate(self):
                self.dock = QDockWidget("TODOs", self.window)
                self.window.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.dock)

            def deactivate(self):
                self.dock.deleteLater()
    """

    NAME = ""
    DESCRIPTION = ""

    def __init__(self, main_window):
        self.window = main_window

    def activate(self):
        """Called once when the plugin is loaded. Wire up your feature here."""
        pass

    def deactivate(self):
        """Called on app close or when the plugin is disabled."""
        pass


# ─────────────────────────────────────────────────────────────────────────────
# 3. Universal Highlighting Engine
# ─────────────────────────────────────────────────────────────────────────────

class UniversalHighlighter(QSyntaxHighlighter):
    """
    Drives any LanguagePlugin — applies its rules to each text block.
    Handles both single-line and multiline patterns (docstrings, block comments).
    """

    def __init__(self, document, plugin: LanguagePlugin):
        super().__init__(document)
        self.plugin = plugin

    def highlightBlock(self, text):
        # ── Single-line rules ─────────────────────────────────────
        for regex, fmt in self.plugin.rules:
            iterator = regex.globalMatch(text)
            while iterator.hasNext():
                match = iterator.next()
                self.setFormat(
                    match.capturedStart(), match.capturedLength(), fmt
                )

        # ── Multiline rules (docstrings, block comments) ──────────
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

            next_match = self.plugin.multiline_start.match(
                text, start_index + length
            )
            start_index = (
                next_match.capturedStart() if next_match.hasMatch() else -1
            )


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
        self._feature_plugins: list  = []
        self._filename_map: dict[str, type] = {}

    # ── Language plugins ──────────────────────────────────────────

    def register(self, extension: str, plugin_class):
        """Manually register a language plugin for a file extension."""
        self._language_plugins[extension] = plugin_class

    def auto_register_languages(self, languages_dir: str):
        """
        Scans plugins/languages/ and registers every LanguagePlugin subclass
        that declares an EXTENSIONS or FILENAMES list.
    
        To add a new language: drop a *_plugin.py in plugins/languages/
        with EXTENSIONS = ['.xyz'] and/or FILENAMES = ['Dockerfile']
        — zero other changes needed anywhere.
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
                spec = importlib.util.spec_from_file_location(
                    module_name, module_path
                )
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
    
                for _, obj in inspect.getmembers(module, inspect.isclass):
                    if not inspect.isclass(obj):
                        continue
    
                    is_language = (
                        issubclass(obj, LanguagePlugin) and
                        obj is not LanguagePlugin and
                        (obj.EXTENSIONS or getattr(obj, 'FILENAMES', None))
                    )
                    is_standalone = (
                        issubclass(obj, QSyntaxHighlighter) and
                        not issubclass(obj, UniversalHighlighter) and
                        hasattr(obj, 'EXTENSIONS') and
                        obj.EXTENSIONS
                    )
    
                    if is_language or is_standalone:
                        # Register by extension
                        for ext in obj.EXTENSIONS:
                            self.register(ext, obj)
    
                        # Register by exact filename
                        for fname in getattr(obj, 'FILENAMES', []):
                            self.register_filename(fname, obj)
    
            except Exception as e:
                print(f"Could not load language plugin '{filename}': {e}")
                
    def register_filename(self, filename: str, plugin_class):
        """Register a highlighter for an exact filename (e.g. 'Dockerfile')."""
        self._filename_map[filename.lower()] = plugin_class
    
    def get_highlighter(self, document, ext_or_path: str = ""):
        """
        Return a highlighter instance for the given extension or file path.
        Checks exact filename first, then extension.
        """
        if not ext_or_path:
            return None

        # Check exact filename match first
        basename = os.path.basename(ext_or_path).lower()
        if basename in self._filename_map:
            plugin_class = self._filename_map[basename]
            if issubclass(plugin_class, QSyntaxHighlighter):
                return plugin_class(document)
            return UniversalHighlighter(document, plugin_class())

        # Fall back to extension
        ext = ext_or_path if ext_or_path.startswith('.') \
            else os.path.splitext(ext_or_path)[1].lower()

        plugin_class = self._language_plugins.get(ext)
        if plugin_class is None:
            return None

        if issubclass(plugin_class, QSyntaxHighlighter):
            return plugin_class(document)

        return UniversalHighlighter(document, plugin_class())

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
                spec = importlib.util.spec_from_file_location(
                    module_name, module_path
                )
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

    def on_theme_changed(self, ui_theme: dict):
        """
        Called by apply_theme() when the user switches UI themes.
        Rebuilds the syntax color palette so code highlighting
        matches the new theme automatically.
        """
        refresh_syntax_theme(ui_theme)

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
        """Returns names of all currently active feature plugins."""
        return [p.NAME for p in self._feature_plugins]


# ─────────────────────────────────────────────────────────────────────────────
# Global registry instance
# ─────────────────────────────────────────────────────────────────────────────
registry = HighlighterRegistry()


# Bootstrap the syntax theme using the default UI theme.
# This runs once at import time so THEME is populated before any plugin loads.
# apply_theme() will call refresh_syntax_theme() again with the user's saved
# theme on startup, and again whenever they switch themes at runtime.
try:
    from ui.theme import get_theme as _get_theme
    THEME.update(build_syntax_theme(_get_theme()))
except Exception:
    # Fallback to hardcoded Monokai if theme system isn't available yet
    # (e.g. during unit testing or early import)
    THEME.update({
        'keyword':   create_format('#F92672', 'bold'),
        'builtin':   create_format('#66D9EF', 'italic'),
        'string':    create_format('#E6DB74'),
        'comment':   create_format('#75715E', 'italic'),
        'number':    create_format('#AE81FF'),
        'class_def': create_format('#A6E22E', 'bold'),
        'func_def':  create_format('#A6E22E', 'bold'),
        'tag':       create_format('#F92672', 'bold'),
        'attribute': create_format('#A6E22E'),
        'decorator': create_format('#A6E22E'),
        'type':      create_format('#66D9EF', 'italic'),
        'constant':  create_format('#AE81FF'),
        'operator':  create_format('#FD971F'),
    })
