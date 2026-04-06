from editor.highlighter import LanguagePlugin, THEME
from PyQt6.QtCore import QRegularExpression


class NixPlugin(LanguagePlugin):
    EXTENSIONS = ['.nix']

    def __init__(self):
        super().__init__()

        # ── Keywords ──────────────────────────────────────────────────────
        keywords = [
            r'\blet\b', r'\bin\b', r'\bwith\b', r'\binherit\b', r'\brec\b',
            r'\bif\b', r'\bthen\b', r'\belse\b', r'\bassert\b', r'\bor\b',
        ]
        for kw in keywords:
            self.add_rule(kw, 'keyword')

        # ── Constants ─────────────────────────────────────────────────────
        for c in [r'\btrue\b', r'\bfalse\b', r'\bnull\b']:
            self.add_rule(c, 'number')

        # ── Built-in functions ────────────────────────────────────────────
        builtins = [
            r'\bbuiltins\b', r'\bimport\b', r'\bderivation\b',
            r'\bmap\b', r'\bfilter\b', r'\bfoldl\b', r'\bfoldl\'\b',
            r'\bfetchurl\b', r'\bfetchgit\b', r'\bfetchTarball\b',
            r'\bfetchFromGitHub\b', r'\bfetchFromGitLab\b',
            r'\bmkDerivation\b', r'\bmkShell\b', r'\bmkIf\b',
            r'\bmkMerge\b', r'\bmkForce\b', r'\bmkDefault\b',
            r'\bmkOption\b', r'\btypes\b', r'\blib\b',
            r'\bpkgs\b', r'\bnixpkgs\b', r'\bstdenv\b',
            r'\bwithPackages\b', r'\bcallPackage\b', r'\boverrideAttrs\b',
        ]
        for fn in builtins:
            self.add_rule(fn, 'builtin')

        # ── Attribute names (word before =) ──────────────────────────────
        self.add_rule(r'\b[\w-]+\s*(?==(?!=))', 'keyword')

        # ── Paths (./foo/bar or <nixpkgs>) ────────────────────────────────
        self.add_rule(r'\.{0,2}/[\w\-\./]+', 'string2')
        self.add_rule(r'<[\w\-\.]+>', 'string2')

        # ── Numbers ───────────────────────────────────────────────────────
        self.add_rule(r'\b[0-9]+(\.[0-9]+)?\b', 'number')

        # ── Strings ───────────────────────────────────────────────────────
        self.add_rule(r'"[^"\\]*(\\.[^"\\]*)*"', 'string')

        # ── String interpolation ${ ... } ────────────────────────────────
        self.add_rule(r'\$\{[^}]*\}', 'builtin')

        # ── Operators ────────────────────────────────────────────────────
        self.add_rule(r'[=\+\?\.\!\@\/\\]', 'operator')
        self.add_rule(r'\+\+', 'operator')   # list concat
        self.add_rule(r'//', 'operator')      # update operator

        # ── Single-line comments ──────────────────────────────────────────
        self.add_rule(r'#[^\n]*', 'comment')

        # ── Multiline comments /* ... */ ──────────────────────────────────
        self.multiline_start  = QRegularExpression(r'/\*')
        self.multiline_end    = QRegularExpression(r'\*/')
        self.multiline_format = THEME['comment']

        # ── Indented strings '' ... '' ────────────────────────────────────
        self.multiline_start  = QRegularExpression(r"''")
        self.multiline_end    = QRegularExpression(r"''")
        self.multiline_format = THEME['string']