import re
from PyQt6.QtWidgets import QDockWidget, QTextBrowser, QWidget, QVBoxLayout
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QTextCursor

from ui.theme import get_theme


class MarkdownPreviewDock(QDockWidget):
    def __init__(self, parent=None):
        super().__init__("Markdown Preview", parent)
        self.setObjectName("md_preview_dock")

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(300)
        self._debounce.timeout.connect(self._do_render)
        self._pending_text = ""
        self._parent = parent

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        self._apply_browser_style()
        layout.addWidget(self.browser)
        self.setWidget(container)

        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable |
            QDockWidget.DockWidgetFeature.DockWidgetMovable |
            QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )

    def _get_theme(self) -> dict:
        theme_name = None
        if self._parent and hasattr(self._parent, 'settings_manager'):
            theme_name = self._parent.settings_manager.get('theme')
        return get_theme(theme_name or 'gruvbox_dark')

    def _apply_browser_style(self):
        t = self._get_theme()
        self.browser.setStyleSheet(f"""
            QTextBrowser {{
                background-color: {t['bg0_hard']};
                color: {t['fg1']};
                border: none;
                font-family: 'Inter', 'Segoe UI', sans-serif;
                font-size: 11pt;
                padding: 16px;
                line-height: 1.7;
            }}
        """)

    def update_preview(self, markdown_text: str):
        self._pending_text = markdown_text
        self._debounce.start()

    def _do_render(self):
        t = self._get_theme()

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
            html_body = self._basic_render(self._pending_text)

        html = f"""
<!DOCTYPE html>
<html>
<head>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}

  body {{
    background-color: {t['bg0_hard']};
    color: {t['fg1']};
    font-family: 'Inter', 'Segoe UI', 'Helvetica Neue', sans-serif;
    font-size: 15px;
    line-height: 1.8;
    padding: 24px 32px;
    max-width: 860px;
  }}

  h1, h2, h3, h4, h5, h6 {{
    color: {t['fg0']};
    font-weight: 600;
    line-height: 1.3;
    margin: 1.4em 0 0.5em 0;
  }}
  h1 {{ font-size: 2em; border-bottom: 1px solid {t['border']}; padding-bottom: 0.3em; }}
  h2 {{ font-size: 1.5em; border-bottom: 1px solid {t['border']}; padding-bottom: 0.2em; }}
  h3 {{ font-size: 1.25em; color: {t['fg2']}; }}
  h4 {{ font-size: 1.1em; color: {t['fg3']}; }}

  p {{ margin: 0.8em 0; }}

  a {{ color: {t['aqua']}; text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}

  strong {{ color: {t['fg0']}; font-weight: 600; }}
  em {{ color: {t['orange']}; font-style: italic; }}

  code {{
    background-color: {t['bg2']};
    color: {t['orange']};
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.9em;
    padding: 2px 6px;
    border-radius: 4px;
  }}

  pre {{
    background-color: {t['bg1']};
    border: 1px solid {t['border']};
    border-radius: 8px;
    padding: 16px 20px;
    overflow-x: auto;
    margin: 1em 0;
  }}
  pre code {{
    background: none;
    color: {t['fg1']};
    padding: 0;
    font-size: 0.9em;
    line-height: 1.6;
  }}

  blockquote {{
    border-left: 3px solid {t['blue']};
    margin: 1em 0;
    padding: 8px 16px;
    background-color: {t['bg1']};
    border-radius: 0 6px 6px 0;
    color: {t['fg3']};
    font-style: italic;
  }}

  ul, ol {{ padding-left: 1.5em; margin: 0.8em 0; }}
  li {{ margin: 0.3em 0; line-height: 1.7; }}
  li > p {{ margin: 0.2em 0; }}

  table {{
    border-collapse: collapse;
    width: 100%;
    margin: 1em 0;
    font-size: 0.95em;
  }}
  th {{
    background-color: {t['bg2']};
    color: {t['fg0']};
    font-weight: 600;
    text-align: left;
    padding: 8px 12px;
    border: 1px solid {t['border']};
  }}
  td {{
    padding: 7px 12px;
    border: 1px solid {t['border']};
    color: {t['fg2']};
  }}
  tr:nth-child(even) td {{ background-color: {t['bg1']}; }}
  tr:hover td {{ background-color: {t['bg2']}; }}

  hr {{
    border: none;
    border-top: 1px solid {t['border']};
    margin: 1.5em 0;
  }}

  img {{ max-width: 100%; border-radius: 6px; }}

  .toc {{
    background-color: {t['bg1']};
    border: 1px solid {t['border']};
    border-radius: 6px;
    padding: 12px 16px;
    margin: 1em 0;
    font-size: 0.9em;
  }}
  .toc ul {{ margin: 0.3em 0; }}

  .admonition {{
    border-left: 4px solid {t['blue']};
    background-color: {t['bg1']};
    padding: 10px 16px;
    border-radius: 0 6px 6px 0;
    margin: 1em 0;
  }}
  .admonition-title {{
    font-weight: bold;
    color: {t['blue']};
    margin-bottom: 4px;
  }}
  .warning {{
    border-left-color: {t['yellow']};
    background-color: {t['bg1']};
  }}
  .warning .admonition-title {{ color: {t['yellow']}; }}
  .danger, .error {{
    border-left-color: {t['red']};
    background-color: {t['bg1']};
  }}
  .danger .admonition-title, .error .admonition-title {{ color: {t['red']}; }}
  .tip, .hint {{
    border-left-color: {t['green']};
    background-color: {t['bg1']};
  }}
  .tip .admonition-title, .hint .admonition-title {{ color: {t['green']}; }}

  dl dt {{
    font-weight: bold;
    color: {t['fg2']};
    margin-top: 0.8em;
  }}
  dl dd {{
    margin-left: 1.5em;
    color: {t['fg3']};
  }}

  .footnote {{
    font-size: 0.85em;
    color: {t['fg4']};
    border-top: 1px solid {t['border']};
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
        scrollbar = self.browser.verticalScrollBar()
        scroll_pos = scrollbar.value()
        was_at_bottom = scroll_pos == scrollbar.maximum()

        self.browser.setHtml(html)

        if was_at_bottom:
            scrollbar.setValue(scrollbar.maximum())
        else:
            scrollbar.setValue(scroll_pos)

    def _basic_render(self, text: str) -> str:
        t = self._get_theme()
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