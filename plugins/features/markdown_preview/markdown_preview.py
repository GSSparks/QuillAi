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

        # Scroll sync state
        self._pending_scroll_ratio = None   # applied when range becomes non-zero
        self._sync_ratio           = None   # set by cursor movement, wins over restore

    # ── Theme handling ────────────────────────────────────────────────────

    def _on_theme_changed(self, t: dict):
        self.apply_styles(t)
        if self._pending_text:
            self._do_render()

    def apply_styles(self, t: dict):
        self.browser.setStyleSheet(build_markdown_browser_stylesheet(t))

    # ── Public API ────────────────────────────────────────────────────────

    def update_preview(self, markdown_text: str):
        self._pending_text = markdown_text
        self._debounce.start()

    def sync_scroll(self, cursor_line: int, total_lines: int):
        """
        Scroll the preview to match the editor cursor position.
        cursor_line and total_lines are 0-indexed block counts.
        """
        if total_lines <= 1:
            return
        ratio = cursor_line / max(1, total_lines - 1)
        self._sync_ratio = ratio
        scrollbar = self.browser.verticalScrollBar()
        if scrollbar.maximum() > 0:
            # Content already rendered — apply immediately
            scrollbar.setValue(int(ratio * scrollbar.maximum()))
        else:
            # Content not laid out yet — wait for rangeChanged
            self._pending_scroll_ratio = ratio
            try:
                scrollbar.rangeChanged.disconnect(self._on_range_ready)
            except (RuntimeError, TypeError):
                pass
            scrollbar.rangeChanged.connect(self._on_range_ready)

    def _on_range_ready(self, min_val: int, max_val: int):
        """Called when QTextBrowser finishes layout and scrollbar max is known."""
        print(f"[range_ready] min={min_val} max={max_val} pending={self._pending_scroll_ratio}")
        if max_val <= 0:
            return
        scrollbar = self.browser.verticalScrollBar()
        try:
            scrollbar.rangeChanged.disconnect(self._on_range_ready)
        except (RuntimeError, TypeError):
            pass
        if self._pending_scroll_ratio is not None:
            scrollbar.setValue(int(self._pending_scroll_ratio * max_val))
            self._pending_scroll_ratio = None

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

        print(f"[do_render] after setHtml, max={self.browser.verticalScrollBar().maximum()}")        
        # Capture scroll state before replacing content
        scrollbar     = self.browser.verticalScrollBar()
        old_max       = scrollbar.maximum()
        old_ratio     = (scrollbar.value() / old_max) if old_max > 0 else 0.0
        was_at_bottom = old_ratio > 0.99

        self.browser.setHtml(html)

        # Cursor sync takes priority over position restore
        if self._sync_ratio is not None:
            restore = self._sync_ratio
        elif was_at_bottom:
            restore = 1.0
        else:
            restore = old_ratio

        # Apply after layout completes via rangeChanged
        self._pending_scroll_ratio = restore
        try:
            scrollbar.rangeChanged.disconnect(self._on_range_ready)
        except (RuntimeError, TypeError):
            pass
        scrollbar.rangeChanged.connect(self._on_range_ready)

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