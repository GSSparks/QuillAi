from PyQt6.QtGui import QTextCharFormat, QColor, QFont
from PyQt6.QtCore import QRegularExpression
from editor.highlighter import LanguagePlugin

class NixPlugin(LanguagePlugin):
    EXTENSIONS = ['.nix']
    def __init__(self):
        super().__init__()

        # --- Define Color Formats ---

        # 1. Keywords (let, in, with, inherit, rec, etc.)
        keyword_format = QTextCharFormat()
        keyword_format.setForeground(QColor("#C586C0")) # Purple
        keyword_format.setFontWeight(QFont.Weight.Bold)
        self.rules.append((QRegularExpression(r'\b(let|in|with|inherit|rec|if|then|else|assert)\b'), keyword_format))

        # 2. Constants (true, false, null)
        constant_format = QTextCharFormat()
        constant_format.setForeground(QColor("#569CD6")) # Blue
        constant_format.setFontWeight(QFont.Weight.Bold)
        self.rules.append((QRegularExpression(r'\b(true|false|null)\b'), constant_format))

        # 3. Builtins & Core Functions
        builtin_format = QTextCharFormat()
        builtin_format.setForeground(QColor("#4EC9B0")) # Teal
        self.rules.append((QRegularExpression(r'\b(builtins|import|derivation|map|fetchurl|fetchgit|fetchTarball)\b'), builtin_format))

        # 4. Assignment Attributes (e.g., the 'environment.systemPackages' before the '=')
        attr_format = QTextCharFormat()
        attr_format.setForeground(QColor("#9CDCFE")) # Light Blue
        self.rules.append((QRegularExpression(r'\b[a-zA-Z0-9_-]+\s*(?==)'), attr_format))

        # 5. Paths (e.g., ./configuration.nix or <nixpkgs>)
        path_format = QTextCharFormat()
        path_format.setForeground(QColor("#DCDCAA")) # Yellow
        self.rules.append((QRegularExpression(r'\b[a-zA-Z0-9_\-\.]*/[a-zA-Z0-9_\-\./]+\b'), path_format))
        self.rules.append((QRegularExpression(r'<[a-zA-Z0-9_\-\.]+>'), path_format))

        # 6. Strings (Standard and Indented)
        string_format = QTextCharFormat()
        string_format.setForeground(QColor("#CE9178")) # Orange/Brown
        self.rules.append((QRegularExpression(r'".*?"'), string_format))
        self.rules.append((QRegularExpression(r"''[\s\S]*?''"), string_format))

        # 7. Single-line Comments (#)
        comment_format = QTextCharFormat()
        comment_format.setForeground(QColor("#6A9955")) # Green
        comment_format.setFontItalic(True)
        self.rules.append((QRegularExpression(r'#.*'), comment_format))

        # 8. Multi-line Comments (/* ... */) 
        # Tapping into your awesome base class architecture for this!
        self.multiline_start = QRegularExpression(r'/\*')
        self.multiline_end = QRegularExpression(r'\*/')
        self.multiline_format = comment_format