import os
from PyQt6.QtWidgets import QFileDialog, QMessageBox, QMenu
from PyQt6.QtGui import QAction, QKeySequence
from editor.highlighter import registry

from ui.theme import get_theme, build_menu_stylesheet, build_file_dialog_stylesheet


def _new_project(window):
    from ui.new_project_dialog import NewProjectDialog
    dialog = NewProjectDialog(window)
    if dialog.exec() and dialog.result_path:
        folder_path = dialog.result_path
        open_file   = dialog.result_open_file

        if hasattr(window, '_save_current_session'):
            window._save_current_session()

        window._close_all_tabs_for_switch()

        if hasattr(window, 'tree_view') and hasattr(window, 'file_model'):
            window.file_model.setRootPath(folder_path)
            window.tree_view.setRootIndex(window.file_model.index(folder_path))

        if hasattr(window, 'git_dock'):
            window.git_dock.repo_path = folder_path
            window.git_dock.refresh_status()

        if hasattr(window, 'memory_manager'):
            window.memory_manager.set_project(folder_path)
        if hasattr(window, 'memory_panel'):
            window.memory_panel.refresh()

        if hasattr(window, 'update_git_branch'):
            window.update_git_branch()
        if hasattr(window, 'update_status_bar'):
            window.update_status_bar()
        if hasattr(window, 'load_project_chat'):
            window.load_project_chat()

        if open_file and os.path.exists(open_file):
            window.open_file_in_tab(open_file)
        else:
            window.add_new_tab("Untitled", "")

        window.statusBar().showMessage(
            f"Project '{os.path.basename(folder_path)}' created.", 4000
        )


def _open_recent_project(folder_path, window):
    if not os.path.isdir(folder_path):
        QMessageBox.warning(window, "Project Not Found",
                            f"The folder no longer exists:\n{folder_path}")
        return

    if hasattr(window, '_save_current_session'):
        window._save_current_session()

    window._close_all_tabs_for_switch()

    if hasattr(window, 'tree_view') and hasattr(window, 'file_model'):
        window.file_model.setRootPath(folder_path)
        window.tree_view.setRootIndex(window.file_model.index(folder_path))

    if hasattr(window, 'git_dock'):
        window.git_dock.repo_path = folder_path
        window.git_dock.refresh_status()

    if hasattr(window, 'memory_manager'):
        window.memory_manager.set_project(folder_path)
    if hasattr(window, 'memory_panel'):
        window.memory_panel.refresh()

    if hasattr(window, 'memory_manager'):
        window.memory_manager.set_project(folder_path)
    if hasattr(window, 'load_project_chat'):
        window.load_project_chat()

    if hasattr(window, 'update_git_branch'):
        window.update_git_branch()
    if hasattr(window, 'update_status_bar'):
        window.update_status_bar()

    if hasattr(window, '_restore_session'):
        window._restore_session(project_path=folder_path)


def _populate_recent_projects(menu, window):
    from ui.session_manager import list_project_sessions
    menu.clear()
    menu.setStyleSheet(build_menu_stylesheet(get_theme()))

    sessions = list_project_sessions()

    if not sessions:
        empty_action = QAction("No recent projects", window)
        empty_action.setEnabled(False)
        menu.addAction(empty_action)
        return

    sessions.sort(key=lambda s: os.path.getmtime(s["file"]), reverse=True)

    for session in sessions[:10]:
        project_path = session["project_path"]
        tab_count    = session["tab_count"]
        name         = os.path.basename(project_path.rstrip('/'))
        label        = f"{name}  ({tab_count} tab{'s' if tab_count != 1 else ''})"

        action = QAction(label, window)
        action.setToolTip(project_path)
        action.setStatusTip(project_path)

        def make_handler(path):
            def handler():
                _open_recent_project(path, window)
            return handler

        action.triggered.connect(make_handler(project_path))
        menu.addAction(action)

    menu.addSeparator()
    clear_action = QAction("Clear Recent Projects", window)
    clear_action.triggered.connect(lambda: _clear_recent_projects(menu, window))
    menu.addAction(clear_action)


