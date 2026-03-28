from PyQt6.QtGui import QTextCharFormat, QColor, QFont
from PyQt6.QtCore import QRegularExpression

# [NEW] Import your base class from the highlighter engine!
from editor.highlighter import LanguagePlugin

class AnsiblePlugin(LanguagePlugin):
    EXTENSIONS = ['.yml', '.yaml']
    def __init__(self):
        # [NEW] Call the parent init to set up self.rules and the multiline attributes
        super().__init__()

        # --- Define Color Formats ---

        # 1. YAML Keys (e.g., name:, hosts:, tasks:, apt:)
        key_format = QTextCharFormat()
        key_format.setForeground(QColor("#569CD6")) # VS Code Blue
        key_format.setFontWeight(QFont.Weight.Bold)
        self.rules.append((QRegularExpression(r'\b[\w-]+\s*(?=:)'), key_format))

        # 2. YAML List Dashes (-)
        dash_format = QTextCharFormat()
        dash_format.setForeground(QColor("#D4D4D4")) # Light Grey
        dash_format.setFontWeight(QFont.Weight.Bold)
        self.rules.append((QRegularExpression(r'^\s*-\s'), dash_format))

        # 3. Booleans (yes, no, true, false)
        boolean_format = QTextCharFormat()
        boolean_format.setForeground(QColor("#C586C0")) # Purple
        boolean_format.setFontWeight(QFont.Weight.Bold)
        self.rules.append((QRegularExpression(r'\b(true|false|yes|no)\b', QRegularExpression.PatternOption.CaseInsensitiveOption), boolean_format))

        # 4. Strings (Single and Double Quotes)
        string_format = QTextCharFormat()
        string_format.setForeground(QColor("#CE9178")) # Orange/Brown
        self.rules.append((QRegularExpression(r'".*?"'), string_format))
        self.rules.append((QRegularExpression(r"'.*?'"), string_format))

        # 5. Jinja2 Templating Variables ( {{ variable_name }} )
        jinja_format = QTextCharFormat()
        jinja_format.setForeground(QColor("#4EC9B0")) # Bright Cyan/Teal
        jinja_format.setBackground(QColor("#252526")) # Slight dark inset
        self.rules.append((QRegularExpression(r'\{\{.*?\}\}'), jinja_format))

        # 6. Comments (#)
        comment_format = QTextCharFormat()
        comment_format.setForeground(QColor("#6A9955")) # Green
        comment_format.setFontItalic(True)
        self.rules.append((QRegularExpression(r'#.*'), comment_format))
