from PyQt6.QtGui import QTextCharFormat, QColor, QFont
from PyQt6.QtCore import QRegularExpression
from editor.highlighter import LanguagePlugin

class BashPlugin(LanguagePlugin):
    EXTENSIONS = ['.sh', '.bash']
    def __init__(self):
        super().__init__()

        # 1. Keywords (if, then, fi, for, while, echo, etc.)
        keyword_format = QTextCharFormat()
        keyword_format.setForeground(QColor("#C586C0")) # Purple
        keyword_format.setFontWeight(QFont.Weight.Bold)
        keywords = r'\b(if|then|elif|else|fi|for|while|in|do|done|case|esac|function|return|exit|echo|read|set|export|source|alias|local)\b'
        self.rules.append((QRegularExpression(keywords), keyword_format))

        # 2. Bash Variables ($VAR or ${VAR})
        var_format = QTextCharFormat()
        var_format.setForeground(QColor("#9CDCFE")) # Light Blue
        self.rules.append((QRegularExpression(r'\$[a-zA-Z_][a-zA-Z0-9_]*'), var_format))
        self.rules.append((QRegularExpression(r'\$\{[^}]+\}'), var_format))

        # 3. Command Substitution ($(cmd) or `cmd`)
        cmd_format = QTextCharFormat()
        cmd_format.setForeground(QColor("#4EC9B0")) # Teal
        self.rules.append((QRegularExpression(r'\$\([^)]+\)'), cmd_format))
        self.rules.append((QRegularExpression(r'`[^`]+`'), cmd_format))

        # 4. Strings (Single and Double)
        string_format = QTextCharFormat()
        string_format.setForeground(QColor("#CE9178")) # Orange
        self.rules.append((QRegularExpression(r'".*?"'), string_format))
        self.rules.append((QRegularExpression(r"'.*?'"), string_format))

        # 5. Comments (#)
        comment_format = QTextCharFormat()
        comment_format.setForeground(QColor("#6A9955")) # Green
        comment_format.setFontItalic(True)
        self.rules.append((QRegularExpression(r'(?<!\$)#.*'), comment_format)) # Ignore $# (num args)