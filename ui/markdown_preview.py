import re
from PyQt6.QtWidgets import QDockWidget, QTextBrowser, QWidget, QVBoxLayout
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QTextCursor


class MarkdownPreviewDock(QDockWidget):
    def __init__(self, parent=None):
        super().__init__("Markdown Preview", parent)
        self.setObjectName("md_preview_dock")

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(300)
        self._debounce.timeout.connect(self._do_render)
        self._pending_text = ""

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        self.browser.setStyleSheet("""
            QTextBrowser {
                background-color: #1E1E1E;
                color: #D4D4D4;
                border: none;
                font-family: 'Inter', 'Segoe UI', sans-serif;
                font-size: 11pt;
                padding: 16px;
                line-height: 1.7;
            }
        """)
        layout.addWidget(self.browser)
        self.setWidget(container)

        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable |
            QDockWidget.DockWidgetFeature.DockWidgetMovable |
            QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )

    def update_preview(self, markdown_text: str):
        """Debounced — only renders after 300ms pause."""
        self._pending_text = markdown_text
        self._debounce.start()

    def _do_render(self):
        try:
            import markdown
            html_body = markdown.markdown(
                self._pending_text,
                extensions=[
                    'fenced_code',
                    'tables',
                    'nl2br',
                    'toc',
                    'attr_list',
                    'def_list',
                    'footnotes',
                    'admonition',
                    'sane_lists',
                ]
            )
        except ImportError:
            # Fallback if markdown module not available
            html_body = self._basic_render(self._pending_text)

        html = f"""
<!DOCTYPE html>
<html>
<head>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}

  body {{
    background-color: #1E1E1E;
    color: #D4D4D4;
    font-family: 'Inter', 'Segoe UI', 'Helvetica Neue', sans-serif;
    font-size: 15px;
    line-height: 1.8;
    padding: 24px 32px;
    max-width: 860px;
  }}

  h1, h2, h3, h4, h5, h6 {{
    color: #FFFFFF;
    font-weight: 600;
    line-height: 1.3;
    margin: 1.4em 0 0.5em 0;
  }}
  h1 {{ font-size: 2em; border-bottom: 1px solid #3E3E42; padding-bottom: 0.3em; }}
  h2 {{ font-size: 1.5em; border-bottom: 1px solid #3E3E42; padding-bottom: 0.2em; }}
  h3 {{ font-size: 1.25em; color: #CCCCCC; }}
  h4 {{ font-size: 1.1em; color: #AAAAAA; }}

  p {{
    margin: 0.8em 0;
  }}

  a {{
    color: #4EC9FF;
    text-decoration: none;
  }}
  a:hover {{
    text-decoration: underline;
  }}

  strong {{ color: #FFFFFF; font-weight: 600; }}
  em {{ color: #CE9178; font-style: italic; }}

  code {{
    background-color: #2A2A2D;
    color: #CE9178;
    font-family: 'Hack', 'JetBrains Mono', 'Fira Code', monospace;
    font-size: 0.9em;
    padding: 2px 6px;
    border-radius: 4px;
  }}

  pre {{
    background-color: #1A1A1C;
    border: 1px solid #3E3E42;
    border-radius: 8px;
    padding: 16px 20px;
    overflow-x: auto;
    margin: 1em 0;
  }}
  pre code {{
    background: none;
    color: #D4D4D4;
    padding: 0;
    font-size: 0.9em;
    line-height: 1.6;
  }}

  blockquote {{
    border-left: 3px solid #0E639C;
    margin: 1em 0;
    padding: 8px 16px;
    background-color: #1A2A3A;
    border-radius: 0 6px 6px 0;
    color: #AAAAAA;
    font-style: italic;
  }}

  ul, ol {{
    padding-left: 1.5em;
    margin: 0.8em 0;
  }}
  li {{
    margin: 0.3em 0;
    line-height: 1.7;
  }}
  li > p {{
    margin: 0.2em 0;
  }}

  table {{
    border-collapse: collapse;
    width: 100%;
    margin: 1em 0;
    font-size: 0.95em;
  }}
  th {{
    background-color: #2D2D30;
    color: #FFFFFF;
    font-weight: 600;
    text-align: left;
    padding: 8px 12px;
    border: 1px solid #3E3E42;
  }}
  td {{
    padding: 7px 12px;
    border: 1px solid #3E3E42;
    color: #CCCCCC;
  }}
  tr:nth-child(even) td {{
    background-color: #252526;
  }}
  tr:hover td {{
    background-color: #2A2D2E;
  }}

  hr {{
    border: none;
    border-top: 1px solid #3E3E42;
    margin: 1.5em 0;
  }}

  img {{
    max-width: 100%;
    border-radius: 6px;
  }}

  .toc {{
    background-color: #252526;
    border: 1px solid #3E3E42;
    border-radius: 6px;
    padding: 12px 16px;
    margin: 1em 0;
    font-size: 0.9em;
  }}
  .toc ul {{ margin: 0.3em 0; }}

  .admonition {{
    border-left: 4px solid #569CD6;
    background-color: #1A2233;
    padding: 10px 16px;
    border-radius: 0 6px 6px 0;
    margin: 1em 0;
  }}
  .admonition-title {{
    font-weight: bold;
    color: #569CD6;
    margin-bottom: 4px;
  }}
  .warning {{
    border-left-color: #F0A30A;
    background-color: #2A2010;
  }}
  .warning .admonition-title {{ color: #F0A30A; }}
  .danger, .error {{
    border-left-color: #F44336;
    background-color: #2A1010;
  }}
  .danger .admonition-title, .error .admonition-title {{ color: #F44336; }}
  .tip, .hint {{
    border-left-color: #4CAF50;
    background-color: #102010;
  }}
  .tip .admonition-title, .hint .admonition-title {{ color: #4CAF50; }}

  dl dt {{
    font-weight: bold;
    color: #CCCCCC;
    margin-top: 0.8em;
  }}
  dl dd {{
    margin-left: 1.5em;
    color: #AAAAAA;
  }}

  .footnote {{
    font-size: 0.85em;
    color: #888888;
    border-top: 1px solid #3E3E42;
    margin-top: 2em;
    padding-top: 0.5em;
  }}
</style>
</head>
<body>
{html_body}
</body>
</html>
"""
        # Preserve scroll position
        scrollbar = self.browser.verticalScrollBar()
        scroll_pos = scrollbar.value()
        was_at_bottom = scroll_pos == scrollbar.maximum()

        self.browser.setHtml(html)

        # Restore scroll — if at bottom stay at bottom, otherwise restore position
        if was_at_bottom:
            scrollbar.setValue(scrollbar.maximum())
        else:
            scrollbar.setValue(scroll_pos)

    def _basic_render(self, text: str) -> str:
        """Minimal fallback if markdown module isn't installed."""
        escaped = (text.replace("&", "&amp;")
                       .replace("<", "&lt;")
                       .replace(">", "&gt;"))
        lines = escaped.split('\n')
        html = []
        for line in lines:
            if line.startswith('# '):
                html.append(f'<h1>{line[2:]}</h1>')
            elif line.startswith('## '):
                html.append(f'<h2>{line[3:]}</h2>')
            elif line.startswith('### '):
                html.append(f'<h3>{line[4:]}</h3>')
            elif line.strip() == '':
                html.append('<br>')
            else:
                html.append(f'<p>{line}</p>')
        return '\n'.join(html)