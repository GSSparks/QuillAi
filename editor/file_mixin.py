"""
editor/file_mixin.py

FileMixin — open, save, external file watching, reload, apply editor mode.
Mixed into CodeEditor.
"""

import os
from pathlib import Path

from PyQt6.QtWidgets import QFileDialog, QMessageBox, QWidget, QHBoxLayout, QLabel, QPushButton
from PyQt6.QtCore import Qt, QTimer, QDir
from PyQt6.QtGui import QTextCursor
from PyQt6.QtGui import QTextOption

from editor.highlighter import registry
from ui.theme import get_theme


class FileMixin:

    def open_file_in_tab(self, file_path, line_number=None):
        if os.path.isdir(file_path):
            return

        editor_to_focus = None
        for pane in self.split_container.all_panes():
            for i in range(pane.count()):
                editor = pane.widget(i)
                if getattr(editor, "file_path", None) == file_path:
                    self.split_container._set_active(pane)
                    self.tabs = pane
                    pane.setCurrentIndex(i)
                    editor_to_focus = editor
                    break
            if editor_to_focus:
                break

        if not editor_to_focus:
            try:
                content  = Path(file_path).read_text(encoding="utf-8")
                filename = os.path.basename(file_path)
                editor_to_focus = self.add_new_tab(filename, content, file_path)
                self._apply_editor_mode(editor_to_focus,
                                        os.path.splitext(file_path)[1].lower())
            except Exception as e:
                print(f"Could not open file: {e}")
                return

        if editor_to_focus:
            fp = getattr(editor_to_focus, "file_path", None)
            if fp and os.path.exists(fp) and fp not in self._file_watcher.files():
                self._file_watcher.addPath(fp)

        if editor_to_focus and hasattr(self, "wiki_indexer") and self.wiki_indexer:
            _fp = getattr(editor_to_focus, "file_path", None)
            if _fp:
                self.wiki_indexer.prioritize(Path(_fp))

        if editor_to_focus and line_number is not None:
            cursor = editor_to_focus.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            cursor.movePosition(QTextCursor.MoveOperation.NextBlock,
                                n=line_number - 1)
            editor_to_focus.setTextCursor(cursor)
            editor_to_focus.ensureCursorVisible()
            editor_to_focus.setFocus()
            editor_to_focus.highlight_current_line()

    def _apply_editor_mode(self, editor, ext: str):
        is_md = ext in (".md", ".markdown")
        editor.setWordWrapMode(
            QTextOption.WrapMode.WordWrap if is_md
            else QTextOption.WrapMode.NoWrap
        )
        if hasattr(self, "intent_tracker") and editor.file_path:
            self.intent_tracker.record_file_edit(editor.file_path)
        self._refresh_markdown_preview(editor)

    def save_file(self, index=None):
        if index is None or isinstance(index, bool):
            index = self.tabs.currentIndex()

        editor = self.tabs.widget(index)
        if not editor:
            return False

        if not editor.file_path:
            start_dir    = QDir.currentPath()
            if hasattr(self, "git_dock") and self.git_dock.repo_path:
                start_dir = self.git_dock.repo_path
            detected_ext = getattr(editor, "_detected_ext", "")
            all_filters  = {
                ".py": "Python Files (*.py)", ".js": "JavaScript Files (*.js)",
                ".ts": "TypeScript Files (*.ts)", ".tsx": "TypeScript JSX Files (*.tsx)",
                ".html": "HTML Files (*.html)", ".yml": "YAML Files (*.yml)",
                ".yaml": "YAML Files (*.yaml)", ".sh": "Shell Scripts (*.sh)",
                ".nix": "Nix Files (*.nix)", ".md": "Markdown Files (*.md)",
                ".json": "JSON Files (*.json)", ".txt": "Text Files (*.txt)",
            }
            if detected_ext and detected_ext in all_filters:
                first      = all_filters[detected_ext]
                rest       = [v for k, v in all_filters.items() if k != detected_ext]
                filter_str = ";;".join([first] + rest + ["All Files (*)"])
                default    = os.path.join(start_dir, f"untitled{detected_ext}")
            else:
                filter_str = ";;".join(list(all_filters.values()) + ["All Files (*)"])
                default    = start_dir

            path, _ = QFileDialog.getSaveFileName(self, "Save File", default, filter_str)
            if path:
                editor.file_path = path
                self.tabs.setTabText(index, os.path.basename(path))
                ext = os.path.splitext(path)[1].lower()
                editor.highlighter  = registry.get_highlighter(editor.document(), ext)
                editor._detected_ext = ""
                self._lang_detect_timer.stop()
                self._lang_detect_running = False
                self._apply_editor_mode(editor, ext)
            else:
                return False

        try:
            code = editor.toPlainText()
            if editor.file_path in self._file_watcher.files():
                self._file_watcher.removePath(editor.file_path)
            if self.settings_manager.get_trim_trailing_whitespace():
                code = "\n".join(l.rstrip() for l in code.splitlines())
                if code and not code.endswith("\n"):
                    code += "\n"
            Path(editor.file_path).write_text(code, encoding="utf-8")
            editor.set_original_state(code)
            editor._detected_ext = ""
            if self.repo_map and editor.file_path:
                self.repo_map.invalidate(editor.file_path)
            current_text = self.tabs.tabText(index)
            if current_text.endswith("*"):
                self.tabs.setTabText(index, current_text[:-1])
            ext = os.path.splitext(editor.file_path)[1].lower()
            editor.highlighter = registry.get_highlighter(editor.document(), ext)
            self._apply_editor_mode(editor, ext)
            if hasattr(self, "git_dock"):
                self.git_dock.refresh_status()
            if editor.file_path:
                self.plugin_manager.emit("file_saved", path=editor.file_path)
            self.statusBar().showMessage(f"Saved: {editor.file_path}", 3000)
            self.autosave_manager.clear(editor.file_path)
            if editor.file_path not in self._file_watcher.files():
                self._file_watcher.addPath(editor.file_path)
            return True
        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"Could not save file: {e}")
            return False

    def _on_file_changed_externally(self, path: str):
        if path in self._watch_debounce:
            self._watch_debounce[path].stop()
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: self._handle_file_changed(path))
        timer.start(300)
        self._watch_debounce[path] = timer

    def _handle_file_changed(self, path: str):
        self._watch_debounce.pop(path, None)
        if not os.path.exists(path):
            return
        try:
            new_content = Path(path).read_text(encoding="utf-8")
        except Exception:
            return
        for pane in self.split_container.all_panes():
            for i in range(pane.count()):
                editor = pane.widget(i)
                if getattr(editor, "file_path", None) == path:
                    if editor.toPlainText() == new_content:
                        continue
                    name = os.path.basename(path)
                    self._show_external_change_bar(editor, path, new_content, name)

        if path not in self._file_watcher.files():
            self._file_watcher.addPath(path)

    def _reload_editor(self, editor, new_content: str, path: str):
        cursor = editor.textCursor()
        pos    = cursor.position()
        editor.blockSignals(True)
        editor.setPlainText(new_content)
        editor.set_original_state(new_content)
        editor.blockSignals(False)
        cursor = editor.textCursor()
        cursor.setPosition(min(pos, len(new_content)))
        editor.setTextCursor(cursor)
        editor.highlight_current_line()

    def _reload_file_in_editors(self, abs_path: str):
        try:
            new_content = Path(abs_path).read_text(encoding="utf-8")
        except Exception:
            return
        for pane in self.split_container.all_panes():
            for i in range(pane.count()):
                editor = pane.widget(i)
                if getattr(editor, "file_path", None) == abs_path:
                    self._reload_editor(editor, new_content, abs_path)

    def _show_external_change_bar(self, editor, path: str, new_content: str, name: str):
        from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton
        t   = get_theme()
        bar = QWidget(editor.parent())
        bar.setFixedHeight(32)
        bl  = QHBoxLayout(bar)
        bl.setContentsMargins(8, 0, 8, 0)
        lbl = QLabel(f"⚠ {name} changed on disk")
        lbl.setStyleSheet(f"color: {t.get('yellow', '#d79921')};")
        bl.addWidget(lbl, stretch=1)
        reload_btn  = QPushButton("Reload")
        dismiss_btn = QPushButton("Dismiss")
        for btn in (reload_btn, dismiss_btn):
            btn.setFixedHeight(22)
            bl.addWidget(btn)
        bar.show()

        def _do_reload():
            self._reload_editor(editor, new_content, path)
            bar.deleteLater()

        reload_btn.clicked.connect(_do_reload)
        dismiss_btn.clicked.connect(bar.deleteLater)

        parent_layout = editor.parent().layout() if editor.parent() else None
        if parent_layout:
            parent_layout.insertWidget(0, bar)
