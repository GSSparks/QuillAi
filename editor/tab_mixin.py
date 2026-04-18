"""
editor/tab_mixin.py

TabMixin — tab lifecycle, pane management, editor creation.
Mixed into CodeEditor.
"""

import os
from PyQt6.QtWidgets import QMessageBox
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QTextCursor

from editor.ghost_editor import GhostEditor
from ui.theme import (get_theme, build_tab_widget_stylesheet,
                      build_editor_stylesheet)
from editor.highlighter import registry
from ui.split_container import EditorPane


class TabMixin:

    def current_editor(self):
        editor = self.tabs.currentWidget()
        if editor and hasattr(editor, "toPlainText"):
            return editor
        return None

    def get_open_editors(self):
        editors = []
        for pane in self.split_container.all_panes():
            for i in range(pane.count()):
                e = pane.widget(i)
                if hasattr(e, "file_path") and e.file_path:
                    editors.append(e)
        return editors

    def _get_all_editors_indexed(self):
        result = []
        for pane in self.split_container.all_panes():
            for i in range(pane.count()):
                e = pane.widget(i)
                if hasattr(e, "file_path"):
                    result.append((e.file_path or f"untitled_{i}", e))
        return result

    def add_new_tab(self, name="Untitled", content="", path=None):
        t      = get_theme()
        editor = GhostEditor(settings_manager=self.settings_manager)
        if getattr(self, "lsp_manager", None):
            self._wire_editor_lsp(editor)
        editor.setStyleSheet(build_editor_stylesheet(t))
        editor.setFont(editor.font())
        editor.viewport().setFont(editor.font())

        if path:
            ext = os.path.splitext(path)[1].lower()
            editor.highlighter = registry.get_highlighter(editor.document(), ext)
        editor.setPlainText(content)
        editor.set_original_state(content)
        editor.file_path = path

        # Wire editor signals
        editor.textChanged.connect(self.on_text_changed)
        if hasattr(editor, "save_requested"):
            editor.save_requested.connect(
                lambda: self.save_file(self.tabs.indexOf(editor))
            )
        if hasattr(editor, "goto_definition_requested"):
            editor.goto_definition_requested.connect(self._goto_file)
        if hasattr(editor, "lsp_rename_requested"):
            editor.lsp_rename_requested.connect(
                lambda fp, ln, ch, new: self._handle_lsp_rename(fp, ln, ch, new)
            )

        pane = self.split_container.active_pane()
        idx  = pane.addTab(editor, name)
        pane.setCurrentIndex(idx)
        self.tabs = pane

        if path and os.path.exists(path):
            if path not in self._file_watcher.files():
                self._file_watcher.addPath(path)

        editor.setFocus()
        return editor

    def _open_recovered_tab(self, name: str, content: str, path: str = None):
        editor = self.add_new_tab(name, content, path)
        pane   = self.split_container.active_pane()
        idx    = pane.indexOf(editor)
        pane.setTabText(idx, f"↩ {name}")
        return editor

    def close_tab(self, index):
        editor = self.tabs.widget(index)
        if editor and hasattr(editor, "is_dirty") and editor.is_dirty():
            reply = QMessageBox.question(
                self, "Unsaved Changes",
                f"Save changes to {self.tabs.tabText(index).rstrip('*')}?",
                QMessageBox.StandardButton.Save    |
                QMessageBox.StandardButton.Discard |
                QMessageBox.StandardButton.Cancel,
            )
            if reply == QMessageBox.StandardButton.Save:
                if not self.save_file(index):
                    return
            elif reply == QMessageBox.StandardButton.Cancel:
                return

        fp = getattr(editor, "file_path", None)
        if fp and fp in self._file_watcher.files():
            self._file_watcher.removePath(fp)

        self.autosave_manager.clear(fp or "")
        self.tabs.removeTab(index)

        if self.tabs.count() == 0:
            self.add_new_tab()

    def _on_active_pane_changed(self, pane: EditorPane):
        self.tabs = pane
        self.update_status_bar()

    def _on_pane_tab_close(self, pane: EditorPane, index: int):
        prev_tabs = self.tabs
        self.tabs = pane
        self.close_tab(index)
        self.tabs = prev_tabs if prev_tabs.count() > 0 else self.split_container.active_pane()

    def _on_pane_current_changed(self, pane: EditorPane, index: int):
        self.update_status_bar()

    def _split_active(self, orientation):
        self.split_container.split_active(orientation)
        for pane in self.split_container.all_panes():
            pane.setStyleSheet(build_tab_widget_stylesheet(get_theme()))
        # Activate the new empty pane and add a tab
        for pane in self.split_container.all_panes():
            if pane.count() == 0:
                self.split_container._set_active(pane)
                self.tabs = pane
                self.add_new_tab("Untitled", "")
                break

    def _close_active_pane(self):
        self.split_container.close_active_pane()
        self.tabs = self.split_container.active_pane()

    def _focus_adjacent_pane(self, direction: int):
        panes = self.split_container.all_panes()
        if len(panes) < 2:
            return
        current = self.split_container.active_pane()
        try:
            idx = panes.index(current)
        except ValueError:
            return
        target = panes[(idx + direction) % len(panes)]
        self.split_container._set_active(target)
        self.tabs = target
        editor = target.currentWidget()
        if editor:
            editor.setFocus()

    def _on_tab_changed(self, index):
        self.update_status_bar()

    def _close_all_tabs_for_switch(self):
        while self.tabs.count() > 0:
            self.tabs.removeTab(0)

    def request_manual_completion(self):
        editor = self.current_editor()
        if editor and editor.hasFocus():
            if hasattr(editor, "request_completion_hotkey"):
                editor.request_completion_hotkey()

    def on_text_changed(self):
        from editor.highlighter import registry
        editor = self.current_editor()
        if not editor or getattr(self, "_is_loading", False):
            return
        if editor.function_active or not editor.hasFocus():
            return
        if not editor.file_path:
            text = editor.toPlainText()
            if len(text) > 20:
                ext         = self.detect_language_from_content(text)
                current_ext = getattr(editor, "_detected_ext", "")
                if ext and ext != current_ext:
                    editor._detected_ext = ext
                    editor.highlighter   = registry.get_highlighter(editor.document(), ext)
                    self.update_status_bar()
                    self.statusBar().showMessage(
                        f"Language detected: {ext.lstrip('.')}", 3000
                    )
                    self._lang_detect_timer.stop()
                elif not ext and not current_ext:
                    self._lang_detect_timer.start(2000)
        if hasattr(editor, "is_dirty"):
            index         = self.tabs.indexOf(editor)
            current_title = self.tabs.tabText(index)
            if editor.is_dirty() and not current_title.endswith("*"):
                self.tabs.setTabText(index, current_title + "*")
            elif not editor.is_dirty() and current_title.endswith("*"):
                self.tabs.setTabText(index, current_title[:-1])
        editor.clear_ghost_text()
        if self.last_worker:
            self.last_worker.cancel()
