from editor.highlighter import LanguagePlugin, THEME
from PyQt6.QtCore import QRegularExpression

class HTMLPlugin(LanguagePlugin):
    def __init__(self):
        super().__init__()

        # HTML Tags (e.g., <div>, </span>)
        self.add_rule(r'</?[a-zA-Z0-9]+', 'tag')
        self.add_rule(r'>', 'tag')

        # Attributes (e.g., class=, id=)
        self.add_rule(r'\b[a-zA-Z0-9_-]+(?=\=)', 'attribute')

        # Strings (Attribute values)
        self.add_rule(r'"[^"]*"', 'string')
        self.add_rule(r"'[^']*'", 'string')

        # Multiline HTML Comments
        self.multiline_start = QRegularExpression(r'')
        self.multiline_format = THEME['comment']
