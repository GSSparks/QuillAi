import os
from PyQt6.QtWidgets import QFileDialog, QMessageBox
from PyQt6.QtGui import QAction, QKeySequence
from editor.highlighter import registry

DIALOG_STYLE = """
    QFileDialog, QMessageBox { 
        background-color: #1E1E1E; 
        color: #CCCCCC; 
        font-family: 'JetBrains Mono', monospace; 
    }
    QWidget { 
        background-color: #1E1E1E; 
        color: #CCCCCC; 
    }
    QLineEdit, QTreeView, QListView { 
        background-color: #2D2D30; 
        border: 1px solid #3E3E42; 
        border-radius: 4px; 
        color: white; 
        padding: 2px; 
    }
    QPushButton { 
        background-color: #0E639C; 
        color: white; 
        border: none; 
        padding: 6px 12px; 
        border-radius: 4px; 
    }
    QPushButton:hover { background-color: #1177BB; }
"""

def setup_file_menu(window):
    menu = window.menuBar()
    file_menu = menu.addMenu("File")

    # Actions
    new_file_action = QAction("New File", window)
    open_action = QAction("Open File...", window)
    open_folder_action = QAction("Open Folder (Project)...", window)
    save_action = QAction("Save", window)
    save_as_action = QAction("Save As...", window)
    
    # [NEW] Settings Action
    settings_action = QAction("⚙ Settings", window)

    # Shortcuts
    new_file_action.setShortcut(QKeySequence("Ctrl+N"))
    open_action.setShortcut(QKeySequence("Ctrl+O"))
    save_action.setShortcut(QKeySequence("Ctrl+S"))
    save_as_action.setShortcut(QKeySequence("Ctrl+Shift+S"))
    # Standard shortcut for settings
    settings_action.setShortcut(QKeySequence("Ctrl+,")) 

    # --- Internal Helper Functions ---

    def create_themed_dialog(title, accept_mode, is_folder=False):
        # We pass 'window' as the parent to keep the dialog centered and stable
        dialog = QFileDialog(window, title)
        
        # [CRITICAL] Force Qt's own dialog instead of the OS native one
        # This prevents the crash on NixOS/Linux/Wayland
        dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        
        if is_folder:
            # Set to only select existing directories
            dialog.setFileMode(QFileDialog.FileMode.Directory)
            # Ensure the "Open" button works for folders
            dialog.setOption(QFileDialog.Option.ShowDirsOnly, True)
        else:
            dialog.setAcceptMode(accept_mode)
            
        dialog.setStyleSheet(DIALOG_STYLE)
        return dialog

    def new_file():
        window.add_new_tab("Untitled", "")

    def open_folder():
        dialog = create_themed_dialog("Open Project Folder", QFileDialog.AcceptMode.AcceptOpen, is_folder=True)
        if dialog.exec():
            selected_files = dialog.selectedFiles()
            if selected_files:
                folder_path = selected_files[0]
                
                # Double-check the path is a valid directory string
                if os.path.isdir(folder_path):
                    if hasattr(window, 'tree_view') and hasattr(window, 'file_model'):
                        window.tree_view.setRootIndex(window.file_model.index(folder_path))
                    
                    if hasattr(window, 'git_dock'):
                        window.git_dock.repo_path = folder_path
                        window.git_dock.refresh_status()

    def open_file():
        # Get the project path for the dialog starting point
        start_dir = window.git_dock.repo_path if hasattr(window, 'git_dock') and window.git_dock.repo_path else QDir.currentPath()
        
        dialog = QFileDialog(window, "Open File", start_dir)
        dialog.setStyleSheet(DIALOG_STYLE)
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptOpen)
        
        if dialog.exec():
            selected_files = dialog.selectedFiles()
            if selected_files:
                path = selected_files[0]
                window.open_file_in_tab(path)

    def save_as_file():
        editor = window.current_editor()
        if not editor: return

        # Get the project path
        start_dir = window.git_dock.repo_path if hasattr(window, 'git_dock') and window.git_dock.repo_path else QDir.currentPath()

        path, _ = QFileDialog.getSaveFileName(window, "Save File As", start_dir, "All Files (*)")
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

    # --- Connect Signals ---
    new_file_action.triggered.connect(new_file)
    open_action.triggered.connect(open_file)
    open_folder_action.triggered.connect(open_folder)
    save_action.triggered.connect(window.save_file)
    save_as_action.triggered.connect(save_as_file)
    
    settings_action.triggered.connect(window.show_settings_dialog)

    # --- Build Menu ---
    file_menu.addAction(new_file_action)
    file_menu.addSeparator() 
    file_menu.addAction(open_action)
    file_menu.addAction(open_folder_action)
    file_menu.addSeparator()
    file_menu.addAction(save_action)
    file_menu.addAction(save_as_action)
    file_menu.addSeparator()
    # Add the settings action at the bottom
    file_menu.addAction(settings_action)