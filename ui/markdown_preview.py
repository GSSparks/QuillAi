import re
from PyQt6.QtWidgets import QDockWidget, QTextBrowser, QWidget, QVBoxLayout
from PyQt6.QtCore import Qt, QTimer


def md_to_html(md: str) -> str:
    """Converts markdown to HTML. Handles the most common cases."""
    lines = md.split('\n')
    html_lines = []
    in_code_block = False
    code_lang = ""
    code_buf = []
    in_list = False
    in_blockquote = False

    def flush_list():
        nonlocal in_list
        if in_list:
            html_lines.append("</ul>")
            in_list = False

    def flush_blockquote():
        nonlocal in_blockquote
        if in_blockquote:
            html_lines.append("</blockquote>")
            in_blockquote = False

    def inline(text):
        # Escape HTML
        text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        # Images before links
        text = re.sub(r'!\[([^\]]*)\]\(([^)]+)\)',
                      r'<img src="\2" alt="\1" style="max-width:100%">', text)
        # Links
        text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)',
                      r'<a href="\2" style="color:#4EC9B0">\1</a>', text)
        # Bold
        text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
        text = re.sub(r'__(.+?)__',     r'<strong>\1</strong>', text)
        # Italic
        text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
        text = re.sub(r'_(.+?)_',   r'<em>\1</em>', text)
        # Inline code
        text = re.sub(r'`([^`]+)`',
                      r'<code style="background:#2A2A2D;color:#CE9178;'
                      r'padding:1px 4px;border-radius:3px;'
                      r'font-family:JetBrains Mono,monospace">\1</code>', text)
        # Strikethrough
        text = re.sub(r'~~(.+?)~~', r'<del>\1</del>', text)
        return text

    for line in lines:
        stripped = line.strip()

        # Code block toggle
        if stripped.startswith("```"):
            if in_code_block:
                code_html = '\n'.join(
                    l.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                    for l in code_buf
                )
                html_lines.append(
                    f'<pre style="background:#1A1A1C;color:#CE9178;'
                    f'padding:12px;border-radius:6px;overflow-x:auto;'
                    f'font-family:JetBrains Mono,monospace;font-size:10pt;'
                    f'border-left:3px solid #3E3E42">{code_html}</pre>'
                )
                code_buf = []
                in_code_block = False
            else:
                flush_list()
                flush_blockquote()
                code_lang = stripped[3:]
                in_code_block = True
            continue

        if in_code_block:
            code_buf.append(line)
            continue

        # Horizontal rule
        if re.match(r'^[-*_]{3,}\s*$', stripped):
            flush_list()
            flush_blockquote()
            html_lines.append('<hr style="border:none;border-top:1px solid #3E3E42;margin:16px 0">')
            continue

        # Blockquote
        if stripped.startswith(">"):
            flush_list()
            if not in_blockquote:
                html_lines.append(
                    '<blockquote style="border-left:3px solid #555;'
                    'margin:0;padding:4px 12px;color:#888888;font-style:italic">'
                )
                in_blockquote = True
            html_lines.append(f'<p style="margin:4px 0">{inline(stripped[1:].strip())}</p>')
            continue
        else:
            flush_blockquote()

        # Headings
        hm = re.match(r'^(#{1,6})\s+(.*)', stripped)
        if hm:
            flush_list()
            level = len(hm.group(1))
            sizes  = {1: "22pt", 2: "18pt", 3: "14pt", 4: "12pt", 5: "11pt", 6: "10pt"}
            borders = {1: "border-bottom:1px solid #3E3E42;padding-bottom:6px;margin-bottom:8px;"}
            style = (f"color:#569CD6;font-weight:bold;font-size:{sizes.get(level,'12pt')};"
                     f"margin:16px 0 8px;{borders.get(level,'')}")
            html_lines.append(f'<h{level} style="{style}">{inline(hm.group(2))}</h{level}>')
            continue

        # Unordered list
        lm = re.match(r'^(\s*)([-*+])\s+(.*)', line)
        if lm:
            if not in_list:
                html_lines.append('<ul style="padding-left:20px;margin:4px 0">')
                in_list = True
            html_lines.append(
                f'<li style="margin:3px 0;color:#D4D4D4">{inline(lm.group(3))}</li>'
            )
            continue

        # Ordered list
        om = re.match(r'^(\s*)\d+\.\s+(.*)', line)
        if om:
            flush_list()
            html_lines.append(
                f'<li style="margin:3px 0;color:#D4D4D4">{inline(om.group(2))}</li>'
            )
            continue

        flush_list()

        # Blank line
        if not stripped:
            html_lines.append('<br>')
            continue

        # Normal paragraph
        html_lines.append(f'<p style="margin:4px 0;color:#D4D4D4;line-height:1.6">{inline(stripped)}</p>')

    flush_list()
    flush_blockquote()

    return f"""
    <html><body style="
        background-color:#1E1E1E;
        color:#D4D4D4;
        font-family:Inter,'Segoe UI',sans-serif;
        font-size:11pt;
        padding:20px 28px;
        line-height:1.7;
        max-width:860px;
    ">
    {''.join(html_lines)}
    </body></html>
    """


class MarkdownPreviewDock(QDockWidget):
    def __init__(self, parent=None):
        super().__init__("Markdown Preview", parent)
        self.setStyleSheet("""
            QDockWidget {
                color: #CCCCCC;
                font-family: 'Inter', sans-serif;
                font-weight: bold;
                font-size: 10pt;
            }
            QDockWidget::title {
                background-color: #252526;
                padding: 6px 10px;
            }
        """)

        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        self.browser.setStyleSheet("""
            QTextBrowser {
                background-color: #1E1E1E;
                border: none;
                padding: 0;
            }
        """)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.browser)
        self.setWidget(container)

        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable |
            QDockWidget.DockWidgetFeature.DockWidgetMovable
        )

        # Debounce timer so we don't re-render on every single keystroke
        self._timer = QTimer()
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._do_render)
        self._pending_text = ""

    def update_preview(self, markdown_text: str):
        self._pending_text = markdown_text
        self._timer.start(300)

    def _do_render(self):
        scroll = self.browser.verticalScrollBar().value()
        self.browser.setHtml(md_to_html(self._pending_text))
        self.browser.verticalScrollBar().setValue(scroll)