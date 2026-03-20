from editor.highlighter import LanguagePlugin, THEME
from PyQt6.QtCore import QRegularExpression

class PythonPlugin(LanguagePlugin):
    def __init__(self):
        super().__init__()

        # Keywords
        keywords = [
            r'\band\b', r'\bas\b', r'\bassert\b', r'\bbreak\b', r'\bclass\b', r'\bcontinue\b',
            r'\bdef\b', r'\bdel\b', r'\belif\b', r'\belse\b', r'\bexcept\b', r'\bFalse\b',
            r'\bfinally\b', r'\bfor\b', r'\bfrom\b', r'\bglobal\b', r'\bif\b', r'\bimport\b',
            r'\bin\b', r'\bis\b', r'\blambda\b', r'\bNone\b', r'\bnonlocal\b', r'\bnot\b',
            r'\bor\b', r'\bpass\b', r'\braise\b', r'\breturn\b', r'\bTrue\b', r'\btry\b',
            r'\bwhile\b', r'\bwith\b', r'\byield\b'
        ]
        for word in keywords:
            self.add_rule(word, 'keyword')

        # Builtins
        builtins = [r'\bprint\b', r'\blen\b', r'\bstr\b', r'\bint\b', r'\bfloat\b', r'\blist\b', r'\bdict\b']
        for word in builtins:
            self.add_rule(word, 'builtin')

        # Numbers
        self.add_rule(r'\b[0-9]+\b', 'number')

        # Strings (Single and Double quotes)
        self.add_rule(r'"[^"\\]*(\\.[^"\\]*)*"', 'string')
        self.add_rule(r"'[^'\\]*(\\.[^'\\]*)*'", 'string')

        # Comments
        self.add_rule(r'#[^\n]*', 'comment')

        # Functions and Classes (highlighting the word after def/class)
        self.add_rule(r'\bclass\s+([A-Za-z_]+)\b', 'class_def')
        self.add_rule(r'\bdef\s+([A-Za-z_]+)\b', 'func_def')

        # Multiline Strings (acting as multiline comments in Python)
        self.multiline_start = QRegularExpression(r'\"\"\"')
        self.multiline_end = QRegularExpression(r'\"\"\"')
        self.multiline_format = THEME['comment']
