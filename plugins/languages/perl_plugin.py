"""
plugins/languages/perl_plugin.py

Perl syntax highlighting plugin for QuillAI.
Covers keywords, builtins, sigils, regex literals, strings,
heredocs (start marker only), and comments.
"""

from editor.highlighter import LanguagePlugin, THEME
from PyQt6.QtCore import QRegularExpression


class PerlPlugin(LanguagePlugin):
    EXTENSIONS = ['.pl', '.pm', '.pod', '.t']

    def __init__(self):
        super().__init__()

        # ── Keywords ──────────────────────────────────────────────────────
        keywords = [
            r'\bif\b', r'\belsif\b', r'\belse\b', r'\bunless\b',
            r'\bwhile\b', r'\buntil\b', r'\bfor\b', r'\bforeach\b',
            r'\bdo\b', r'\bnext\b', r'\blast\b', r'\bredo\b',
            r'\breturn\b', r'\bsub\b', r'\bmy\b', r'\bour\b',
            r'\blocal\b', r'\buse\b', r'\bno\b', r'\brequire\b',
            r'\bpackage\b', r'\bbegin\b', r'\bend\b', r'\bdie\b',
            r'\bwarn\b', r'\bexit\b', r'\bundef\b', r'\bref\b',
            r'\bwantarray\b', r'\beval\b', r'\bgivenb\b', r'\bwhen\b',
            r'\bdefault\b', r'\band\b', r'\bor\b', r'\bnot\b',
            r'\bne\b', r'\beq\b', r'\blt\b', r'\bgt\b',
            r'\ble\b', r'\bge\b', r'\bcmp\b',
        ]
        for kw in keywords:
            self.add_rule(kw, 'keyword')

        # ── Built-in functions ────────────────────────────────────────────
        builtins = [
            r'\bprint\b', r'\bprintf\b', r'\bsay\b', r'\bsprintf\b',
            r'\bopen\b', r'\bclose\b', r'\bread\b', r'\bwrite\b',
            r'\bpush\b', r'\bpop\b', r'\bshift\b', r'\bunshift\b',
            r'\bsplice\b', r'\bjoin\b', r'\bsplit\b', r'\bsort\b',
            r'\breverse\b', r'\bmap\b', r'\bgrep\b', r'\bkeys\b',
            r'\bvalues\b', r'\beach\b', r'\bdelete\b', r'\bexists\b',
            r'\bdefined\b', r'\bscalar\b', r'\bchompchomp\b',
            r'\bchomp\b', r'\bchop\b', r'\blength\b', r'\bindex\b',
            r'\brindex\b', r'\bsubstr\b', r'\blc\b', r'\buc\b',
            r'\blcfirst\b', r'\bucfirst\b', r'\bchr\b', r'\bord\b',
            r'\bhex\b', r'\boct\b', r'\babs\b', r'\bint\b',
            r'\bsqrt\b', r'\brand\b', r'\bsrand\b', r'\btime\b',
            r'\blocaltime\b', r'\bgmtime\b', r'\bstat\b', r'\bchdir\b',
            r'\bmkdir\b', r'\bunlink\b', r'\brename\b', r'\bcopy\b',
            r'\bsystem\b', r'\bexec\b', r'\bwait\b', r'\bfork\b',
            r'\bpos\b', r'\bstudy\b', r'\bwq\b',
        ]
        for bi in builtins:
            self.add_rule(bi, 'builtin')

        # ── Sigils — $scalar, @array, %hash, &sub, *glob ─────────────────
        self.add_rule(r'[\$@%&\*][A-Za-z_]\w*', 'builtin')

        # ── Special variables ─────────────────────────────────────────────
        special_vars = [
            r'\$_', r'\$!', r'\$@', r'\$/', r'\$\\',
            r'\$,', r'\$"', r'\$;', r'\$0', r'\$\d+',
            r'\$\&', r'\$`', r"\$'", r'\$\+',
            r'\@_', r'\@ARGV', r'\@INC', r'\%ENV', r'\%INC',
            r'\$ARGV', r'\$ENV\b',
        ]
        for sv in special_vars:
            self.add_rule(sv, 'keyword')

        # ── Numbers ───────────────────────────────────────────────────────
        self.add_rule(r'\b0x[0-9A-Fa-f]+\b', 'number')
        self.add_rule(r'\b0b[01]+\b',         'number')
        self.add_rule(r'\b\d+\.?\d*\b',       'number')

        # ── Double-quoted strings ─────────────────────────────────────────
        self.add_rule(r'"[^"\\]*(\\.[^"\\]*)*"', 'string')

        # ── Single-quoted strings (no interpolation) ──────────────────────
        self.add_rule(r"'[^'\\]*(\\.[^'\\]*)*'", 'string')

        # ── qq{} qw{} q{} operators ───────────────────────────────────────
        self.add_rule(r'\bq[qwxr]?\s*[\{\[\(<]', 'string')

        # ── Regex literals  /.../ and m/.../  s/.../.../  tr/.../.../  ────
        self.add_rule(r'm\s*/[^/\\]*(\\.[^/\\]*)*/[gimsxe]*', 'string')
        self.add_rule(r's\s*/[^/\\]*(\\.[^/\\]*)*/[^/\\]*(\\.[^/\\]*)*/[gimsxe]*', 'string')
        self.add_rule(r'tr\s*/[^/]*/[^/]*/', 'string')
        # Bare /regex/ (heuristic — after = or ( or , or ! or not at start of line)
        self.add_rule(r'(?<=[=(,!~\s])/[^/\n\\]*(\\.[^/\n\\]*)*/[gimsxe]*', 'string')

        # ── POD blocks start marker ───────────────────────────────────────
        self.add_rule(r'^=(?:pod|head\d|over|item|back|begin|end|for|encoding)\b.*', 'comment')

        # ── Line comments ─────────────────────────────────────────────────
        self.add_rule(r'#[^\n]*', 'comment')

        # ── Subroutine definitions ────────────────────────────────────────
        self.add_rule(r'\bsub\s+([A-Za-z_]\w*)', 'func_def')

        # ── Package declarations ──────────────────────────────────────────
        self.add_rule(r'\bpackage\s+([A-Za-z_][\w:]*)', 'class_def')

        # ── Heredoc start markers (highlight the delimiter) ───────────────
        self.add_rule(r'<<\s*[\'"]?[A-Z_]+[\'"]?', 'string')

        # ── Multiline POD — =pod ... =cut ────────────────────────────────
        self.multiline_start  = QRegularExpression(r'^=pod\b')
        self.multiline_end    = QRegularExpression(r'^=cut\b')
        self.multiline_format = THEME['comment']