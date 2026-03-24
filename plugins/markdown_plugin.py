from PyQt6.QtGui import QSyntaxHighlighter, QTextCharFormat, QColor, QFont
from PyQt6.QtCore import Qt
import re


class MarkdownPlugin(QSyntaxHighlighter):
    """Standalone highlighter for Markdown — bypasses UniversalHighlighter
    because it needs a code-block state machine."""

    def __init__(self, document):
        super().__init__(document)

        self.h1_fmt = self._fmt("#569CD6", bold=True, size=16)
        self.h2_fmt = self._fmt("#569CD6", bold=True, size=14)
        self.h3_fmt = self._fmt("#569CD6", bold=True, size=12)

        self.bold_fmt   = self._fmt("#D4D4D4", bold=True)
        self.italic_fmt = self._fmt("#D4D4D4", italic=True)

        self.code_fmt = self._fmt("#CE9178")
        self.code_fmt.setFontFamily("JetBrains Mono")
        self.code_fmt.setBackground(QColor("#2A2A2D"))

        self.codeblock_fmt = self._fmt("#CE9178")
        self.codeblock_fmt.setFontFamily("JetBrains Mono")
        self.codeblock_fmt.setBackground(QColor("#1A1A1C"))

        self.link_fmt       = self._fmt("#4EC9B0")
        self.link_fmt.setFontUnderline(True)

        self.bullet_fmt     = self._fmt("#608B4E", bold=True)
        self.blockquote_fmt = self._fmt("#888888", italic=True)
        self.hr_fmt         = self._fmt("#3E3E42")

    @staticmethod
    def _fmt(color, bold=False, italic=False, size=None):
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        if bold:
            fmt.setFontWeight(QFont.Weight.Bold)
        if italic:
            fmt.setFontItalic(True)
        if size:
            fmt.setFontPointSize(size)
        return fmt

    def highlightBlock(self, text):
        self.setCurrentBlockState(0)
        stripped = text.strip()

        # ── Code block state machine ──────────────────────────
        if self.previousBlockState() == 1:
            self.setFormat(0, len(text), self.codeblock_fmt)
            if stripped.startswith("```"):
                self.setCurrentBlockState(0)
            else:
                self.setCurrentBlockState(1)
            return

        if stripped.startswith("```"):
            self.setCurrentBlockState(1)
            self.setFormat(0, len(text), self.codeblock_fmt)
            return

        # ── Headings ──────────────────────────────────────────
        if re.match(r'^# ', text):
            self.setFormat(0, len(text), self.h1_fmt)
            return
        if re.match(r'^## ', text):
            self.setFormat(0, len(text), self.h2_fmt)
            return
        if re.match(r'^#{3,} ', text):
            self.setFormat(0, len(text), self.h3_fmt)
            return

        # ── Blockquote ────────────────────────────────────────
        if stripped.startswith(">"):
            self.setFormat(0, len(text), self.blockquote_fmt)
            return

        # ── Horizontal rule ───────────────────────────────────
        if re.match(r'^[-*_]{3,}\s*$', stripped):
            self.setFormat(0, len(text), self.hr_fmt)
            return

        # ── Bullet marker ─────────────────────────────────────
        m = re.match(r'^(\s*)([-*+]|\d+\.)\s', text)
        if m:
            self.setFormat(m.start(2), len(m.group(2)), self.bullet_fmt)

        # ── Inline rules ──────────────────────────────────────
        inline_rules = [
            (r'\*\*(.+?)\*\*',  self.bold_fmt),
            (r'__(.+?)__',      self.bold_fmt),
            (r'\*(.+?)\*',      self.italic_fmt),
            (r'_(.+?)_',        self.italic_fmt),
            (r'`[^`]+`',        self.code_fmt),
            (r'!?\[.+?\]\(.+?\)', self.link_fmt),
        ]
        for pattern, fmt in inline_rules:
            for match in re.finditer(pattern, text):
                self.setFormat(match.start(), match.end() - match.start(), fmt)