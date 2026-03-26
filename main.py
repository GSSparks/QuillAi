import sys
import os
import tempfile
import ast
import re
import base64

from PyQt6.QtWidgets import (QApplication, QMainWindow, QProgressBar, QLabel,
                             QDockWidget, QTreeView, QPlainTextEdit, QTextEdit,
                             QVBoxLayout, QWidget, QLineEdit, QTabWidget,
                             QPushButton, QHBoxLayout, QMessageBox, QFileDialog,
                             QTextBrowser, QSizePolicy)
from PyQt6.QtCore import QTimer, QThread, Qt, QDir, QProcess, QUrl
from PyQt6.QtGui import (QFileSystemModel, QAction, QKeySequence, QTextCursor,
                         QIcon, QPixmap, QPainter, QColor, QShortcut,
                         QSyntaxHighlighter, QTextCharFormat, QFont)

from editor.ghost_editor import GhostEditor
from ai.worker import AIWorker
from ui.menu import setup_file_menu
from ui.find_replace import FindReplaceWidget
from ui.find_in_files import FindInFilesWidget
from ui.settings_manager import SettingsManager
from ui.settings_dialog import SettingsDialog
from ui.memory_manager import MemoryManager
from ui.memory_panel import MemoryPanel
from ui.session_manager import save_session, load_session
from ui.session_intent import init_tracker
from ui.sliding_chat_panel import SlidingPanel

from editor.highlighter import registry
from plugins.git_plugin import GitDockWidget
from plugins.python_plugin import PythonPlugin
from plugins.html_plugin import HTMLPlugin
from plugins.ansible_plugin import AnsiblePlugin
from plugins.nix_plugin import NixPlugin
from plugins.bash_plugin import BashPlugin
from plugins.markdown_plugin import MarkdownPlugin

registry.register(".html", HTMLPlugin)
registry.register(".htm", HTMLPlugin)
registry.register(".py", PythonPlugin)
registry.register(".yml", AnsiblePlugin)
registry.register(".yaml", AnsiblePlugin)
registry.register(".nix", NixPlugin)
registry.register(".sh", BashPlugin)
registry.register(".bash", BashPlugin)
registry.register(".md", MarkdownPlugin)
registry.register(".markdown", MarkdownPlugin)

