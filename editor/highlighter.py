from PyQt6.QtGui import QSyntaxHighlighter, QTextCharFormat, QColor, QFont
from PyQt6.QtCore import QRegularExpression

# -----------------------------------------
# 1. Theme Engine
# -----------------------------------------
def create_format(color_hex, style=''):
    """Helper to create QTextCharFormat with colors and styles."""
    fmt = QTextCharFormat()
    fmt.setForeground(QColor(color_hex))
    if 'bold' in style:
        fmt.setFontWeight(QFont.Weight.Bold)
    if 'italic' in style:
        fmt.setFontItalic(True)
    return fmt

# A Kate/Monokai-inspired dark theme
THEME = {
    'keyword': create_format('#F92672', 'bold'),    # Pink/Red
    'builtin': create_format('#66D9EF', 'italic'),  # Cyan
    'string': create_format('#E6DB74'),             # Yellow
    'comment': create_format('#75715E', 'italic'),  # Grey
    'number': create_format('#AE81FF'),             # Purple
    'class_def': create_format('#A6E22E', 'bold'),  # Green
    'func_def': create_format('#A6E22E', 'bold'),   # Green
    'tag': create_format('#F92672', 'bold'),        # Pink (HTML tags)
    'attribute': create_format('#A6E22E'),          # Green (HTML attributes)
}

# -----------------------------------------
# 2. Base Plugin Interface
# -----------------------------------------
class LanguagePlugin:
    """Base class for language syntax rules."""
    def __init__(self):
        self.rules = [] # List of tuples: (QRegularExpression, QTextCharFormat)

        # Multiline support
        self.multiline_start = QRegularExpression()
        self.multiline_end = QRegularExpression()
        self.multiline_format = QTextCharFormat()

    def add_rule(self, pattern, format_name):
        if format_name in THEME:
            self.rules.append((QRegularExpression(pattern), THEME[format_name]))

# -----------------------------------------
# 3. The Universal Engine
# -----------------------------------------
class UniversalHighlighter(QSyntaxHighlighter):
    def __init__(self, document, plugin: LanguagePlugin):
        super().__init__(document)
        self.plugin = plugin

    def highlightBlock(self, text):
        # 1. Apply single-line rules
        for regex, fmt in self.plugin.rules:
            iterator = regex.globalMatch(text)
            while iterator.hasNext():
                match = iterator.next()
                self.setFormat(match.capturedStart(), match.capturedLength(), fmt)

        # 2. Apply multiline rules (e.g., block comments, multi-line strings)
        self.setCurrentBlockState(0)

        # If the plugin doesn't have multiline rules, stop here.
        if self.plugin.multiline_start.pattern() == "":
            return

        startIndex = 0
        if self.previousBlockState() != 1:
            startIndex = text.find(self.plugin.multiline_start.pattern()) # Basic string find for start
            # For complex regex starts, you'd use self.plugin.multiline_start.match(text).capturedStart()

        while startIndex >= 0:
            match = self.plugin.multiline_end.match(text, startIndex)
            endIndex = match.capturedStart()
            matchLength = match.capturedLength()

            if endIndex == -1:
                self.setCurrentBlockState(1)
                commentLength = len(text) - startIndex
            else:
                commentLength = endIndex - startIndex + matchLength

            self.setFormat(startIndex, commentLength, self.plugin.multiline_format)
            startIndex = text.find(self.plugin.multiline_start.pattern(), startIndex + commentLength)

# -----------------------------------------
# 4. Registry System
# -----------------------------------------
class HighlighterRegistry:
    def __init__(self):
        self.plugins = {}

    def register(self, extension, plugin_class):
        self.plugins[extension] = plugin_class

    def get_highlighter(self, document, extension=".py"):
        plugin_class = self.plugins.get(extension)
        if plugin_class is None:
            return None

        # Check if it's a standalone QSyntaxHighlighter subclass
        # (like MarkdownPlugin) rather than a LanguagePlugin
        from PyQt6.QtGui import QSyntaxHighlighter
        if issubclass(plugin_class, QSyntaxHighlighter):
            return plugin_class(document)

        # Standard LanguagePlugin path
        return UniversalHighlighter(document, plugin_class())

# Create a global registry instance
registry = HighlighterRegistry()
