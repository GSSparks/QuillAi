from PyQt6.QtWidgets import QDockWidget, QTextBrowser, QWidget, QVBoxLayout
from PyQt6.QtCore import QTimer

from ui.theme import (get_theme, theme_signals,
                      build_markdown_browser_stylesheet,
                      build_markdown_html_css)


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
        layout.addWidget(self.browser)
        self.setWidget(container)

        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable |
            QDockWidget.DockWidgetFeature.DockWidgetMovable |
            QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )

        self.apply_styles(get_theme())
        theme_signals.theme_changed.connect(self._on_theme_changed)

    # ── Theme handling ────────────────────────────────────────────────────

    def _on_theme_changed(self, t: dict):
        self.apply_styles(t)
        # Re-render so the injected HTML CSS reflects the new palette
        if self._pending_text:
            self._do_render()

    def apply_styles(self, t: dict):
        self.browser.setStyleSheet(build_markdown_browser_stylesheet(t))

    # ── Public API ────────────────────────────────────────────────────────

    def update_preview(self, markdown_text: str):
        self._pending_text = markdown_text
        self._debounce.start()

    # ── Rendering ─────────────────────────────────────────────────────────

    def _do_render(self):
        t = get_theme()

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

        html = f"""<!DOCTYPE html>
<html>
<head>
<style>
{build_markdown_html_css(t)}
</style>
</head>
<body>
{html_body}
</body>
</html>"""

        scrollbar = self.browser.verticalScrollBar()
        scroll_pos = scrollbar.value()
        was_at_bottom = scroll_pos == scrollbar.maximum()

        self.browser.setHtml(html)

        if was_at_bottom:
            scrollbar.setValue(scrollbar.maximum())
        else:
            scrollbar.setValue(scroll_pos)

    def _basic_render(self, text: str) -> str:
        """Minimal fallback renderer used when the markdown package is absent."""
        escaped = (text.replace("&", "&amp;")
                       .replace("<", "&lt;")
                       .replace(">", "&gt;"))
        html = []
        for line in escaped.split('\n'):
            if line.startswith('### '):
                html.append(f'<h3>{line[4:]}</h3>')
            elif line.startswith('## '):
                html.append(f'<h2>{line[3:]}</h2>')
            elif line.startswith('# '):
                html.append(f'<h1>{line[2:]}</h1>')
            elif line.strip() == '':
                html.append('<br>')
            else:
                html.append(f'<p>{line}</p>')
        return '\n'.join(html)

    # ── Cleanup ───────────────────────────────────────────────────────────

    def closeEvent(self, event):
        try:
            theme_signals.theme_changed.disconnect(self._on_theme_changed)
        except RuntimeError:
            pass
        super().closeEvent(event)