# ==========================================
# Main Application
# ==========================================
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
        # 1. Load settings FIRST
        self.settings_manager = SettingsManager()
        
        # 2. Load memory
        self.memory_manager = MemoryManager()
        self.intent_tracker = init_tracker(self.memory_manager)

        # 3. Basic App State
        self.setWindowTitle("QuillAI")
        self._is_loading = False
        self.inline_completion_enabled = True
        self.current_error_text = ""
        self.current_ai_raw_text = ""
        self.last_worker = None
        self.chat_worker = None
        self.active_threads = []

        # --------------------------
        # Tab System Setup
        # --------------------------
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(lambda _: self._refresh_markdown_preview())  # ADD THIS
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
        
        self.tabs.currentChanged.connect(lambda _: self.update_status_bar())
        self.tabs.currentChanged.connect(lambda _: self.update_git_branch())
        self.tabs.currentChanged.connect(self._on_tab_changed)

        # --------------------------
        # Layout Assembly (Tabs + Find/Replace)
        # --------------------------
        self.central_container = QWidget()
        self.central_layout = QVBoxLayout(self.central_container)
        self.central_layout.setContentsMargins(0, 0, 0, 0)
        self.central_layout.setSpacing(0)

        self.find_replace_panel = FindReplaceWidget(self)
        self.find_replace_panel.hide()

        self.central_layout.addWidget(self.find_replace_panel)
        self.central_layout.addWidget(self.tabs)

        self.setCentralWidget(self.central_container)

        # Keybinds (Find, Replace)
        self.find_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        self.find_shortcut.activated.connect(self.show_find_replace)

        self.replace_shortcut = QShortcut(QKeySequence("Ctrl+H"), self)
        self.replace_shortcut.activated.connect(self.show_find_replace)

        self.project_search_shortcut = QShortcut(QKeySequence("Ctrl+Shift+F"), self)
        self.project_search_shortcut.activated.connect(self.show_project_search)
        
        self.completion_shortcut = QShortcut(QKeySequence("Ctrl+Space"), self)
        self.completion_shortcut.activated.connect(self.request_manual_completion)

        self.timer = QTimer()
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.ask_ai)

        setup_file_menu(self)
        self.setup_run_menu()
        self.setup_view_menu()

        # UI Status Bar
        self.status_bar = self.statusBar()
        self.status_bar.setSizeGripEnabled(False)
        self.status_bar.setStyleSheet("""
            QStatusBar {
                background-color: #007ACC;
                color: #FFFFFF;
                font-family: 'Inter', 'Segoe UI', sans-serif;
                font-size: 9pt;
            }
            QStatusBar::item {
                border: none;
                background: transparent;
            }
            QStatusBar QLabel {
                color: #FFFFFF;
                background: transparent;
                padding: 0 8px;
                font-size: 9pt;
            }
            QStatusBar QPushButton {
                color: #FFFFFF;
                background: transparent;
                border: none;
                padding: 0 8px;
                font-size: 9pt;
                font-weight: bold;
            }
            QStatusBar QPushButton:hover {
                background-color: rgba(255,255,255,0.15);
            }
            QStatusBar QProgressBar {
                background-color: rgba(255,255,255,0.2);
                border: none;
                border-radius: 6px;
                max-width: 100px;
                min-height: 8px;
                max-height: 8px;
            }
            QStatusBar QProgressBar::chunk {
                background-color: #FFFFFF;
                border-radius: 6px;
            }
            QPushButton {
                color: #FFFFFF;
                background: transparent;
                border: none;
                padding: 0 8px;
                font-size: 9pt;
                font-weight: bold;
            }
            QPushButton:hover { background-color: rgba(255,255,255,0.15); }
        """)
        
        # Left side — git branch
        self.branch_label = QLabel("")
        self.status_bar.addWidget(self.branch_label)
        
        # Separator between branch and the rest
        sep = QLabel("|")
        sep.setStyleSheet("color: rgba(255,255,255,0.3); padding: 0 2px;")
        self.status_bar.addWidget(sep)
        
        # Right side items
        self.filetype_label  = QLabel("")
        self.indent_label    = QLabel("")
        self.encoding_label  = QLabel("UTF-8")
        self.lineending_label = QLabel("LF")
        self.cursor_label    = QLabel("Ln 1, Col 1")
        
        for lbl in (self.filetype_label, self.indent_label,
                    self.encoding_label, self.lineending_label,
                    self.cursor_label):
            self.status_bar.addPermanentWidget(lbl)
        
        # AI mode button and loading indicator
        self.ai_mode_btn = QPushButton("🏠 LOCAL")
        self.ai_mode_btn.setCheckable(False)
        self.ai_mode_btn.setFlat(True)
        self.ai_mode_btn.setFixedWidth(90) 
        self.ai_mode_btn.clicked.connect(self.toggle_ai_mode)
        backend = self.settings_manager.get_backend()
        self.update_mode_label(backend)
        self.status_bar.addPermanentWidget(self.ai_mode_btn) 
        self.hide_loading_indicator()
        
        # Set initial state based on saved settings  
        self.update_mode_label(self.settings_manager.get_backend())

        # Panels & Sidebars
        self.setup_sidebar()
        self.setup_git_panel()
        self.setup_output_panel()
        self.setup_chat_panel()
        self.setup_memory_panel()
        self.setup_markdown_preview()
        self.setup_find_in_files_panel()
        self.process = QProcess(self)
        self.process.readyReadStandardOutput.connect(self.handle_stdout)
        self.process.readyReadStandardError.connect(self.handle_stderr)
        self.process.finished.connect(self.process_finished)

        self._restore_session()
        
    def toggle_inline_completion(self, enabled):
        self.inline_completion_enabled = enabled
        # Optional: Add code to visually indicate the toggle state, e.g., status bar message.
        if enabled:
            print("In-line completion enabled")
        else:
            print("In-line completion disabled")
             
    def update_status_bar(self):
        editor = self.current_editor()
        if not editor:
            self.cursor_label.setText("")
            self.filetype_label.setText("")
            self.indent_label.setText("")
            return
    
        # Ln / Col
        cursor = editor.textCursor()
        line = cursor.blockNumber() + 1
        col  = cursor.columnNumber() + 1
        self.cursor_label.setText(f"Ln {line}, Col {col}")
    
        # File type
        path = getattr(editor, 'file_path', None)
        if path:
            ext = os.path.splitext(path)[1].lower()
            type_map = {
                '.py':   'Python',
                '.md':   'Markdown',
                '.html': 'HTML',
                '.htm':  'HTML',
                '.yml':  'YAML',
                '.yaml': 'YAML',
                '.nix':  'Nix',
                '.sh':   'Bash',
                '.bash': 'Bash',
                '.js':   'JavaScript',
                '.ts':   'TypeScript',
                '.json': 'JSON',
                '.toml': 'TOML',
                '.txt':  'Text',
            }
            self.filetype_label.setText(type_map.get(ext, ext.lstrip('.').upper() or 'Plain Text'))
        else:
            self.filetype_label.setText('Plain Text')
    
        # Indentation — detect from file content
        text = editor.toPlainText()
        tab_count   = sum(1 for l in text.split('\n') if l.startswith('\t'))
        space_count = sum(1 for l in text.split('\n') if l.startswith('    '))
        if tab_count > space_count:
            self.indent_label.setText("Tabs")
        else:
            self.indent_label.setText("Spaces: 4")
    
        # Line endings
        raw = text
        if '\r\n' in raw:
            self.lineending_label.setText("CRLF")
        elif '\r' in raw:
            self.lineending_label.setText("CR")
        else:
            self.lineending_label.setText("LF")
    
        # Encoding — detect from file on disk if saved
        if path and os.path.exists(path):
            try:
                import chardet
                with open(path, 'rb') as f:
                    raw_bytes = f.read(4096)
                detected = chardet.detect(raw_bytes)
                enc = (detected.get('encoding') or 'UTF-8').upper()
                # Normalise common variants
                enc = enc.replace('UTF-8-SIG', 'UTF-8 BOM').replace('ASCII', 'UTF-8')
                self.encoding_label.setText(enc)
            except ImportError:
                self.encoding_label.setText("UTF-8")
        else:
            self.encoding_label.setText("UTF-8")
    
    def update_git_branch(self):
        """Read the current git branch and update the status bar label."""
        repo_path = None
        if hasattr(self, 'git_dock') and self.git_dock.repo_path:
            repo_path = self.git_dock.repo_path
        else:
            editor = self.current_editor()
            if editor and getattr(editor, 'file_path', None):
                repo_path = os.path.dirname(editor.file_path)
    
        if not repo_path:
            self.branch_label.setText("")
            return
    
        try:
            import subprocess
            result = subprocess.run(
                ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
                cwd=repo_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=2,
            )
            if result.returncode == 0:
                branch = result.stdout.strip()
                self.branch_label.setText(f"⎇  {branch}")
            else:
                self.branch_label.setText("")
        except Exception:
            self.branch_label.setText("")    
            
    def load_project_chat(self):
        self.chat_history.clear()
        self.current_ai_raw_text = ""
        saved = self.memory_manager.load_chat_history()
        if saved:
            self.chat_history.setHtml(saved)
            self.chat_history.moveCursor(QTextCursor.MoveOperation.End)
        else:
            self.chat_history.setPlainText("")
        
    def estimate_tokens(self, text: str) -> int:
        """Rough token estimate — 1 token ≈ 4 characters for code."""
        return len(text) // 4

    def build_chat_context(self, user_text: str, active_code: str) -> str:
        TOKEN_BUDGET = 28000  # leave 2k headroom under the 30k limit
        used = self.estimate_tokens(user_text)
        
        # ── Memory (highest priority after the message itself) ──
        memory_ctx = self.memory_manager.build_memory_context(query=user_text)
        used += self.estimate_tokens(memory_ctx)

        # ── 1. Active file (high priority, always include, but cap it) ──
        active_budget = 6000  # tokens
        active_chars = active_budget * 4
        if len(active_code) > active_chars:
            head = active_code[:active_chars // 3]
            tail = active_code[-(active_chars * 2 // 3):]
            active_code_ctx = head + "\n...(truncated)...\n" + tail
        else:
            active_code_ctx = active_code
        used += self.estimate_tokens(active_code_ctx)

        # ── 2. Direct imports (medium priority) ──
        import_ctx = ""
        if used < TOKEN_BUDGET:
            import_budget = TOKEN_BUDGET - used - 8000  # reserve for tabs + tree
            raw_imports = self.resolve_local_imports(active_code, _max_depth=1)
            import_chars = import_budget * 4
            if len(raw_imports) > import_chars:
                import_ctx = raw_imports[:import_chars] + "\n...(imports truncated)..."
            else:
                import_ctx = raw_imports
            used += self.estimate_tokens(import_ctx)

        # ── 3. Open tabs (lower priority, cap each tab tightly) ──
        tabs_ctx = ""
        if used < TOKEN_BUDGET:
            tabs_budget = TOKEN_BUDGET - used - 2000  # reserve for tree
            tabs_chars = tabs_budget * 4
            raw_tabs = self.get_open_tabs_context()
            if len(raw_tabs) > tabs_chars:
                tabs_ctx = raw_tabs[:tabs_chars] + "\n...(tabs truncated)..."
            else:
                tabs_ctx = raw_tabs
            used += self.estimate_tokens(tabs_ctx)
            
        # ── 4. Project tree (cheapest, include last) ──
        tree_ctx = ""
        if used < TOKEN_BUDGET:
            tree_ctx = self.get_project_tree()
            if self.estimate_tokens(tree_ctx) + used > TOKEN_BUDGET:
                tree_ctx = ""  # drop entirely if we're already close
 
        # ── Assemble ──
        parts = []
        if memory_ctx:
            parts.append(memory_ctx)
        parts.append(f"[Active File]\n```python\n{active_code_ctx}\n```")
        if import_ctx:
            parts.append(import_ctx)
        if tabs_ctx:
            parts.append(tabs_ctx)
        if tree_ctx:
            parts.append(tree_ctx)

        return "\n\n".join(parts)    
    
    def toggle_ai_mode(self):
        current = self.settings_manager.get_backend()
        if current == "llama":
            backend = "openai"
        elif current == "openai":
            backend = "claude"
        else:
            backend = "llama"
        self.settings_manager.set_backend(backend)
        self.update_mode_label(backend)
        self.statusBar().showMessage(f"AI Mode: {backend}", 3000)
    
    def update_mode_label(self, backend):
        labels = {
            "llama":  "🏠 LOCAL",
            "openai": "☁️  OPENAI",
            "claude": "🟠 CLAUDE",
        }
        self.ai_mode_btn.setText(labels.get(backend, "🏠 LOCAL"))

    def create_worker(self, prompt, editor_text="", cursor_pos=0,
                      generate_function=False, is_edit=False, is_chat=False):
        backend = self.settings_manager.get_backend()
        model = (self.settings_manager.get_chat_model()
                 if is_chat
                 else self.settings_manager.get_inline_model())
        api_key = (self.settings_manager.get_api_key())

        return AIWorker(
            prompt=prompt,
            editor_text=editor_text,
            cursor_pos=cursor_pos,
            generate_function=generate_function,
            is_edit=is_edit,
            is_chat=is_chat,
            model=model,
            api_url=self.settings_manager.get_api_url(),
            api_key=api_key,
            backend=backend,
        )
        
    def request_manual_completion(self):
        editor = self.current_editor()
        if editor and editor.hasFocus():
            editor.request_completion_hotkey()
    
    def setup_markdown_preview(self):
        # Preview is now built into the sliding panel
        # _refresh_markdown_preview calls chat_panel.update_preview directly
        pass
        
    def _refresh_markdown_preview(self, editor=None):
        if editor is None:
            editor = self.current_editor()
        if not editor:
            return
        path = getattr(editor, 'file_path', '') or ''
        is_md = path.lower().endswith(('.md', '.markdown'))
        if is_md and hasattr(self, 'chat_panel'):
            self.chat_panel.update_preview(editor.toPlainText())
            self.chat_panel.switch_to_preview()
                    
    # -----------------------------
    # Find / Replace Method
    # -----------------------------
    def show_find_replace(self):
        self.find_replace_panel.show()
        self.find_replace_panel.focus_find()

    def setup_find_in_files_panel(self):
        self.search_dock = QDockWidget("Find in Files", self)
        self.search_dock.setStyleSheet(DOCK_STYLE)

        self.find_in_files_widget = FindInFilesWidget(self)
        self.find_in_files_widget.open_file_request.connect(self.open_file_in_tab)

        self.search_dock.setWidget(self.find_in_files_widget)
        self.search_dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetClosable | QDockWidget.DockWidgetFeature.DockWidgetMovable)

        # Dock it at the bottom, and tabify it with the Output panel to save space!
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.search_dock)
        if hasattr(self, 'output_dock'):
            self.tabifyDockWidget(self.output_dock, self.search_dock)
        self.search_dock.hide()

    def show_project_search(self):
        self.search_dock.show()
        self.search_dock.raise_() # Bring to front if tabbed
        self.find_in_files_widget.focus_search()

    # ==========================================
    # Settings Dialog Trigger
    # ==========================================
    def show_settings_dialog(self):
        """Creates and displays the settings window."""
        from ui.settings_dialog import SettingsDialog

        dialog = SettingsDialog(self.settings_manager, self)

        if dialog.exec():
            self.statusBar().showMessage("Settings saved successfully.", 3000)

    # -----------------------------
    # Tab Management Methods
    # -----------------------------
    def current_editor(self):
        return self.tabs.currentWidget()

    def add_new_tab(self, name="Untitled", content="", path=None):
        editor = GhostEditor(settings_manager=self.settings_manager)

        self._is_loading = True
        editor.setPlainText(content)
        editor.set_original_state(content)
        editor.file_path = path

        if path:
            self.intent_tracker.record_file_edit(path)

        ext = os.path.splitext(name)[1].lower() if path else ".py"

        editor.highlighter = registry.get_highlighter(editor.document(), ext)

        editor.cursorPositionChanged.connect(self.update_status_bar)
        editor.textChanged.connect(self.update_status_bar)        
        
        editor.textChanged.connect(self.on_text_changed)
        editor.ai_started.connect(self.show_loading_indicator)
        editor.ai_finished.connect(self.hide_loading_indicator)

        editor.error_help_requested.connect(self.handle_editor_error_help)
        editor.send_to_chat_requested.connect(self.load_snippet_to_chat)
        editor.textChanged.connect(lambda: self._refresh_markdown_preview(editor))
        
        index = self.tabs.addTab(editor, name)
        self.tabs.setCurrentIndex(index)

        self._is_loading = False
        return editor

    def handle_editor_error_help(self, error_msg, code, line_num):
        self.chat_panel.expand()
        self.chat_panel.chat_input.setFocus()

        user_text = f"I have a SyntaxError on line {line_num}: {error_msg}. Can you help me fix it?"

        self.chat_history.moveCursor(QTextCursor.MoveOperation.End)
        self.chat_history.insertPlainText(f"\nYou: {user_text}\n\n[Code Context Sent]\n\nQuillAI: ")
        self.chat_history.ensureCursorVisible()

        prompt = f"""
        The user has encountered a SyntaxError in their Python file.

        Error Message: {error_msg}
        Error Location: Line {line_num}

        Full Code:
        ```python
        {code}
        ```

        Instructions:
        1. Briefly explain what the error means and why it happened.
        2. Provide the corrected code for that line or block.
        """

        thread = QThread()
        self.chat_worker = self.create_worker(
            prompt=prompt_with_context,
            is_chat=True,
        )

        self.chat_worker.moveToThread(thread)
        self.chat_worker.chat_update.connect(self.append_chat_stream)

        self.chat_worker.finished.connect(self.chat_stream_finished)

        self.chat_worker.finished.connect(thread.quit)
        self.chat_worker.finished.connect(self.chat_worker.deleteLater)
        thread.finished.connect(thread.deleteLater)

        self.show_loading_indicator()
        self.chat_worker.finished.connect(self.hide_loading_indicator)

        self.active_threads.append(thread)
        thread.finished.connect(lambda: self.active_threads.remove(thread) if thread in self.active_threads else None)

        thread.started.connect(self.chat_worker.run)
        thread.start()

    def closeEvent(self, event):
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
                event.accept()
            elif reply == QMessageBox.StandardButton.Discard:
                event.accept()
            else:
                event.ignore()
                return
        else:
            event.accept()
    
        # Save session on the way out
        if event.isAccepted():
            self._save_current_session()
            
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'chat_panel'):
            self.chat_panel.reposition()
            self.chat_panel.setFixedHeight(
                self.central_container.height()
            )

    def close_tab(self, index):
        editor = self.tabs.widget(index)
        if not editor: return

        if hasattr(editor, 'is_dirty') and editor.is_dirty():
            filename = self.tabs.tabText(index).replace("*", "")
            reply = QMessageBox.question(
                self, "Unsaved Changes",
                f"Save changes to '{filename}' before closing?",
                QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel
            )

            if reply == QMessageBox.StandardButton.Save:
                if not self.save_file(index):
                    return
            elif reply == QMessageBox.StandardButton.Cancel:
                return

        widget = self.tabs.widget(index)
        if widget:
            widget.deleteLater()
        self.tabs.removeTab(index)
        if self.tabs.count() == 0:
            self.add_new_tab("Untitled", "")

    def open_file_in_tab(self, file_path, line_number=None):
        if os.path.isdir(file_path):
            return

        editor_to_focus = None

        for i in range(self.tabs.count()):
            editor = self.tabs.widget(i)
            if hasattr(editor, 'file_path') and editor.file_path == file_path:
                self.tabs.setCurrentIndex(i)
                editor_to_focus = editor
                break

        if not editor_to_focus:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                filename = os.path.basename(file_path)
                editor_to_focus = self.add_new_tab(filename, content, file_path)
            except Exception as e:
                print(f"Could not open file: {e}")
                return

        if editor_to_focus and line_number is not None:
            cursor = editor_to_focus.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            cursor.movePosition(QTextCursor.MoveOperation.NextBlock, n=line_number - 1)

            editor_to_focus.setTextCursor(cursor)
            editor_to_focus.ensureCursorVisible()
            editor_to_focus.setFocus()
            editor_to_focus.highlight_current_line()

    def save_file(self, index=None):
        if index is None or isinstance(index, bool):
            index = self.tabs.currentIndex()

        editor = self.tabs.widget(index)
        if not editor:
            return False

        if not editor.file_path:
            start_dir = QDir.currentPath()
            if hasattr(self, 'git_dock') and self.git_dock.repo_path:
                start_dir = self.git_dock.repo_path

            path, _ = QFileDialog.getSaveFileName(
                self, "Save File", start_dir,
                "Python Files (*.py);;All Files (*)"
            )

            if path:
                editor.file_path = path
                self.tabs.setTabText(index, os.path.basename(path))
                ext = os.path.splitext(path)[1].lower()
                editor.highlighter = registry.get_highlighter(editor.document(), ext)
            else:
                return False

        try:
            code = editor.toPlainText()
            with open(editor.file_path, "w", encoding="utf-8") as f:
                f.write(code)

            editor.set_original_state(code)

            current_text = self.tabs.tabText(index)
            if current_text.endswith("*"):
                self.tabs.setTabText(index, current_text[:-1])

            if hasattr(self, 'git_dock'):
                self.git_dock.refresh_status()

            self.statusBar().showMessage(f"Saved: {editor.file_path}", 3000)
            return True
        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"Could not save file: {e}")
            return False

    def _save_current_session(self):
        """Save the current tab state for the current project."""
        tabs = []
        for i in range(self.tabs.count()):
            editor = self.tabs.widget(i)
            path = getattr(editor, 'file_path', None)
            cursor_pos = editor.textCursor().position() if editor else 0
            tabs.append((path, cursor_pos))
    
        project_path = None
        if hasattr(self, 'git_dock') and self.git_dock.repo_path:
            project_path = self.git_dock.repo_path
    
        save_session(tabs, self.tabs.currentIndex(), project_path)
                    
    def _restore_session(self, project_path=None):
        # If no project_path passed, try to infer from git dock
        if project_path is None and hasattr(self, 'git_dock') and self.git_dock.repo_path:
            project_path = self.git_dock.repo_path
    
        session = load_session(project_path)
    
        if not session or not session.get("tabs"):
            self.add_new_tab("Untitled", "")
            return
    
        # Restore project folder
        saved_project = session.get("project_path") or project_path
        if saved_project and os.path.isdir(saved_project):
            if hasattr(self, 'tree_view') and hasattr(self, 'file_model'):
                self.file_model.setRootPath(saved_project)
                self.tree_view.setRootIndex(self.file_model.index(saved_project))
            if hasattr(self, 'git_dock'):
                self.git_dock.repo_path = saved_project
                self.git_dock.refresh_status()
            if hasattr(self, 'memory_manager'):
                self.memory_manager.set_project(saved_project)
            if hasattr(self, 'update_git_branch'):
                self.update_git_branch()
    
        # Restore tabs
        restored = 0
        for tab_data in session.get("tabs", []):
            path = tab_data.get("path")
            cursor_pos = tab_data.get("cursor", 0)
    
            if not path or not os.path.exists(path):
                continue
    
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
    
                filename = os.path.basename(path)
                editor = self.add_new_tab(filename, content, path)
    
                cursor = editor.textCursor()
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

    def _close_all_tabs_for_switch(self):
        """Close all tabs without prompting — session was already saved."""
        while self.tabs.count() > 0:
            widget = self.tabs.widget(0)
            if widget:
                widget.deleteLater()
            self.tabs.removeTab(0)
            
    def _on_tab_changed(self, index):
        self.update_status_bar()
        self.update_git_branch()
        self._refresh_markdown_preview()
        editor = self.tabs.widget(index)
        if editor and hasattr(editor, 'file_path') and editor.file_path:
            self.intent_tracker.record_file_edit(editor.file_path)

    def _restore_conversation(self, user_message: str, ai_response: str):
        self.chat_panel.expand()
        self.chat_panel.chat_input.setFocus()
        self.chat_history.clear()
        self.current_ai_raw_text = ""
        self._ai_response_buffer = ""
    
        self._append_user_message(user_message)
        self.chat_history.insertHtml(self._render_ai_response(ai_response))
        self.chat_history.moveCursor(QTextCursor.MoveOperation.End)
        self.statusBar().showMessage(
            "Past conversation restored — send a message to continue it.", 5000
        )
    
    # -----------------------------
    # Cross-File Context Engine
    # -----------------------------
    
    def get_project_tree(self):
        root = self.file_model.filePath(self.tree_view.rootIndex())
        if not root or not os.path.isdir(root):
            return ""
        lines = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted([
                d for d in dirnames
                if not d.startswith('.')
                and d not in ('__pycache__', 'node_modules', '.git', 'venv', '.venv', 'dist', 'build')
            ])
            level = dirpath.replace(root, '').count(os.sep)
            indent = '  ' * level
            lines.append(f"{indent}{os.path.basename(dirpath)}/")
            for f in sorted(filenames):
                if not f.startswith('.') and not f.endswith(('.pyc', '.pyo')):
                    lines.append(f"{indent}  {f}")
        return "[Project Structure]\n" + "\n".join(lines)

    def get_open_tabs_context(self):
        context = []
        current_editor = self.current_editor()
        for i in range(self.tabs.count()):
            editor = self.tabs.widget(i)
            if not editor or not hasattr(editor, 'file_path'):
                continue
            if editor is current_editor:
                continue  # already sent as active file
            if not editor.file_path:
                continue
            content = editor.toPlainText()
            if not content.strip():
                continue
            # Keep head + tail of each tab so one huge file doesn't blow the context
            if len(content) > 1500:
                head = content[:500]
                tail = content[-1000:]
                content = head + "\n...(truncated)...\n" + tail
            rel_path = os.path.relpath(editor.file_path) if editor.file_path else "untitled"
            context.append(f"--- Open tab: {rel_path} ---\n```python\n{content}\n```")
        if not context:
            return ""
        return "[Other Open Files]\n" + "\n\n".join(context)

    def resolve_local_imports(self, code_text, _visited=None, _depth=0, _max_depth=3):
        if _visited is None:
            _visited = set()

        if _depth >= _max_depth:  # use _max_depth instead of hardcoded 3
            return ""

        editor = self.current_editor()
        if not editor:
            return ""

        try:
            tree = ast.parse(code_text)
        except Exception:
            return ""

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

                # Check project root first, then relative to current file
                candidate_paths = [
                    os.path.join(project_root, rel_path),
                ]
                if editor.file_path:
                    candidate_paths.append(
                        os.path.join(os.path.dirname(editor.file_path), rel_path)
                    )

                for full_path in candidate_paths:
                    full_path = os.path.normpath(full_path)

                    if not os.path.exists(full_path):
                        continue
                    if full_path in _visited:
                        continue

                    _visited.add(full_path)

                    try:
                        with open(full_path, 'r', encoding='utf-8') as f:
                            content = f.read()

                        display_path = os.path.relpath(full_path, project_root)

                        if len(content) > MAX_FILE_SIZE:
                            head = content[:500]
                            tail = content[-1000:]
                            content = head + "\n...(truncated)...\n" + tail

                        imported_context.append(
                            f"\n--- Imported file: {display_path} (depth {_depth + 1}) ---\n"
                            f"```python\n{content}\n```\n"
                        )

                        # Recurse into this file's imports
                        nested = self.resolve_local_imports(
                            content,
                            _visited=_visited,
                            _depth=_depth + 1
                        )
                        if nested:
                            imported_context.append(nested)

                    except Exception:
                        pass

                    break  # found it, don't check the other candidate path

        return "".join(imported_context)

    def setup_chat_panel(self):
        self.chat_panel = SlidingPanel(
            self.central_container,
            settings_manager=self.settings_manager
        )
        self.chat_panel.message_sent.connect(self._on_chat_message)
        self.chat_panel.show()
        self.chat_panel.raise_()
    
        self.chat_history = self.chat_panel.chat_history
        self.chat_input = self.chat_panel.chat_input
        self.chat_history.anchorClicked.connect(self.handle_chat_link)
    
        saved = self.memory_manager.load_chat_history()
        if saved:
            self.chat_history.setHtml(saved)
            self.chat_history.moveCursor(QTextCursor.MoveOperation.End)

    def _on_chat_message(self, user_text: str):
        self._append_user_message(user_text)
    
        editor = self.current_editor()
        active_code = editor.toPlainText() if editor else ""
        context = self.build_chat_context(user_text, active_code)
        prompt_with_context = f"{user_text}\n\n{context}"
    
        self._ai_response_buffer = ""
        self.current_ai_raw_text = ""
    
        thread = QThread()
        self.chat_worker = self.create_worker(
            prompt=prompt_with_context,
            is_chat=True,
        )
        self.chat_worker.moveToThread(thread)
        self.chat_worker.chat_update.connect(self.append_chat_stream)
        self.chat_worker.finished.connect(self.chat_stream_finished)
        self.chat_worker.finished.connect(thread.quit)
        self.chat_worker.finished.connect(self.chat_worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        self.show_loading_indicator()
        self.chat_worker.finished.connect(self.hide_loading_indicator)
        self.active_threads.append(thread)
        thread.finished.connect(
            lambda: self.active_threads.remove(thread)
            if thread in self.active_threads else None
        )
        thread.started.connect(self.chat_worker.run)
        thread.start()

    def send_chat_message(self):
        user_text = self.chat_input.toPlainText().strip()
        if not user_text: return
        self.chat_input.clear()
    
        # Render user message as HTML bubble
        self._append_user_message(user_text)
    
        editor = self.current_editor()
        active_code = editor.toPlainText() if editor else ""
        context = self.build_chat_context(user_text, active_code)
        prompt_with_context = f"{user_text}\n\n{context}"
    
        # Start AI response placeholder
        self._ai_response_buffer = ""
        self.current_ai_raw_text = ""
    
        thread = QThread()
        self.chat_worker = self.create_worker(
            prompt=prompt_with_context,
            is_chat=True,
        )
        self.chat_worker.moveToThread(thread)
        self.chat_worker.chat_update.connect(self.append_chat_stream)
        self.chat_worker.finished.connect(self.chat_stream_finished)
        self.chat_worker.finished.connect(thread.quit)
        self.chat_worker.finished.connect(self.chat_worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        self.show_loading_indicator()
        self.chat_worker.finished.connect(self.hide_loading_indicator)
        self.active_threads.append(thread)
        thread.finished.connect(
            lambda: self.active_threads.remove(thread)
            if thread in self.active_threads else None
        )
        thread.started.connect(self.chat_worker.run)
        thread.start()
    
    def _append_user_message(self, text: str):
        escaped = (text.replace("&", "&amp;")
                       .replace("<", "&lt;")
                       .replace(">", "&gt;")
                       .replace("\n", "<br>"))
    
        html = (
            # Right-aligned user bubble
            f'<table width="100%" cellpadding="0" cellspacing="0" '
            f'style="margin:8px 0;">'
            f'<tr><td width="10%"></td>'
            f'<td width="90%" align="right">'
            f'<table cellpadding="0" cellspacing="0" align="right">'
            f'<tr><td style="background-color:#0E639C; border-radius:18px 18px 4px 18px; '
            f'padding:10px 14px; color:#FFFFFF; '
            f'font-family:Inter,sans-serif; font-size:10pt; '
            f'line-height:1.5;">{escaped}</td></tr>'
            f'<tr><td align="right" style="padding:2px 4px 8px 0; '
            f'color:#555555; font-size:8pt; '
            f'font-family:Inter,sans-serif;">You</td></tr>'
            f'</table></td></tr></table>'
    
            # Left-aligned QuillAI label ready for streaming
            f'<table width="100%" cellpadding="0" cellspacing="0">'
            f'<tr><td width="90%">'
            f'<table cellpadding="0" cellspacing="0">'
            f'<tr><td style="padding:2px 0 4px 4px; color:#8A2BE2; '
            f'font-size:8pt; font-family:Inter,sans-serif; '
            f'font-weight:bold;">QuillAI</td></tr>'
            f'<tr><td style="background-color:#252526; '
            f'border-radius:8px 18px 18px 18px; '
            f'padding:10px 14px; color:#D4D4D4; '
            f'font-family:Inter,sans-serif; font-size:10pt; '
            f'line-height:1.5;" id="streaming"> </td></tr>'
            f'</table></td><td width="20%"></td></tr></table>'
        )
    
        self.chat_history.moveCursor(QTextCursor.MoveOperation.End)
        self.chat_history.insertHtml(html)
        self.chat_history.ensureCursorVisible()
    
    def append_chat_stream(self, text):
        self.current_ai_raw_text += text
        self.chat_history.moveCursor(QTextCursor.MoveOperation.End)
        self.chat_history.insertPlainText(text)
        self.chat_history.ensureCursorVisible()
    
    def chat_stream_finished(self):
        full_response = self.current_ai_raw_text
    
        # Remove the streamed plain text placeholder
        full_plain = self.chat_history.toPlainText()
        last_quillai = full_plain.rfind("QuillAI")
        if last_quillai >= 0:
            cursor = self.chat_history.textCursor()
            cursor.setPosition(last_quillai + len("QuillAI"))
            cursor.movePosition(QTextCursor.MoveOperation.End,
                                QTextCursor.MoveMode.KeepAnchor)
            cursor.removeSelectedText()
            self.chat_history.setTextCursor(cursor)
    
        # Insert the properly rendered bubble
        rendered = self._render_ai_response(full_response)
        self.chat_history.moveCursor(QTextCursor.MoveOperation.End)
        self.chat_history.insertHtml(rendered)
        self.chat_history.moveCursor(QTextCursor.MoveOperation.End)
        self.chat_history.ensureCursorVisible()
    
        if full_response.strip():
            self._summarize_conversation_to_memory(full_response)
    
        self.memory_manager.save_chat_history(self.chat_history.toHtml())

        self.current_ai_raw_text = ""
        self._ai_response_buffer = ""
    
    def _render_markdown_text(self, text: str) -> str:
        """Convert markdown text to HTML for display in chat bubbles."""
        import re
    
        lines = text.split('\n')
        html_lines = []
        in_list = False
    
        for line in lines:
            stripped = line.strip()
    
            # Bullet points — -, *, +
            if re.match(r'^[-*+]\s+', stripped):
                if not in_list:
                    html_lines.append('<ul style="margin:4px 0 4px 16px; padding:0;">')
                    in_list = True
                content = re.sub(r'^[-*+]\s+', '', stripped)
                content = self._apply_inline_markdown(content)
                html_lines.append(
                    f'<li style="color:#D4D4D4; font-family:Hack,JetBrains Mono,'
                    f'monospace; font-size:10pt; line-height:1.8; '
                    f'margin:2px 0;">{content}</li>'
                )
                continue
    
            # Numbered list
            if re.match(r'^\d+\.\s+', stripped):
                if not in_list:
                    html_lines.append('<ol style="margin:4px 0 4px 16px; padding:0;">')
                    in_list = True
                content = re.sub(r'^\d+\.\s+', '', stripped)
                content = self._apply_inline_markdown(content)
                html_lines.append(
                    f'<li style="color:#D4D4D4; font-family:Hack,JetBrains Mono,'
                    f'monospace; font-size:10pt; line-height:1.8; '
                    f'margin:2px 0;">{content}</li>'
                )
                continue
    
            # Close list if we hit a non-list line
            if in_list:
                html_lines.append('</ul>' if not re.match(r'^\d+', stripped) else '</ol>')
                in_list = False
    
            # Headings
            if re.match(r'^#{1,3}\s', stripped):
                level = len(re.match(r'^(#+)', stripped).group(1))
                content = re.sub(r'^#+\s+', '', stripped)
                sizes = {1: '14pt', 2: '12pt', 3: '11pt'}
                html_lines.append(
                    f'<p style="margin:10px 0 4px 0; color:#569CD6; '
                    f'font-weight:bold; font-family:Hack,JetBrains Mono,monospace; '
                    f'font-size:{sizes.get(level, "11pt")};">'
                    f'{self._apply_inline_markdown(content)}</p>'
                )
                continue
    
            # Horizontal rule
            if re.match(r'^[-*_]{3,}\s*$', stripped):
                html_lines.append(
                    '<hr style="border:none; border-top:1px solid #3E3E42; '
                    'margin:8px 0;"/>'
                )
                continue
    
            # Blank line
            if not stripped:
                html_lines.append('<p style="margin:4px 0;">&nbsp;</p>')
                continue
    
            # Normal paragraph
            content = self._apply_inline_markdown(stripped)
            html_lines.append(
                f'<p style="margin:2px 0; color:#D4D4D4; '
                f'font-family:Hack,JetBrains Mono,monospace; '
                f'font-size:10pt; line-height:1.8;">{content}</p>'
            )
    
        if in_list:
            html_lines.append('</ul>')
    
        return ''.join(html_lines)
    
    def _apply_inline_markdown(self, text: str) -> str:
        """Apply inline markdown — bold, italic, inline code."""
        import re
        # Inline code
        text = re.sub(
            r'`([^`]+)`',
            r'<code style="background:#2A2A2D;color:#CE9178;'
            r'padding:1px 5px;border-radius:3px;'
            r'font-family:Hack,JetBrains Mono,monospace;font-size:9pt;">'
            r'\1</code>',
            text
        )
        # Bold
        text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
        text = re.sub(r'__(.+?)__',     r'<strong>\1</strong>', text)
        # Italic
        text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
        text = re.sub(r'_(.+?)_',   r'<em>\1</em>', text)
        return text
    
    def _render_ai_response(self, text: str) -> str:
        import re
    
        parts = re.split(r'(```(?:[\w]*)\n.*?```)', text, flags=re.DOTALL)
        html_parts = []
    
        for part in parts:
            if part.startswith('```'):
                lang_match = re.match(r'```([\w]*)\n?', part)
                lang = lang_match.group(1).lower() if lang_match else ""
                code = re.sub(r'^```[\w]*\n?', '', part)
                code = re.sub(r'\n?```$', '', code)
            
                highlighted = self._highlight_code_block(code, lang)
            
                # Encode code for the copy link
                import base64
                encoded = base64.b64encode(code.encode('utf-8')).decode('utf-8')
                lang_label = lang.upper() if lang else "CODE"
            
                html_parts.append(
                    f'<table width="100%" cellpadding="0" cellspacing="0" '
                    f'style="margin:8px 0;">'
                    f'<tr><td style="background-color:#2A2A2D; '
                    f'border-radius:12px 12px 0 0; '
                    f'padding:4px 12px;">'
                    f'<span style="color:#888888; font-family:Hack,monospace; '
                    f'font-size:8pt;">{lang_label}</span>'
                    f'&nbsp;&nbsp;'
                    f'<a href="copy:{encoded}" style="color:#569CD6; '
                    f'font-family:Hack,monospace; font-size:8pt; '
                    f'text-decoration:none;">⎘ Copy</a>'
                    f'</td></tr>'
                    f'<tr><td style="background-color:#1A1A1C; '
                    f'border:1px solid #3E3E42; border-radius:0 0 12px 12px; '
                    f'padding:12px 16px;">'
                    f'<pre style="margin:0; '
                    f'font-family:Hack,JetBrains Mono,Courier New,monospace; '
                    f'font-size:10pt; line-height:1.8; white-space:pre; '
                    f'color:#D4D4D4;">{highlighted}</pre>'
                    f'</td></tr></table>'
                )
            else:
                if not part.strip():
                    continue
                # Escape HTML before markdown processing
                escaped = (part.replace("&", "&amp;")
                              .replace("<", "&lt;")
                              .replace(">", "&gt;"))
                html_parts.append(self._render_markdown_text(escaped))
    
        inner = ''.join(html_parts)
        return (
            f'<table width="100%" cellpadding="0" cellspacing="0" '
            f'style="margin:0 0 16px 0;">'
            f'<tr>'
            f'<td width="80%" valign="top">'
            f'<table cellpadding="0" cellspacing="0" width="100%">'
            f'<tr><td style="background-color:#252526; '
            f'border-radius:4px 18px 18px 18px; '
            f'padding:12px 16px;">{inner}</td></tr>'
            f'</table></td>'
            f'<td width="20%"></td>'
            f'</tr></table>'
        )

    def _highlight_code_block(self, code: str, lang: str = "") -> str:
        """
        Apply syntax highlighting to a code block by injecting
        inline HTML span tags. Works inside QTextBrowser.
        """
        import re
    
        escaped = (code.replace("&", "&amp;")
                       .replace("<", "&lt;")
                       .replace(">", "&gt;"))
    
        # Detect language if not specified
        if not lang:
            if re.search(r'\bdef \w+|import \w+|class \w+:', escaped):
                lang = "python"
            elif re.search(r'\bfunction\b|\bconst\b|\blet\b|\bvar\b', escaped):
                lang = "javascript"
            elif re.search(r'^\s*-\s+\w+:|hosts:|tasks:', escaped, re.MULTILINE):
                lang = "yaml"
            elif re.search(r'#!/.*bash|echo\b|\bfi\b|\bdone\b', escaped):
                lang = "bash"
            elif re.search(r'nixpkgs|mkShell|buildInputs', escaped):
                lang = "nix"
    
        if lang in ("python", "py"):
            keywords = (r'\b(def|class|import|from|return|if|elif|else|for|while|'
                        r'in|and|or|not|True|False|None|pass|try|except|with|as|'
                        r'async|await|lambda|yield|raise|break|continue|global|'
                        r'nonlocal|del|assert|is)\b')
            builtins = (r'\b(print|len|range|str|int|float|list|dict|set|tuple|'
                        r'bool|type|isinstance|hasattr|getattr|setattr|open|'
                        r'enumerate|zip|map|filter|any|all|sum|min|max|abs|'
                        r'round|sorted|reversed|super|self)\b')
    
            # Order matters — process strings and comments first to avoid
            # highlighting keywords inside them
    
            # Protect strings first by replacing with placeholders
            string_map = {}
            counter = [0]
    
            def protect_string(m):
                key = f"\x00STR{counter[0]}\x00"
                counter[0] += 1
                content = m.group(0)
                colored = (f'<span style="color:#E6DB74;">{content}</span>')
                string_map[key] = colored
                return key
    
            # Triple quoted strings
            escaped = re.sub(r'""".*?"""|\'\'\'.*?\'\'\'',
                             protect_string, escaped, flags=re.DOTALL)
            # Single quoted strings
            escaped = re.sub(r'"[^"\n]*"|\'[^\'\n]*\'',
                             protect_string, escaped)
    
            # Comments
            def protect_comment(m):
                key = f"\x00CMT{counter[0]}\x00"
                counter[0] += 1
                string_map[key] = f'<span style="color:#75715E;font-style:italic;">{m.group(0)}</span>'
                return key
    
            escaped = re.sub(r'#[^\n]*', protect_comment, escaped)
    
            # Decorators
            escaped = re.sub(
                r'(@\w+)',
                r'<span style="color:#A6E22E;">\1</span>',
                escaped
            )
    
            # Keywords
            escaped = re.sub(
                keywords,
                r'<span style="color:#F92672;font-weight:bold;">\1</span>',
                escaped
            )
    
            # Builtins
            escaped = re.sub(
                builtins,
                r'<span style="color:#66D9EF;font-style:italic;">\1</span>',
                escaped
            )
    
            # Numbers
            escaped = re.sub(
                r'\b(\d+\.?\d*)\b',
                r'<span style="color:#AE81FF;">\1</span>',
                escaped
            )
    
            # Function/class definitions — highlight the name
            escaped = re.sub(
                r'(def|class)\s+(<span[^>]*>)?(\w+)',
                lambda m: f'{m.group(1)} <span style="color:#A6E22E;font-weight:bold;">{m.group(3)}</span>',
                escaped
            )
    
            # Restore protected strings and comments
            for key, value in string_map.items():
                escaped = escaped.replace(key, value)
    
        elif lang in ("javascript", "js", "typescript", "ts"):
            keywords = (r'\b(function|const|let|var|return|if|else|for|while|'
                        r'class|import|export|from|new|this|typeof|instanceof|'
                        r'async|await|try|catch|throw|true|false|null|undefined|'
                        r'switch|case|break|continue|default|of|in)\b')
            escaped = re.sub(r'"[^"\n]*"|\'[^\'\n]*\'|`[^`]*`',
                             lambda m: f'<span style="color:#E6DB74;">{m.group(0)}</span>',
                             escaped)
            escaped = re.sub(r'//[^\n]*',
                             lambda m: f'<span style="color:#75715E;font-style:italic;">{m.group(0)}</span>',
                             escaped)
            escaped = re.sub(keywords,
                             r'<span style="color:#F92672;font-weight:bold;">\1</span>',
                             escaped)
            escaped = re.sub(r'\b(\d+\.?\d*)\b',
                             r'<span style="color:#AE81FF;">\1</span>', escaped)
    
        elif lang in ("bash", "sh"):
            escaped = re.sub(r'#[^\n]*',
                             lambda m: f'<span style="color:#75715E;font-style:italic;">{m.group(0)}</span>',
                             escaped)
            escaped = re.sub(r'"[^"\n]*"|\'[^\'\n]*\'',
                             lambda m: f'<span style="color:#E6DB74;">{m.group(0)}</span>',
                             escaped)
            escaped = re.sub(r'\$\{?\w+\}?',
                             lambda m: f'<span style="color:#AE81FF;">{m.group(0)}</span>',
                             escaped)
            escaped = re.sub(
                r'\b(if|then|else|elif|fi|for|while|do|done|case|esac|'
                r'function|return|export|local|echo|source)\b',
                r'<span style="color:#F92672;font-weight:bold;">\1</span>',
                escaped
            )
    
        elif lang in ("yaml", "yml", "ansible"):
            lines = escaped.split('\n')
            result = []
            for line in lines:
                # Keys
                line = re.sub(
                    r'^(\s*)(\w[\w\s]*?)(:)',
                    r'\1<span style="color:#66D9EF;">\2</span>\3',
                    line
                )
                # Comments
                line = re.sub(
                    r'(#[^\n]*)',
                    r'<span style="color:#75715E;font-style:italic;">\1</span>',
                    line
                )
                # Values that are strings
                line = re.sub(
                    r':\s*(["\'].*?["\'])',
                    lambda m: f': <span style="color:#E6DB74;">{m.group(1)}</span>',
                    line
                )
                result.append(line)
            escaped = '\n'.join(result)
    
        elif lang in ("nix",):
            escaped = re.sub(r'#[^\n]*',
                             lambda m: f'<span style="color:#75715E;font-style:italic;">{m.group(0)}</span>',
                             escaped)
            escaped = re.sub(r'"[^"\n]*"',
                             lambda m: f'<span style="color:#E6DB74;">{m.group(0)}</span>',
                             escaped)
            escaped = re.sub(
                r'\b(let|in|with|rec|if|then|else|import|inherit|true|false|null)\b',
                r'<span style="color:#F92672;font-weight:bold;">\1</span>',
                escaped
            )
    
        return escaped   
           
    def setup_memory_panel(self):
        self.memory_panel = MemoryPanel(self.memory_manager, self)
        self.memory_panel.restore_conversation_requested.connect(
            self._restore_conversation
        )
        # Inject into the sliding panel's memory tab
        self.chat_panel.set_memory_widget(self.memory_panel)

    # ==========================================
    # The Two-Way Bridge Methods
    # ==========================================
    def load_snippet_to_chat(self, text):
        self.chat_panel.expand()
        self.chat_panel.chat_input.setFocus()
        current_input = self.chat_input.toPlainText()
        new_text = f"```python\n{text}\n```\n"

        if current_input.strip():
            final_text = current_input + "\n\n" + new_text
        else:
            final_text = new_text

        self.chat_input.setPlainText(final_text)
        self.chat_input.setFocus()

        cursor = self.chat_input.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.chat_input.setTextCursor(cursor)
     
    def _summarize_conversation_to_memory(self, ai_response: str):
        try:
            last_user = ""
            text = self.chat_history.toPlainText()
            lines = text.strip().split('\n')
    
            for i in range(len(lines) - 1, -1, -1):
                line = lines[i]
                if line.startswith("You:"):
                    inline = line.replace("You:", "").strip()
                    if inline:
                        last_user = inline
                    elif i + 1 < len(lines) and lines[i + 1].strip():
                        last_user = lines[i + 1].strip()
                    break
    
            if not last_user:
                return
    
            # Auto-extract facts
            extracted = self.memory_manager.extract_facts_from_exchange(
                last_user, ai_response
            )
            for fact in extracted:
                self.memory_manager.add_fact(fact, project_scoped=False)
            if extracted and hasattr(self, 'memory_panel'):
                self.memory_panel.refresh()
    
            # Record for intent tracking
            self.intent_tracker.record_chat_exchange(last_user, ai_response[:500])
    
            # Save full exchange so it can be restored later
            summary = last_user[:80] + ("..." if len(last_user) > 80 else "")
            self.memory_manager.add_conversation(
                summary=summary,
                user_message=last_user,
                ai_response=ai_response[:2000],
            )
            if hasattr(self, 'memory_panel'):
                self.memory_panel.refresh()
    
        except Exception as e:
            import traceback
            print(f"_summarize_conversation_to_memory error: {e}")
            traceback.print_exc()
        
            def on_finished():
                try:
                    summary = "".join(summary_buf).strip()
                    print(f"DEBUG on_finished: summary='{summary}'")
                    if summary:
                        self.memory_manager.add_conversation(summary)
                    if hasattr(self, 'memory_panel'):
                        self.memory_panel.refresh()
                except Exception as e:
                    import traceback
                    print(f"DEBUG on_finished error: {e}")
                    traceback.print_exc()

            worker.finished.connect(on_finished)
            worker.finished.connect(thread.quit)
            worker.finished.connect(worker.deleteLater)
            thread.finished.connect(thread.deleteLater)
            self.active_threads.append(thread)
            thread.finished.connect(
                lambda: self.active_threads.remove(thread)
                if thread in self.active_threads else None
            )
            thread.started.connect(worker.run)
            thread.start()
    
        except Exception as e:
            import traceback
            traceback.print_exc()

    def handle_chat_link(self, url: QUrl):
        url_str = url.toString()
        
        if url_str.startswith("insert:"):
            encoded_code = url_str.replace("insert:", "")
            decoded_code = base64.b64decode(encoded_code).decode('utf-8')
            editor = self.current_editor()
            if editor:
                editor.textCursor().insertText(decoded_code)
                editor.setFocus()
    
        elif url_str.startswith("copy:"):
            encoded_code = url_str.replace("copy:", "")
            decoded_code = base64.b64decode(encoded_code).decode('utf-8')
            QApplication.clipboard().setText(decoded_code)
            self.statusBar().showMessage("Code copied to clipboard.", 2000)
    # -----------------------------
    # Runner Methods
    # -----------------------------
    def setup_run_menu(self):
        run_menu = self.menuBar().addMenu("Run")
        run_action = QAction("Run Script", self)
        run_action.setShortcut(QKeySequence("F5"))
        run_action.triggered.connect(self.run_script)
        run_menu.addAction(run_action)

    def setup_view_menu(self):
        view_menu = self.menuBar().addMenu("View")
    
        panels = [
            ("Chat",            lambda: self.chat_panel.switch_to_chat()),
            ("Memory",          lambda: self.chat_panel.switch_to_memory()),
            ("Markdown Preview",lambda: self.chat_panel.switch_to_preview()),
            ("Explorer",        lambda: (self.sidebar_dock.show(), self.sidebar_dock.raise_())),
            ("Source Control",  lambda: (self.git_dock.show(),     self.git_dock.raise_())),
            ("Output",          lambda: (self.output_dock.show(),  self.output_dock.raise_())),
            ("Find in Files",   lambda: (self.search_dock.show(),  self.search_dock.raise_())),
        ]
    
        for name, fn in panels:
            action = QAction(name, self)
            action.triggered.connect(fn)
            view_menu.addAction(action)
        
        toggle_completion_action = QAction("Toggle In-line Completion", self)
        toggle_completion_action.setCheckable(True)
        toggle_completion_action.setChecked(True) 
        toggle_completion_action.toggled.connect(self.toggle_inline_completion)
        view_menu.addAction(toggle_completion_action)

    def setup_output_panel(self):
        output_container = QWidget()
        layout = QVBoxLayout(output_container)
        layout.setContentsMargins(0, 0, 0, 0)

        self.output_editor = QPlainTextEdit()
        self.output_editor.setReadOnly(True)
        self.output_editor.setStyleSheet("QPlainTextEdit { background-color: #1E1E1E; color: #CCCCCC; font-family: 'JetBrains Mono', monospace; font-size: 10pt; border: none; }")

        self.explain_error_btn = QPushButton("💡 Explain Error")
        self.explain_error_btn.setStyleSheet("""
            QPushButton {
                background-color: #8A2BE2;
                color: white;
                border: none;
                padding: 6px 12px;
                border-radius: 4px;
                font-family: 'Inter', 'SF Pro Text', 'Segoe UI', sans-serif;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #9B30FF; }
        """)
        self.explain_error_btn.hide()
        self.explain_error_btn.clicked.connect(self.explain_error)

        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(5, 5, 5, 5)
        btn_layout.addStretch()
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

            index = self.tabs.indexOf(editor)
            current_text = self.tabs.tabText(index)
            if current_text.endswith("*"):
                self.tabs.setTabText(index, current_text[:-1])

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

        self.current_error_text += stderr
        self.explain_error_btn.show()

    def explain_error(self):
        if not self.current_error_text.strip():
            return

        self.chat_panel.expand()
        self.chat_panel.chat_input.setFocus()
        self.explain_error_btn.hide()

        user_text = "My script crashed with an error. Can you explain what went wrong and how to fix it?"

        self.chat_history.moveCursor(QTextCursor.MoveOperation.End)
        self.chat_history.insertPlainText(f"You: {user_text}\n\n[Error Trace Sent]\n\nQuillAI: ")
        self.chat_history.ensureCursorVisible()

        editor = self.current_editor()
        active_code = editor.toPlainText() if editor else ""
        cross_file_context = self.resolve_local_imports(active_code)

        if len(active_code) > 2000:
            active_code = "...(truncated)...\n" + active_code[-2000:]

        if len(cross_file_context) > 2000:
            cross_file_context = "...(truncated)...\n" + cross_file_context[-2000:]

        open_tabs_context = self.get_open_tabs_context()
        project_tree = self.get_project_tree()

        context = self.build_chat_context(user_text, active_code)
        prompt_with_context = f"""
        {user_text}

        [Error Trace]
        {self.current_error_text[:8000]}

        {context}

        Instructions:
        - Explain the error clearly
        - Identify the root cause  
        - Show how to fix it
        - Include corrected code if possible
        """

        thread = QThread()

        self.chat_worker = self.create_worker(
            prompt=prompt_with_context,
            is_chat=True,
        )
        self.chat_worker.moveToThread(thread)
        self.chat_worker.chat_update.connect(self.append_chat_stream)
        self.chat_worker.finished.connect(self.chat_stream_finished)
        self.chat_worker.finished.connect(thread.quit)
        self.chat_worker.finished.connect(self.chat_worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        self.show_loading_indicator()
        self.chat_worker.finished.connect(self.hide_loading_indicator)
        self.active_threads.append(thread)
        thread.finished.connect(lambda: self.active_threads.remove(thread) if thread in self.active_threads else None)
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
        index = self.tabs.currentIndex()
        if index >= 0:
            title = self.tabs.tabText(index)
            if not title.startswith("⟳ "):
                self.tabs.setTabText(index, "⟳ " + title)
    
    def hide_loading_indicator(self):
        for i in range(self.tabs.count()):
            title = self.tabs.tabText(i)
            if title.startswith("⟳ "):
                self.tabs.setTabText(i, title[2:])

    def on_text_changed(self):
        editor = self.current_editor()

        if not editor or getattr(self, '_is_loading', False) or editor.function_active or not editor.hasFocus():
            return

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
        if not self.inline_completion_enabled:
            return
        if not editor or not editor.hasFocus():
            return
    
        cursor = editor.textCursor()
        line_text = cursor.block().text()
    
        generate_function = False
        if line_text.strip().startswith("#") and "function" in line_text.lower():
            generate_function = True
    
        if line_text.strip().endswith(":") or line_text.strip().endswith(")"):
            return
    
        text = editor.toPlainText()
        cursor_pos = int(cursor.position())
        context = text[max(0, cursor_pos - 1500):cursor_pos]
        cross_file_context = self.resolve_local_imports(text)
    
        # Detect language for intent context
        lang = "code"
        if editor.file_path:
            ext_map = {
                '.py': 'Python', '.sh': 'Bash', '.bash': 'Bash',
                '.yml': 'YAML', '.yaml': 'YAML', '.nix': 'Nix',
                '.html': 'HTML', '.js': 'JavaScript', '.ts': 'TypeScript',
            }
            for ext, name in ext_map.items():
                if editor.file_path.lower().endswith(ext):
                    lang = name
                    break
    
        # Record current symbol for intent tracking
        current_symbol = self.intent_tracker.get_current_symbol(text, cursor_pos)
        if current_symbol:
            self.intent_tracker.record_cursor_symbol(current_symbol)
    
        # Build intent prefix — cached, nearly free on repeated calls
        intent_ctx = self.intent_tracker.build_intent_context(
            current_file_path=editor.file_path or "",
            language=lang,
        )
    
        if generate_function:
            prompt = (
                f"{intent_ctx}\n"
                f"Generate a {lang} function for this comment:\n"
                f"{line_text}\n"
                f"{cross_file_context}\n"
                f"Return ONLY code. Do not repeat the comment."
            )
        else:
            prompt = (
                f"{intent_ctx}\n"
                f"{cross_file_context}\n"
                f"Complete the following {lang} code:\n\n{context}"
            )
    
        thread = QThread()
        worker = self.create_worker(
            prompt=prompt,
            editor_text=text,
            cursor_pos=cursor_pos,
            generate_function=generate_function,
        )
    
        worker.moveToThread(thread)
        worker.update_ghost.connect(editor.set_ghost_text)
        worker.function_ready.connect(editor.handle_function_output)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
    
        self.last_worker = worker
        self.active_threads.append(thread)
        thread.finished.connect(
            lambda: self.active_threads.remove(thread)
            if thread in self.active_threads else None
        )
        thread.started.connect(worker.run)
        thread.start()
        
if __name__ == "__main__":
    app = QApplication(sys.argv)

    # ==========================================
    # Global Modern IDE Stylesheet
    # ==========================================
    app.setStyleSheet("""
        QWidget {
            background-color: #1E1E1E;
            color: #D4D4D4;
        }

        QSplitter::handle {
            background-color: #333333;
            margin: 0px;
        }
        QSplitter::handle:horizontal {
            width: 1px;
        }
        QSplitter::handle:vertical {
            height: 1px;
        }

        QSplitter::handle:hover {
            background-color: #007ACC;
        }

        QScrollBar:vertical {
            border: none;
            background: transparent;
            width: 14px;
            margin: 0px;
        }
        QScrollBar::handle:vertical {
            background: #424242;
            min-height: 30px;
            border-radius: 7px;
            margin: 2px 3px 2px 3px;
        }
        QScrollBar::handle:vertical:hover {
            background: #4F4F4F;
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            height: 0px;
        }
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
            background: none;
        }

        QScrollBar:horizontal {
            border: none;
            background: transparent;
            height: 14px;
            margin: 0px;
        }
        QScrollBar::handle:horizontal {
            background: #424242;
            min-width: 30px;
            border-radius: 7px;
            margin: 3px 2px 3px 2px;
        }
        QScrollBar::handle:horizontal:hover {
            background: #4F4F4F;
        }
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
            width: 0px;
        }
        QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
            background: none;
        }

        QLineEdit, QTextEdit {
            background-color: #252526;
            border: 1px solid #3E3E42;
            border-radius: 4px;
            padding: 5px 8px;
            color: #CCCCCC;
            selection-background-color: #264F78;
        }
        QLineEdit:focus, QTextEdit:focus {
            border: 1px solid #007ACC;
        }

        QTreeView, QListView {
            background-color: #1E1E1E;
            border: none;
            outline: none;
        }
        QTreeView::item, QListView::item {
            padding: 4px;
            border-radius: 4px;
        }
        QTreeView::item:selected, QListView::item:selected {
            background-color: #37373D;
            color: #FFFFFF;
        }
        QTreeView::item:hover:!selected, QListView::item:hover:!selected {
            background-color: #2A2D2E;
        }

        QPushButton {
            background-color: #0E639C;
            color: white;
            border: none;
            border-radius: 4px;
            padding: 6px 14px;
            font-weight: bold;
        }
        QPushButton:hover {
            background-color: #1177BB;
        }
        QPushButton:pressed {
            background-color: #094771;
        }
        QPushButton:disabled {
            background-color: #333333;
            color: #888888;
        }
    """)

    window = CodeEditor()
    window.resize(1000, 700)
    window.show()
    sys.exit(app.exec())
