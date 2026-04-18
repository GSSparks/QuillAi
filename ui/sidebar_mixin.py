"""
ui/sidebar_mixin.py

SidebarMixin — file explorer tree, context menu, git panel setup.
Mixed into CodeEditor.
"""

import os
import shutil
from pathlib import Path

from PyQt6.QtWidgets import (QDockWidget, QTreeView, QMenu, QInputDialog,
                              QMessageBox, QApplication)
from PyQt6.QtCore import Qt, QDir, QUrl
from PyQt6.QtGui import QDesktopServices

from ui.file_system_model import CustomFileSystemModel
from ui.theme import get_theme, build_dock_stylesheet, build_tree_view_stylesheet
from ui.git_panel import GitDockWidget


class SidebarMixin:

    def setup_sidebar(self):
        self.file_model = CustomFileSystemModel()
        self.file_model.setRootPath(QDir.currentPath())
        self.file_model.setFilter(
            QDir.Filter.AllEntries | QDir.Filter.Hidden | QDir.Filter.NoDotAndDotDot
        )
        self.tree_view = QTreeView()
        self.tree_view.setModel(self.file_model)
        self.tree_view.setRootIndex(self.file_model.index(QDir.currentPath()))
        self.tree_view.setHeaderHidden(True)
        for i in range(1, 4):
            self.tree_view.hideColumn(i)
        self.tree_view.setIndentation(15)
        self.tree_view.setStyleSheet(build_tree_view_stylesheet(get_theme()))
        self.tree_view.doubleClicked.connect(self.open_tree_item)
        self.tree_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree_view.customContextMenuRequested.connect(self._on_tree_context_menu)

        self.sidebar_dock = QDockWidget("Explorer", self)
        self.sidebar_dock.setStyleSheet(build_dock_stylesheet(get_theme()))
        self.sidebar_dock.setWidget(self.tree_view)
        self.sidebar_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable |
            QDockWidget.DockWidgetFeature.DockWidgetMovable
        )
        self.sidebar_dock.setObjectName("sidebar_dock")
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.sidebar_dock)

    def setup_git_panel(self):
        self.git_dock = GitDockWidget(self)
        self.git_dock.file_double_clicked.connect(self.open_file_in_tab)
        self.git_dock.setObjectName("git_dock")
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.git_dock)
        self.tabifyDockWidget(self.sidebar_dock, self.git_dock)

    def open_tree_item(self, index):
        file_path = self.file_model.filePath(index)
        if not self.file_model.isDir(index):
            self.open_file_in_tab(file_path)

    def _on_tree_context_menu(self, pos):
        index     = self.tree_view.indexAt(pos)
        has_sel   = index.isValid()
        sel_path  = Path(self.file_model.filePath(index)) if has_sel else None
        root_path = Path(self.file_model.filePath(self.tree_view.rootIndex()))
        parent_path = (
            sel_path.parent if sel_path and sel_path.is_file()
            else sel_path or root_path
        )

        t    = get_theme()
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background: {t["bg1"]}; color: {t["fg1"]};
                border: 1px solid {t["bg3"]}; padding: 4px 0; font-size: 9pt;
            }}
            QMenu::item {{ padding: 4px 20px 4px 12px; }}
            QMenu::item:selected {{ background: {t["bg3"]}; color: {t["yellow"]}; }}
            QMenu::separator {{ height: 1px; background: {t["bg3"]}; margin: 3px 6px; }}
        """)

        act_new_file   = menu.addAction("\U0001f4c4  New File")
        act_new_folder = menu.addAction("\U0001f4c1  New Folder")
        menu.addSeparator()
        act_rename     = menu.addAction("\u270e   Rename")
        act_delete     = menu.addAction("\U0001f5d1  Delete")
        if not has_sel:
            act_rename.setEnabled(False)
            act_delete.setEnabled(False)
        menu.addSeparator()
        act_copy_path = menu.addAction("\u2398   Copy Path")
        act_copy_rel  = menu.addAction("\u2398   Copy Relative Path")
        act_reveal    = menu.addAction("\U0001f50d  Reveal in File Manager")
        if not has_sel:
            act_copy_path.setEnabled(False)
            act_copy_rel.setEnabled(False)
            act_reveal.setEnabled(False)

        act_terminal = None
        if hasattr(self, "terminal_dock"):
            menu.addSeparator()
            act_terminal = menu.addAction("\u2328   Open in Terminal")

        action = menu.exec(self.tree_view.viewport().mapToGlobal(pos))
        if not action:
            return

        if action == act_new_file:
            name, ok = QInputDialog.getText(self, "New File", "File name:", text="untitled.txt")
            if ok and name.strip():
                new_path = parent_path / name.strip()
                try:
                    new_path.parent.mkdir(parents=True, exist_ok=True)
                    new_path.touch()
                    self.open_file_in_tab(str(new_path))
                except Exception as e:
                    QMessageBox.warning(self, "Error", f"Could not create file:\n{e}")

        elif action == act_new_folder:
            name, ok = QInputDialog.getText(self, "New Folder", "Folder name:")
            if ok and name.strip():
                try:
                    (parent_path / name.strip()).mkdir(parents=True, exist_ok=True)
                except Exception as e:
                    QMessageBox.warning(self, "Error", f"Could not create folder:\n{e}")

        elif action == act_rename and sel_path:
            name, ok = QInputDialog.getText(self, "Rename",
                                            f'Rename "{sel_path.name}" to:',
                                            text=sel_path.name)
            if ok and name.strip() and name.strip() != sel_path.name:
                new_path = sel_path.parent / name.strip()
                try:
                    sel_path.rename(new_path)
                    self._reload_file_in_editors(str(new_path))
                except Exception as e:
                    QMessageBox.warning(self, "Error", f"Could not rename:\n{e}")

        elif action == act_delete and sel_path:
            kind  = "folder" if sel_path.is_dir() else "file"
            reply = QMessageBox.question(
                self, f"Delete {kind}",
                f'Permanently delete "{sel_path.name}"?\n\n{sel_path}',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                try:
                    shutil.rmtree(sel_path) if sel_path.is_dir() else sel_path.unlink()
                except Exception as e:
                    QMessageBox.warning(self, "Error", f"Could not delete:\n{e}")

        elif action == act_copy_path and sel_path:
            QApplication.clipboard().setText(str(sel_path))
            self.statusBar().showMessage("Path copied", 2000)

        elif action == act_copy_rel and sel_path:
            try:
                rel = sel_path.relative_to(root_path)
            except ValueError:
                rel = sel_path
            QApplication.clipboard().setText(str(rel))
            self.statusBar().showMessage("Relative path copied", 2000)

        elif action == act_reveal and sel_path:
            target = sel_path if sel_path.is_dir() else sel_path.parent
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))

        elif act_terminal and action == act_terminal:
            target = sel_path if sel_path and sel_path.is_dir() else parent_path
            if hasattr(self.terminal_dock, "set_working_dir"):
                self.terminal_dock.set_working_dir(str(target))
            elif hasattr(self.terminal_dock, "run_command"):
                self.terminal_dock.run_command(f"cd {str(target)!r}")
