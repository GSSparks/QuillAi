import os
from PyQt6.QtWidgets import QFileDialog, QMessageBox
from PyQt6.QtGui import QAction, QKeySequence
from editor.highlighter import registry

DIALOG_STYLE = """
    QFileDialog, QMessageBox { background-color: #1E1E1E; color: #CCCCCC; font-family: 'JetBrains Mono', monospace; }
    QWidget { background-color: #1E1E1E; color: #CCCCCC; }
    QLineEdit, QTreeView, QListView { background-color: #2D2D30; border: 1px solid #3E3E42; border-radius: 4px; color: white; padding: 2px; }
    QPushButton { background-color: #0E639C; color: white; border: none; padding: 6px 12px; border-radius: 4px; }
    QPushButton:hover { background-color: #1177BB; }
"""

def setup_file_menu(window): 
    menu = window.menuBar()
    file_menu = menu.addMenu("File")

    new_file_action = QAction("New File", window)
    open_action = QAction("Open File...", window)
    open_folder_action = QAction("Open Folder (Project)...", window)
    save_action = QAction("Save", window)
    save_as_action = QAction("Save As...", window)

    new_file_action.setShortcut(QKeySequence("Ctrl+N"))
    open_action.setShortcut(QKeySequence("Ctrl+O"))
    save_action.setShortcut(QKeySequence("Ctrl+S"))
    save_as_action.setShortcut(QKeySequence("Ctrl+Shift+S"))

    def create_themed_dialog(title, accept_mode, is_folder=False):
        dialog = QFileDialog(window, title)
        if is_folder:
            dialog.setFileMode(QFileDialog.FileMode.Directory)
        else:
            dialog.setAcceptMode(accept_mode)
        return dialog

    def new_file():
        # Let the main window handle tab creation
        window.add_new_tab("Untitled", "")

    def open_folder():
        dialog = create_themed_dialog("Open Project Folder", QFileDialog.AcceptMode.AcceptOpen, is_folder=True)
        if dialog.exec():
            selected_files = dialog.selectedFiles()
            if selected_files:
                folder_path = selected_files[0]
                if hasattr(window, 'tree_view') and hasattr(window, 'file_model'):
                    window.tree_view.setRootIndex(window.file_model.index(folder_path))

    def open_file():
        dialog = create_themed_dialog("Open File", QFileDialog.AcceptMode.AcceptOpen)
        if dialog.exec():
            selected_files = dialog.selectedFiles()
            if selected_files:
                path = selected_files[0]
                
                # Extract the folder path from the file and change directory!
                # Example: turns '/home/user/dev/main.py' into '/home/user/dev'
                file_directory = os.path.dirname(path)
                os.chdir(file_directory)
                
                window.open_file_in_tab(path)
                
                # Force the Git plugin to refresh immediately after the directory changes
                if hasattr(window, 'git_plugin'):
                    window.git_plugin.refresh_status()

    def save_as_file():
        editor = window.current_editor()
        if not editor: return

        dialog = create_themed_dialog("Save File As", QFileDialog.AcceptMode.AcceptSave)
        if dialog.exec():
            selected_files = dialog.selectedFiles()
            if selected_files:
                path = selected_files[0]
                with open(path, "w", encoding="utf-8") as f:
                    f.write(editor.toPlainText())

                # Update the specific tab's info
                editor.file_path = path
                index = window.tabs.indexOf(editor)
                window.tabs.setTabText(index, os.path.basename(path))

                # [NEW] Clear the dirty tracker so the asterisk disappears
                if hasattr(editor, 'set_original_state'):
                    editor.set_original_state(editor.toPlainText())

                # Assign it here too!
                _, ext = os.path.splitext(path)
                editor.highlighter = registry.get_highlighter(editor.document(), ext.lower())
                
                # [NEW] Automatically update the Git tree!
                if hasattr(window, 'git_dock'):
                    window.git_dock.refresh_status()

    new_file_action.triggered.connect(new_file)
    open_action.triggered.connect(open_file)
    open_folder_action.triggered.connect(open_folder)
    
    # [FIXED] Route the standard Save directly to the main window's method!
    save_action.triggered.connect(window.save_file)
    
    save_as_action.triggered.connect(save_as_file)

    file_menu.addAction(new_file_action)
    file_menu.addSeparator() 
    file_menu.addAction(open_action)
    file_menu.addAction(open_folder_action)
    file_menu.addSeparator()
    file_menu.addAction(save_action)
    file_menu.addAction(save_as_action)