# plugins/languages/dockerfile_plugin.py
from editor.highlighter import LanguagePlugin, THEME
from PyQt6.QtCore import QRegularExpression


class DockerfilePlugin(LanguagePlugin):
    EXTENSIONS = ['.dockerfile']
    FILENAMES  = ['Dockerfile', 'Dockerfile.dev', 'Dockerfile.prod',
                  'Dockerfile.test', 'containerfile', 'Containerfile']

    def __init__(self):
        super().__init__()

        # Instructions
        instructions = [
            r'\bFROM\b', r'\bRUN\b', r'\bCMD\b', r'\bLABEL\b',
            r'\bEXPOSE\b', r'\bENV\b', r'\bADD\b', r'\bCOPY\b',
            r'\bENTRYPOINT\b', r'\bVOLUME\b', r'\bUSER\b',
            r'\bWORKDIR\b', r'\bARG\b', r'\bONBUILD\b',
            r'\bSTOPSIGNAL\b', r'\bHEALTHCHECK\b', r'\bSHELL\b',
            r'\bMAINTAINER\b',
        ]
        for inst in instructions:
            self.add_rule(inst, 'keyword')

        # Stage names (AS name in FROM)
        self.add_rule(r'(?<=\bAS\s)\w+', 'class_def')
        self.add_rule(r'\bAS\b', 'keyword')

        # Variables ${VAR} and $VAR
        self.add_rule(r'\$\{[\w]+\}', 'string2')
        self.add_rule(r'\$[\w]+', 'string2')

        # Strings
        self.add_rule(r'"[^"\\]*(\\.[^"\\]*)*"', 'string')
        self.add_rule(r"'[^'\\]*(\\.[^'\\]*)*'", 'string')

        # Numbers and ports
        self.add_rule(r'\b[0-9]+\b', 'number')

        # Comments
        self.add_rule(r'#[^\n]*', 'comment')

        # Line continuation
        self.add_rule(r'\\$', 'operator')