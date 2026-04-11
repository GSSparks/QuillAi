from PyQt6.QtCore import Qt
from core.plugin_base import FeaturePlugin
from plugins.features.markdown_preview.markdown_preview import MarkdownPreviewDock


class MarkdownPreviewPlugin(FeaturePlugin):
    name = "markdown_preview"
    description = "Live markdown preview panel"
    enabled = True

    @classmethod
    def should_show(cls, project_root: str) -> bool:
        """Show only when the project contains markdown files."""
        import os
        for dirpath, dirnames, filenames in os.walk(project_root):
            dirnames[:] = [d for d in dirnames
                           if not d.startswith('.')
                           and d not in ('node_modules', '__pycache__',
                                         'venv', '.venv')]
            for f in filenames:
                if f.lower().endswith(('.md', '.markdown')):
                    return True
        return False

    def activate(self):
        self.dock = MarkdownPreviewDock(self.app)
        self.app.md_preview_dock = self.dock
        self.app.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.dock)
        self.dock.hide()

        self.app.plugin_manager.register_dock("Markdown Preview", "md_preview_dock")

        self.on("file_opened", self._on_file_opened)
        self.on("editor_scrolled", self._on_editor_scrolled)
        self.on("markdown_changed", self._on_markdown_changed)

    def _on_file_opened(self, path: str = None, editor=None, **kwargs):
        if not path or not path.lower().endswith(('.md', '.markdown')):
            return
        if editor is None:
            editor = self.app.current_editor()
        if editor:
            self.dock.show()
            self.dock.raise_()
            self.dock.update_preview(editor.toPlainText())

    def _on_markdown_changed(self, text: str = None, **kwargs):
        if text is not None:
            self.dock.update_preview(text)

    def _on_editor_scrolled(self, first_visible: int = 0,
                             total_lines: int = 1, **kwargs):
        self.dock.sync_scroll(first_visible, total_lines)

    def deactivate(self):
        self.dock.close()
        self.app.md_preview_dock = None