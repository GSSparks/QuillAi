import sys
import os
import tempfile
import ast

from PyQt6.QtWidgets import (QApplication, QMainWindow, QProgressBar, QLabel, 
                             QDockWidget, QTreeView, QPlainTextEdit, QTextEdit, 
                             QVBoxLayout, QWidget, QLineEdit, QTabWidget,
                             QPushButton, QHBoxLayout, QMessageBox, QFileDialog)
from PyQt6.QtCore import QTimer, QThread, Qt, QDir, QProcess
from PyQt6.QtGui import (QFileSystemModel, QAction, QKeySequence, QTextCursor,
                         QIcon, QPixmap, QPainter, QColor, QShortcut)

from editor.ghost_editor import GhostEditor
from ai.worker import AIWorker
from ui.menu import setup_file_menu
from ui.find_replace import FindReplaceWidget

from editor.highlighter import registry
from plugins.git_plugin import GitDockWidget
from plugins.python_plugin import PythonPlugin
from plugins.html_plugin import HTMLPlugin

registry.register(".html", HTMLPlugin)
registry.register(".htm", HTMLPlugin)
registry.register(".py", PythonPlugin)

class CustomFileSystemModel(QFileSystemModel):
    def __init__(self):
        super().__init__()
        self.folder_icon = self._create_icon("#D4A373", is_folder=True)
        self.file_icon = self._create_icon("#A9A9A9", is_folder=False)
        self.py_icon = self._create_icon("#4B8BBE", is_folder=False)
        self.html_icon = self._create_icon("#E34F26", is_folder=False)

    def _create_icon(self, color, is_folder):
        pixmap = QPixmap(16, 16)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if is_folder:
            painter.setBrush(QColor(color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(1, 2, 7, 4, 1, 1)
            painter.drawRoundedRect(1, 5, 14, 9, 2, 2)
        else:
            painter.setBrush(QColor(color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(3, 1, 10, 14, 1, 1)
            painter.setBrush(QColor("#1E1E1E"))
            painter.drawRect(5, 5, 6, 1)
            painter.drawRect(5, 8, 6, 1)
            painter.drawRect(5, 11, 4, 1)

        painter.end()
        return QIcon(pixmap)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DecorationRole:
            if self.isDir(index):
                return self.folder_icon
            else:
                filename = self.fileName(index).lower()
                if filename.endswith(".py"):
                    return self.py_icon
                elif filename.endswith((".html", ".htm")):
                    return self.html_icon
                else:
                    return self.file_icon
        return super().data(index, role)

# [FIXED] Moved DOCK_STYLE to the global scope!
DOCK_STYLE = """
    QDockWidget {
        color: #CCCCCC;
        font-family: 'Inter', 'SF Pro Text', 'Segoe UI', sans-serif;
        font-weight: bold;
        font-size: 10pt;
    }
    QDockWidget::title {
        background-color: #252526;
        text-align: left;
        padding-left: 10px;
        padding-top: 6px;
        padding-bottom: 6px;
    }
"""

class CodeEditor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("QuillAI")
        self._is_loading = False
        self.current_error_text = ""

        # --------------------------
        # Tab System Setup
        # --------------------------
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.setStyleSheet("""
            QTabWidget::pane { border: none; background-color: #1E1E1E; }
            QTabBar::tab {
                background-color: #2D2D30;
                color: #888888;
                padding: 8px 15px;
                border-right: 1px solid #1E1E1E;
                font-family: 'Inter', 'SF Pro Text', 'Segoe UI', sans-serif;
                font-size: 10pt;
            }
            QTabBar::tab:selected {
                background-color: #1E1E1E;
                color: #FFFFFF;
                border-top: 2px solid #0E639C;
            }
        """)

        # --------------------------
        # Layout Assembly (Tabs + Find/Replace)
        # --------------------------
        self.central_container = QWidget()
        self.central_layout = QVBoxLayout(self.central_container)
        self.central_layout.setContentsMargins(0, 0, 0, 0)
        self.central_layout.setSpacing(0)

        # Initialize and hide the Find/Replace Panel
        self.find_replace_panel = FindReplaceWidget(self)
        self.find_replace_panel.hide()

        self.central_layout.addWidget(self.find_replace_panel)
        self.central_layout.addWidget(self.tabs)
        
        self.setCentralWidget(self.central_container)

        # Keybinds (Find, Replace, Save)
        self.find_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        self.find_shortcut.activated.connect(self.show_find_replace)

        self.replace_shortcut = QShortcut(QKeySequence("Ctrl+H"), self)
        self.replace_shortcut.activated.connect(self.show_find_replace)

        self.save_shortcut = QShortcut(QKeySequence("Ctrl+S"), self)
        self.save_shortcut.activated.connect(self.save_file)

        self.timer = QTimer()
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.ask_ai)

        setup_file_menu(self)
        self.setup_run_menu()

        # UI Status Bar
        self.status_bar = self.statusBar()
        self.ai_status_label = QLabel("AI Thinking...")
        self.ai_progress = QProgressBar()
        self.ai_progress.setRange(0, 0)
        self.ai_progress.setMaximumWidth(150)
        self.ai_progress.setFixedHeight(14)
        self.status_bar.addPermanentWidget(self.ai_status_label)
        self.status_bar.addPermanentWidget(self.ai_progress)
        self.hide_loading_indicator()

        # Panels & Sidebars
        self.setup_sidebar()
        self.setup_git_panel()
        self.setup_output_panel()
        self.setup_chat_panel()

        self.process = QProcess(self)
        self.process.readyReadStandardOutput.connect(self.handle_stdout)
        self.process.readyReadStandardError.connect(self.handle_stderr)
        self.process.finished.connect(self.process_finished)

        self.last_worker = None
        self.chat_worker = None
        self.active_threads = []

        # Start with a blank tab
        self.add_new_tab("Untitled", "")

    # -----------------------------
    # Find / Replace Method
    # -----------------------------
    def show_find_replace(self):
        self.find_replace_panel.show()
        self.find_replace_panel.focus_find()

    # -----------------------------
    # Tab Management Methods
    # -----------------------------
    def current_editor(self):
        return self.tabs.currentWidget()

    def add_new_tab(self, name="Untitled", content="", path=None):
        editor = GhostEditor()

        self._is_loading = True # <-- LOCK ON
        editor.setPlainText(content)
        editor.set_original_state(content)
        editor.file_path = path

        ext = os.path.splitext(name)[1].lower() if path else ".py"

        editor.highlighter = registry.get_highlighter(editor.document(), ext)

        editor.textChanged.connect(self.on_text_changed)
        editor.ai_started.connect(self.show_loading_indicator)
        editor.ai_finished.connect(self.hide_loading_indicator)

        index = self.tabs.addTab(editor, name)
        self.tabs.setCurrentIndex(index)
        
        self._is_loading = False # <-- LOCK OFF (Moved to the very end!)
        return editor
        
    def closeEvent(self, event):
        # Check if ANY tabs are dirty
        unsaved = False
        for i in range(self.tabs.count()):
            editor = self.tabs.widget(i)
            if hasattr(editor, 'is_dirty') and editor.is_dirty():
                unsaved = True
                break
                
        if unsaved:
            reply = QMessageBox.question(
                self, "Unsaved Changes",
                "You have unsaved files. Do you want to save them before exiting?",
                QMessageBox.StandardButton.SaveAll | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel
            )
            
            if reply == QMessageBox.StandardButton.SaveAll:
                for i in range(self.tabs.count()):
                    editor = self.tabs.widget(i)
                    if hasattr(editor, 'is_dirty') and editor.is_dirty():
                        self.save_file(i)
                event.accept() # Allow the app to close
            elif reply == QMessageBox.StandardButton.Discard:
                event.accept() # Close without saving
            else:
                event.ignore() # Cancel the close entirely
        else:
            event.accept()
            
    def close_tab(self, index):
        editor = self.tabs.widget(index)
        if not editor: return

        # Check for unsaved changes before closing the tab
        if hasattr(editor, 'is_dirty') and editor.is_dirty():
            filename = self.tabs.tabText(index).replace("*", "")
            reply = QMessageBox.question(
                self, "Unsaved Changes",
                f"Save changes to '{filename}' before closing?",
                QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel
            )

            if reply == QMessageBox.StandardButton.Save:
                if not self.save_file(index):
                    return # Abort close if they cancel the save dialog
            elif reply == QMessageBox.StandardButton.Cancel:
                return # Abort close entirely

        widget = self.tabs.widget(index)
        if widget:
            widget.deleteLater()
        self.tabs.removeTab(index)
        if self.tabs.count() == 0:
            self.add_new_tab("Untitled", "")

    def open_file_in_tab(self, file_path):
        # Prevent trying to open directories as text files
        if os.path.isdir(file_path):
            return

        # Prevent opening the same file twice
        for i in range(self.tabs.count()):
            editor = self.tabs.widget(i)
            if hasattr(editor, 'file_path') and editor.file_path == file_path:
                self.tabs.setCurrentIndex(i)
                return

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            filename = os.path.basename(file_path)
            self.add_new_tab(filename, content, file_path)
        except Exception as e:
            print(f"Could not open file: {e}")
            
    def save_file(self, index=None):
        if index is None:
            index = self.tabs.currentIndex()
        editor = self.tabs.widget(index)
        if not editor: return False

        # Ask for a path if this is a new file
        if not editor.file_path:
            path, _ = QFileDialog.getSaveFileName(self, "Save File", "", "Python Files (*.py);;HTML Files (*.html);;All Files (*)")
            if path:
                editor.file_path = path
                self.tabs.setTabText(index, os.path.basename(path))
            else:
                return False # User canceled the save dialog

        code = editor.toPlainText()
        try:
            with open(editor.file_path, "w", encoding="utf-8") as f:
                f.write(code)
            
            # Reset change tracking for the gutter
            editor.set_original_state(code) 
            
            # Remove the asterisk from the tab title
            current_text = self.tabs.tabText(index)
            if current_text.endswith("*"):
                self.tabs.setTabText(index, current_text[:-1])

            # Automatically update the Git tree
            if hasattr(self, 'git_dock'):
                self.git_dock.refresh_status()

            return True
        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"Could not save file: {e}")
            return False
            
    # -----------------------------
    # Cross-File Context Engine
    # -----------------------------
    def resolve_local_imports(self, code_text):
        editor = self.current_editor()
        if not editor: return ""

        try:
            tree = ast.parse(code_text)
        except Exception:
            return ""

        # Find the project root
        if hasattr(self, 'tree_view') and self.file_model:
            project_root = self.file_model.filePath(self.tree_view.rootIndex())
        elif editor.file_path:
            project_root = os.path.dirname(editor.file_path)
        else:
            return ""

        imported_context = []
        for node in ast.walk(tree):
            modules = []
            if isinstance(node, ast.ImportFrom) and node.module:
                modules.append(node.module)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    modules.append(alias.name)

            for mod in modules:
                rel_path = mod.replace('.', os.sep) + '.py'
                full_path = os.path.join(project_root, rel_path)

                if not os.path.exists(full_path) and editor.file_path:
                    full_path = os.path.join(os.path.dirname(editor.file_path), rel_path)

                if os.path.exists(full_path):
                    try:
                        with open(full_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                            if len(content) > 1500:
                                content = content[:1500] + "\n...[Code truncated]..."
                            imported_context.append(f"\n--- Context from imported file: {mod} ---\n```python\n{content}\n```\n")
                    except Exception:
                        pass
        return "".join(imported_context)

    # -----------------------------
    # Chat Panel
    # -----------------------------
    def setup_chat_panel(self):
        self.chat_dock = QDockWidget("AI Chat", self)
        self.chat_dock.setStyleSheet(DOCK_STYLE)

        chat_container = QWidget()
        chat_layout = QVBoxLayout(chat_container)
        chat_layout.setContentsMargins(5, 5, 5, 5)

        self.chat_history = QTextEdit()
        self.chat_history.setReadOnly(True)
        self.chat_history.setStyleSheet("""
            QTextEdit {
                background-color: #1E1E1E;
                color: #CCCCCC;
                font-family: 'Inter', 'SF Pro Text', 'Segoe UI', sans-serif;
                font-size: 11pt;
                border: 1px solid #3E3E42;
                border-radius: 4px;
            }
        """)

        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText("Ask QuillAI about your code...")
        self.chat_input.setStyleSheet("""
            QLineEdit {
                background-color: #2D2D30;
                color: #FFFFFF;
                border: 1px solid #3E3E42;
                border-radius: 4px;
                padding: 8px;
                font-family: 'Inter', 'SF Pro Text', 'Segoe UI', sans-serif;
                font-size: 10pt;
            }
        """)
        self.chat_input.returnPressed.connect(self.send_chat_message)

        chat_layout.addWidget(self.chat_history)
        chat_layout.addWidget(self.chat_input)
        self.chat_dock.setWidget(chat_container)
        self.chat_dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetClosable | QDockWidget.DockWidgetFeature.DockWidgetMovable)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.chat_dock)

    def send_chat_message(self):
        user_text = self.chat_input.text().strip()
        if not user_text: return
        self.chat_input.clear()

        self.chat_history.moveCursor(QTextCursor.MoveOperation.End)
        self.chat_history.insertPlainText(f"\nYou: {user_text}\n\nQuillAI: ")
        self.chat_history.ensureCursorVisible()

        editor = self.current_editor()
        active_code = editor.toPlainText() if editor else ""
        cross_file_context = self.resolve_local_imports(active_code)

        if len(active_code) > 2000:
            active_code = "...(truncated)...\n" + active_code[-2000:]

        prompt_with_context = f"{user_text}\n\n[Context: The user is currently editing a file with this code:]\n```python\n{active_code}\n```\n{cross_file_context}"

        thread = QThread()
        self.chat_worker = AIWorker(prompt=prompt_with_context, editor_text="", cursor_pos=0, is_chat=True)
        self.chat_worker.moveToThread(thread)
        self.chat_worker.chat_update.connect(self.append_chat_stream)
        self.chat_worker.finished.connect(thread.quit)
        self.chat_worker.finished.connect(self.chat_worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        self.show_loading_indicator()
        self.chat_worker.finished.connect(self.hide_loading_indicator)
        self.active_threads.append(thread)
        thread.finished.connect(lambda: self.active_threads.remove(thread) if thread in self.active_threads else None)
        thread.started.connect(self.chat_worker.run)
        thread.start()

    def append_chat_stream(self, text):
        self.chat_history.moveCursor(QTextCursor.MoveOperation.End)
        self.chat_history.insertPlainText(text)
        self.chat_history.ensureCursorVisible()

    # -----------------------------
    # Runner Methods
    # -----------------------------
    def setup_run_menu(self):
        run_menu = self.menuBar().addMenu("Run")
        run_action = QAction("Run Script", self)
        run_action.setShortcut(QKeySequence("F5"))
        run_action.triggered.connect(self.run_script)
        run_menu.addAction(run_action)

    def setup_output_panel(self):
        # The main container
        output_container = QWidget()
        layout = QVBoxLayout(output_container)
        layout.setContentsMargins(0, 0, 0, 0)

        self.output_editor = QPlainTextEdit()
        self.output_editor.setReadOnly(True)
        self.output_editor.setStyleSheet("QPlainTextEdit { background-color: #1E1E1E; color: #CCCCCC; font-family: 'JetBrains Mono', monospace; font-size: 10pt; border: none; }")
        
        # Explain Error Button
        self.explain_error_btn = QPushButton("💡 Explain Error")
        self.explain_error_btn.setStyleSheet("""
            QPushButton {
                background-color: #8A2BE2; /* A nice AI purple */
                color: white;
                border: none;
                padding: 6px 12px;
                border-radius: 4px;
                font-family: 'Inter', 'SF Pro Text', 'Segoe UI', sans-serif;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #9B30FF; }
        """)
        self.explain_error_btn.hide() # Hide it until there is an error
        self.explain_error_btn.clicked.connect(self.explain_error)

        # Create a horizontal row just for the button so we can push it to the right
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(5, 5, 5, 5)
        btn_layout.addStretch() # Pushes the button to the right
        btn_layout.addWidget(self.explain_error_btn)

        layout.addWidget(self.output_editor)
        layout.addLayout(btn_layout)

        self.output_dock = QDockWidget("Output", self)
        self.output_dock.setStyleSheet(DOCK_STYLE) 
        self.output_dock.setWidget(output_container) 
        self.output_dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetClosable | QDockWidget.DockWidgetFeature.DockWidgetMovable)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.output_dock)
        self.output_dock.hide()

    def run_script(self):
        editor = self.current_editor()
        if not editor: return

        if self.process.state() == QProcess.ProcessState.Running:
            self.process.kill()

        # Reset the error state for a fresh run
        self.output_editor.clear()
        self.current_error_text = ""
        self.explain_error_btn.hide()
        self.output_dock.show() 

        code = editor.toPlainText()
        
        if editor.file_path:
            with open(editor.file_path, "w", encoding="utf-8") as f:
                f.write(code)
            script_path = editor.file_path
            editor.set_original_state(code)
        else:
            self.temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".py")
            self.temp_file.write(code.encode("utf-8"))
            self.temp_file.close()
            script_path = self.temp_file.name

        self.output_editor.appendPlainText(f">>> Running {os.path.basename(script_path)}...\n")
        self.process.start(sys.executable, [script_path])

    def handle_stderr(self):
        data = self.process.readAllStandardError()
        stderr = bytes(data).decode("utf8")
        self.output_editor.insertPlainText(stderr)
        self.output_editor.ensureCursorVisible()
        
        # Track the error and show the button
        self.current_error_text += stderr
        self.explain_error_btn.show()

    def explain_error(self):
        if not self.current_error_text.strip():
            return

        # Ensure the chat panel is open and visible
        self.chat_dock.show()
        self.explain_error_btn.hide()

        user_text = "My script crashed with an error. Can you explain what went wrong and how to fix it?"

        self.chat_history.moveCursor(QTextCursor.MoveOperation.End)
        self.chat_history.insertPlainText(
            f"\nYou: {user_text}\n[Error Trace Sent]\n\nQuillAI: "
        )
        self.chat_history.ensureCursorVisible()

        editor = self.current_editor()
        active_code = editor.toPlainText() if editor else ""
        cross_file_context = self.resolve_local_imports(active_code)

        # Trim large inputs
        if len(active_code) > 2000:
            active_code = "...(truncated)...\n" + active_code[-2000:]

        if len(cross_file_context) > 2000:
            cross_file_context = "...(truncated)...\n" + cross_file_context[-2000:]

        # Build the mega prompt
        prompt_with_context = f"""
    {user_text}

    [Error Trace:]
    {self.current_error_text}

    [Active File:]
    {active_code}

    [Related Files / Imports:]
    {cross_file_context}

    Instructions:
    - Explain the error clearly
    - Identify the root cause
    - Show how to fix it
    - Include corrected code if possible
    """

        thread = QThread()

        self.chat_worker = AIWorker(
            prompt=prompt_with_context,
            editor_text="",
            cursor_pos=0,
            is_chat=True
        )

        self.chat_worker.moveToThread(thread)

        # Stream response into chat
        self.chat_worker.chat_update.connect(self.append_chat_stream)

        # Cleanup
        self.chat_worker.finished.connect(thread.quit)
        self.chat_worker.finished.connect(self.chat_worker.deleteLater)
        thread.finished.connect(thread.deleteLater)

        # Loading indicator
        self.show_loading_indicator()
        self.chat_worker.finished.connect(self.hide_loading_indicator)

        self.active_threads.append(thread)
        thread.finished.connect(
            lambda: self.active_threads.remove(thread)
            if thread in self.active_threads else None
        )

        thread.started.connect(self.chat_worker.run)
        thread.start()

    def handle_stdout(self):
        data = self.process.readAllStandardOutput()
        stdout = bytes(data).decode("utf8")
        self.output_editor.insertPlainText(stdout)
        self.output_editor.ensureCursorVisible()

    def process_finished(self):
        self.output_editor.appendPlainText("\n>>> Process finished.")
        if hasattr(self, 'temp_file') and self.temp_file:
            try: os.remove(self.temp_file.name)
            except: pass
            self.temp_file = None

    # -----------------------------
    # Sidebar Methods
    # -----------------------------
    def setup_sidebar(self):
        self.file_model = CustomFileSystemModel()
        self.file_model.setRootPath(QDir.currentPath())

        self.tree_view = QTreeView()
        self.tree_view.setModel(self.file_model)
        self.tree_view.setRootIndex(self.file_model.index(QDir.currentPath()))
        self.tree_view.setHeaderHidden(True)
        for i in range(1, 4): self.tree_view.hideColumn(i)
        self.tree_view.setIndentation(15)

        self.tree_view.setStyleSheet("""
            QTreeView {
                background-color: #1E1E1E;
                color: #CCCCCC;
                border: none;
                font-family: 'Inter', 'SF Pro Text', 'Segoe UI', sans-serif;
                font-size: 11pt;
            }
            QTreeView::item { padding: 4px; }
            QTreeView::item:selected { background-color: #37373D; color: #FFFFFF; border-radius: 4px; }
            QTreeView::item:hover:!selected { background-color: #2A2D2E; border-radius: 4px; }
            QTreeView::branch { background-color: transparent; }
        """)

        self.tree_view.doubleClicked.connect(self.open_tree_item)
        self.sidebar_dock = QDockWidget("Explorer", self)
        self.sidebar_dock.setStyleSheet(DOCK_STYLE)
        self.sidebar_dock.setWidget(self.tree_view)
        self.sidebar_dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetClosable | QDockWidget.DockWidgetFeature.DockWidgetMovable)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.sidebar_dock)

    def setup_git_panel(self):
        self.git_dock = GitDockWidget(self)
        self.git_dock.file_double_clicked.connect(self.open_file_in_tab)
        
        # Dock it to the left, tabbed with the Explorer
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.git_dock)
        self.tabifyDockWidget(self.sidebar_dock, self.git_dock)
        
    def open_tree_item(self, index):
        file_path = self.file_model.filePath(index)
        if not self.file_model.isDir(index):
            self.open_file_in_tab(file_path)

    # -----------------------------
    # AI Control Methods
    # -----------------------------
    def show_loading_indicator(self):
        self.ai_status_label.show()
        self.ai_progress.show()
        self.timer.stop()

    def hide_loading_indicator(self):
        self.ai_status_label.hide()
        self.ai_progress.hide()

    def on_text_changed(self):
        editor = self.current_editor()
        
        if not editor or getattr(self, '_is_loading', False) or editor.function_active or not editor.hasFocus():
            return

        # Add or remove the asterisk indicator dynamically
        if hasattr(editor, 'is_dirty'):
            index = self.tabs.indexOf(editor)
            current_title = self.tabs.tabText(index)
            if editor.is_dirty() and not current_title.endswith("*"):
                self.tabs.setTabText(index, current_title + "*")
            elif not editor.is_dirty() and current_title.endswith("*"):
                self.tabs.setTabText(index, current_title[:-1])

        self.timer.start(500)
        editor.clear_ghost_text()
        
        if self.last_worker:
            self.last_worker.cancel()

    def ask_ai(self):
        editor = self.current_editor()
        if not editor: return

        cursor = editor.textCursor()
        line_text = cursor.block().text().strip()

        generate_function = False
        if line_text.startswith("#") and "function" in line_text.lower():
            generate_function = True
        if not line_text.strip() or line_text.strip().endswith(":") or line_text.strip().endswith(")"):
            return

        text = editor.toPlainText()
        cursor_pos = int(cursor.position())
        context = text[max(0, cursor_pos-1500):cursor_pos]
        cross_file_context = self.resolve_local_imports(text)

        if generate_function:
            prompt = f"You are a coding assistant.\nGenerate a full Python function that fulfills the following comment.\nComment: {line_text}\n{cross_file_context}\nOnly output the code for the function. Do not repeat the comment."
        else:
            prompt = f"{cross_file_context}\nComplete the following code:\n\n{context}"

        thread = QThread()
        worker = AIWorker(prompt, text, cursor_pos, generate_function=generate_function)
        worker.moveToThread(thread)
        worker.update_ghost.connect(editor.set_ghost_text)
        worker.function_ready.connect(editor.handle_function_output)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)

        self.show_loading_indicator()
        worker.finished.connect(self.hide_loading_indicator)

        self.last_worker = worker
        self.active_threads.append(thread)
        thread.finished.connect(lambda: self.active_threads.remove(thread) if thread in self.active_threads else None)

        thread.started.connect(worker.run)
        thread.start()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = CodeEditor()
    window.resize(1000, 700)
    window.show()
    sys.exit(app.exec())