def _clear_recent_projects(menu, window):
    from ui.session_manager import list_project_sessions
    reply = QMessageBox.question(
        window, "Clear Recent Projects",
        "Remove all recent project history?",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
    )
    if reply == QMessageBox.StandardButton.Yes:
        sessions = list_project_sessions()
        for s in sessions:
            try:
                os.remove(s["file"])
            except Exception:
                pass
        menu.clear()
        menu.setStyleSheet(build_menu_stylesheet(get_theme()))
        empty = QAction("No recent projects", window)
        empty.setEnabled(False)
        menu.addAction(empty)


def setup_file_menu(window):
    menu = window.menuBar()
    file_menu = menu.addMenu("File")

    new_file_action    = QAction("New File", window)
    new_project_action = QAction("New Project...", window)
    open_action        = QAction("Open File...", window)
    open_folder_action = QAction("Open Folder (Project)...", window)
    save_action        = QAction("Save", window)
    save_as_action     = QAction("Save As...", window)
    settings_action    = QAction("⚙ Settings", window)

    new_file_action.setShortcut(QKeySequence("Ctrl+N"))
    new_project_action.setShortcut(QKeySequence("Ctrl+Shift+N"))
    open_action.setShortcut(QKeySequence("Ctrl+O"))
    save_action.setShortcut(QKeySequence("Ctrl+S"))
    save_as_action.setShortcut(QKeySequence("Ctrl+Shift+S"))
    settings_action.setShortcut(QKeySequence("Ctrl+,"))

    new_project_action.triggered.connect(lambda: _new_project(window))

    # Recent Projects submenu — styled on aboutToShow so it tracks theme changes
    recent_menu = QMenu("Recent Projects", window)
    recent_menu.setStyleSheet(build_menu_stylesheet(get_theme()))
    recent_menu.aboutToShow.connect(
        lambda: _populate_recent_projects(recent_menu, window)
    )

    def _dialog_style() -> str:
        return build_file_dialog_stylesheet(get_theme())

    def new_file():
        window.add_new_tab("Untitled", "")

    def open_folder():
        dialog = QFileDialog(window, "Open Project Folder")
        dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        dialog.setFileMode(QFileDialog.FileMode.Directory)
        dialog.setOption(QFileDialog.Option.ShowDirsOnly, True)
        dialog.setStyleSheet(_dialog_style())
        if dialog.exec():
            selected = dialog.selectedFiles()
            if selected and os.path.isdir(selected[0]):
                _open_recent_project(selected[0], window)

    def open_file():
        from PyQt6.QtCore import QDir
        start_dir = (window.git_dock.repo_path
                     if hasattr(window, 'git_dock') and window.git_dock.repo_path
                     else QDir.currentPath())
        dialog = QFileDialog(window, "Open File", start_dir)
        dialog.setStyleSheet(_dialog_style())
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptOpen)
        if dialog.exec():
            selected = dialog.selectedFiles()
            if selected:
                window.open_file_in_tab(selected[0])

    def save_as_file():
        editor = window.current_editor()
        if not editor:
            return
        from PyQt6.QtCore import QDir
        start_dir = (window.git_dock.repo_path
                     if hasattr(window, 'git_dock') and window.git_dock.repo_path
                     else QDir.currentPath())
        path, _ = QFileDialog.getSaveFileName(
            window, "Save File As", start_dir, "All Files (*)"
        )
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(editor.toPlainText())
                editor.file_path = path
                index = window.tabs.indexOf(editor)
                window.tabs.setTabText(index, os.path.basename(path))
                if hasattr(editor, 'set_original_state'):
                    editor.set_original_state(editor.toPlainText())
                if hasattr(window, 'git_dock'):
                    window.git_dock.refresh_status()
                window.statusBar().showMessage(f"Saved as: {path}", 3000)
            except Exception as e:
                QMessageBox.critical(window, "Save Error", f"Could not save: {e}")

    new_file_action.triggered.connect(new_file)
    open_action.triggered.connect(open_file)
    open_folder_action.triggered.connect(open_folder)
    save_action.triggered.connect(window.save_file)
    save_as_action.triggered.connect(save_as_file)
    settings_action.triggered.connect(window.show_settings_dialog)

    file_menu.addAction(new_file_action)
    file_menu.addAction(new_project_action)
    file_menu.addSeparator()
    file_menu.addAction(open_action)
    file_menu.addAction(open_folder_action)
    file_menu.addMenu(recent_menu)
    file_menu.addSeparator()
    file_menu.addAction(save_action)
    file_menu.addAction(save_as_action)
    file_menu.addSeparator()
    file_menu.addAction(settings_action)