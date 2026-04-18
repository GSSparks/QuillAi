"""
editor/session_mixin.py

SessionMixin — window state, session save/restore, crash recovery.
Mixed into CodeEditor.
"""

import os
from PyQt6.QtCore import QTimer, QByteArray

from ui.session_manager import save_session, load_session


class SessionMixin:

    def _restore_window_state(self):
        geometry = self.settings_manager.get("window_geometry")
        if geometry:
            try:
                self.restoreGeometry(QByteArray.fromHex(geometry.encode()))
            except Exception:
                pass
        dock_state = self.settings_manager.get("dock_state")
        if dock_state:
            try:
                self.restoreState(QByteArray.fromHex(dock_state.encode()))
            except Exception:
                pass
        if hasattr(self, "md_preview_dock") and self.md_preview_dock is not None:
            if self.settings_manager.get("md_preview_visible"):
                self.md_preview_dock.show()
            else:
                self.md_preview_dock.hide()
        if hasattr(self, "chat_panel"):
            self.chat_panel.raise_()
        plugin_dock_state = self.settings_manager.get("plugin_dock_state") or {}
        def _restore_plugin_docks():
            for dock_attr, visible in plugin_dock_state.items():
                dock = getattr(self, dock_attr, None)
                if dock is not None:
                    if visible:
                        dock.show()
                        dock.raise_()
                    else:
                        dock.hide()
        QTimer.singleShot(100, _restore_plugin_docks)

    def _save_current_session(self):
        tabs_data = []
        for pane in self.split_container.all_panes():
            for i in range(pane.count()):
                editor = pane.widget(i)
                fp = getattr(editor, "file_path", None)
                if fp:
                    tabs_data.append((fp, editor.textCursor().position()))
        project_path = (
            self.git_dock.repo_path
            if hasattr(self, "git_dock") and self.git_dock.repo_path
            else None
        )
        save_session(tabs_data, self.tabs.currentIndex(), project_path)

    def _restore_session(self, project_path=None):
        self._startup.register("LSP")
        self._startup.register("Repo Map")
        if project_path is None and hasattr(self, "git_dock") and self.git_dock.repo_path:
            project_path = self.git_dock.repo_path

        session = load_session(project_path)
        if not session or not session.get("tabs"):
            self.add_new_tab("Untitled", "")
            return

        saved_project = session.get("project_path") or project_path
        if saved_project and os.path.isdir(saved_project):
            if hasattr(self, "tree_view") and hasattr(self, "file_model"):
                self.file_model.setRootPath(saved_project)
                self.tree_view.setRootIndex(self.file_model.index(saved_project))
            if hasattr(self, "git_dock"):
                self.git_dock.repo_path = saved_project
                self.git_dock.refresh_status()
            if hasattr(self, "memory_manager"):
                self.memory_manager.set_project(saved_project)
            if hasattr(self, "faq_manager"):
                self.faq_manager.set_project(saved_project)
            if hasattr(self, "project_settings"):
                self.project_settings.set_project(saved_project)
            self._start_lsp(project_root=saved_project)
            self._init_repo_map(project_root=saved_project)
            self._init_wiki(project_root=saved_project)
            if hasattr(self, "update_git_branch"):
                self.update_git_branch()
            self._update_window_title(saved_project)
            self.plugin_manager.emit("project_opened", project_root=saved_project)

        restored = 0
        for tab_data in session.get("tabs", []):
            path       = tab_data.get("path")
            cursor_pos = tab_data.get("cursor", 0)
            if not path or not os.path.exists(path):
                continue
            try:
                content = open(path, "r", encoding="utf-8").read()
                editor  = self.add_new_tab(os.path.basename(path), content, path)
                cursor  = editor.textCursor()
                cursor.setPosition(min(cursor_pos, len(content)))
                editor.setTextCursor(cursor)
                editor.ensureCursorVisible()
                restored += 1
            except Exception as e:
                print(f"Could not restore tab {path}: {e}")

        active = session.get("active_tab", 0)
        if restored > 0 and active < self.tabs.count():
            self.tabs.setCurrentIndex(active)
        elif restored == 0:
            self.add_new_tab("Untitled", "")

        self.update_status_bar()
        self.update_git_branch()
        self.autosave_manager.restore(self._open_recovered_tab)
