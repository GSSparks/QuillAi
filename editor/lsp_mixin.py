"""
editor/lsp_mixin.py

LspMixin — LSP server startup, wiring editors, goto definition.
Mixed into CodeEditor.
"""

import os
from ai.lsp_manager import LSPManager
from ai.lsp_context import LSPContextProvider


class LspMixin:

    def _start_lsp(self, project_root: str = None):
        root = (
            project_root
            or (self.git_dock.repo_path
                if hasattr(self, "git_dock") and self.git_dock.repo_path
                else None)
            or os.getcwd()
        )
        if self.lsp_manager:
            self.lsp_manager.restart(root)
        else:
            self.lsp_manager = LSPManager(root, parent=self)
            self.lsp_manager.server_ready.connect(self._on_lsp_ready)
            self.lsp_manager.server_error.connect(
                lambda name, msg: self.statusBar().showMessage(
                    f"LSP [{name}]: {msg}", 5000
                )
            )
            self.lsp_manager.start()
            self.lsp_context_provider = LSPContextProvider(self.lsp_manager)

    def _on_lsp_ready(self, server_name: str):
        self._startup.complete("LSP")
        self.statusBar().showMessage(f"LSP ready: {server_name}", 2000)
        for pane in self.split_container.all_panes():
            for i in range(pane.count()):
                editor = pane.widget(i)
                if hasattr(editor, "file_path") and editor.file_path:
                    self._wire_editor_lsp(editor)

    def _wire_editor_lsp(self, editor):
        if not self.lsp_manager or not hasattr(editor, "set_lsp_manager"):
            return
        fp = getattr(editor, "file_path", None)
        if fp and self.lsp_manager.is_supported(fp):
            editor.set_lsp_manager(self.lsp_manager, fp)

    def _goto_file(self, file_path: str, line: int, col: int):
        self.open_file_in_tab(file_path, line_number=line + 1)
