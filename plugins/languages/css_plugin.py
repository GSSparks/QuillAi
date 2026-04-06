from editor.highlighter import LanguagePlugin, THEME
from PyQt6.QtCore import QRegularExpression


class CSSPlugin(LanguagePlugin):
    EXTENSIONS = ['.css', '.scss', '.sass', '.less']

    def __init__(self):
        super().__init__()

        # ── At-rules (@import, @media, @keyframes, etc.) ──────────────────
        at_rules = [
            r'@import\b', r'@media\b', r'@keyframes\b', r'@font-face\b',
            r'@charset\b', r'@namespace\b', r'@supports\b', r'@layer\b',
            r'@container\b', r'@page\b', r'@counter-style\b',
            # SCSS/Less specific
            r'@mixin\b', r'@include\b', r'@extend\b', r'@function\b',
            r'@return\b', r'@each\b', r'@for\b', r'@while\b', r'@if\b',
            r'@else\b', r'@use\b', r'@forward\b',
        ]
        for rule in at_rules:
            self.add_rule(rule, 'keyword')

        # ── Important keyword ─────────────────────────────────────────────
        self.add_rule(r'!important\b', 'keyword')

        # ── Property names (word before :) ────────────────────────────────
        self.add_rule(r'\b[\w-]+\s*(?=:)', 'builtin')

        # ── Pseudo-classes and pseudo-elements ────────────────────────────
        self.add_rule(r':{1,2}[\w-]+', 'keyword')

        # ── Selectors — tags ─────────────────────────────────────────────
        html_tags = (
            r'\b(html|body|div|span|p|a|ul|ol|li|h[1-6]|header|footer|'
            r'main|nav|section|article|aside|table|thead|tbody|tr|th|td|'
            r'form|input|button|select|textarea|img|video|audio|canvas|'
            r'pre|code|blockquote|figure|figcaption|label|fieldset|'
            r'legend|details|summary|dialog|template)\b'
        )
        self.add_rule(html_tags, 'keyword')

        # ── Class and ID selectors ────────────────────────────────────────
        self.add_rule(r'\.[a-zA-Z_][\w-]*', 'func_def')
        self.add_rule(r'#[a-zA-Z_][\w-]*', 'class_def')

        # ── CSS variables (--custom-property) ────────────────────────────
        self.add_rule(r'--[\w-]+', 'string2')

        # ── var(), env(), calc() and other functions ──────────────────────
        css_functions = [
            r'\bvar\b', r'\bcalc\b', r'\benv\b', r'\bmin\b', r'\bmax\b',
            r'\bclamp\b', r'\brgb\b', r'\brgba\b', r'\bhsl\b', r'\bhsla\b',
            r'\blinear-gradient\b', r'\bradial-gradient\b',
            r'\bconic-gradient\b', r'\brepeating-linear-gradient\b',
            r'\btranslate\b', r'\bscale\b', r'\brotate\b', r'\bskew\b',
            r'\bmatrix\b', r'\bperspective\b',
            r'\burl\b', r'\bformat\b', r'\blocal\b',
            r'\bcubic-bezier\b', r'\bsteps\b',
            # SCSS functions
            r'\bdarken\b', r'\blighten\b', r'\bmix\b', r'\bopacify\b',
            r'\btransparentize\b', r'\bdesaturate\b', r'\bsaturate\b',
        ]
        for fn in css_functions:
            self.add_rule(fn, 'builtin')

        # ── SCSS/Less variables ($var, @var) ──────────────────────────────
        self.add_rule(r'\$[\w-]+', 'string2')
        self.add_rule(r'@[\w-]+(?!\s*[:({])', 'string2')

        # ── SCSS/Less interpolation #{...} ────────────────────────────────
        self.add_rule(r'#\{[^}]*\}', 'string2')

        # ── Numbers with units ────────────────────────────────────────────
        self.add_rule(
            r'-?[0-9]+(\.[0-9]+)?(px|em|rem|vh|vw|vmin|vmax|%|s|ms|'
            r'deg|rad|turn|fr|ch|ex|cm|mm|in|pt|pc)?\b',
            'number'
        )

        # ── Hex colors ────────────────────────────────────────────────────
        self.add_rule(r'#[0-9a-fA-F]{3,8}\b', 'string')

        # ── Strings ───────────────────────────────────────────────────────
        self.add_rule(r'"[^"\\]*(\\.[^"\\]*)*"', 'string')
        self.add_rule(r"'[^'\\]*(\\.[^'\\]*)*'", 'string')

        # ── Operators and combinators ─────────────────────────────────────
        self.add_rule(r'[>~\+\*\|]', 'operator')

        # ── Comments ─────────────────────────────────────────────────────
        # SCSS/Less single-line
        self.add_rule(r'//[^\n]*', 'comment')

        # ── Multiline comments /* ... */ ──────────────────────────────────
        self.multiline_start  = QRegularExpression(r'/\*')
        self.multiline_end    = QRegularExpression(r'\*/')
        self.multiline_format = THEME['comment']