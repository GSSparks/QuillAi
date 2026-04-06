# plugins/languages/env_plugin.py
from editor.highlighter import LanguagePlugin, THEME
from PyQt6.QtCore import QRegularExpression


class EnvPlugin(LanguagePlugin):
    EXTENSIONS = ['.env', '.env.local', '.env.development',
                  '.env.staging', '.env.production', '.env.test']

    def __init__(self):
        super().__init__()

        # Comments
        self.add_rule(r'#[^\n]*', 'comment')

        # Export keyword
        self.add_rule(r'\bexport\b', 'keyword')

        # Key (everything before the =)
        self.add_rule(r'^[\w]+(?==)', 'builtin')

        # Quoted values
        self.add_rule(r'"[^"\\]*(\\.[^"\\]*)*"', 'string')
        self.add_rule(r"'[^'\\]*(\\.[^'\\]*)*'", 'string')

        # Variable interpolation ${VAR} and $VAR
        self.add_rule(r'\$\{[\w]+\}', 'string2')
        self.add_rule(r'\$[\w]+', 'string2')

        # Likely secrets — highlight values for keys containing
        # SECRET, KEY, TOKEN, PASSWORD, PASS, PWD, PRIVATE
        self.add_rule(
            r'(?i)(?<=(?:SECRET|TOKEN|PASSWORD|PASS|PWD|KEY|PRIVATE)'
            r'(?:_\w+)?=)[^\n]+',
            'number'   # stands out — user knows to be careful
        )

        # Numbers
        self.add_rule(r'\b[0-9]+\b', 'number')

        # URLs
        self.add_rule(r'https?://[^\s\n]+', 'string2')