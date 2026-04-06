import sys
import os
import tempfile
import ast
import re
import base64
import threading
from pathlib import Path                                            # ← WIKI


from PyQt6.QtWidgets import (QApplication, QMainWindow, QProgressBar, QLabel,
                             QDockWidget, QTreeView, QPlainTextEdit, QTextEdit,
                             QVBoxLayout, QWidget, QLineEdit, QTabWidget,
                             QPushButton, QHBoxLayout, QMessageBox, QFileDialog,
                             QTextBrowser, QSizePolicy, QSplitter)
from PyQt6.QtCore import QTimer, QThread, Qt, QDir, QProcess, QUrl, pyqtSlot
from PyQt6.QtGui import (QFileSystemModel, QAction, QKeySequence, QTextCursor,
                         QIcon, QPixmap, QPainter, QColor, QShortcut,
                         QSyntaxHighlighter, QTextCharFormat, QFont)
                         
from core.plugin_manager import PluginManager
from core.wiki_manager import WikiManager                
from core.wiki_watcher import WikiWatcher                
from core.wiki_context_builder import WikiContextBuilder 

from editor.ghost_editor import GhostEditor
from ai.worker import AIWorker
from ai.context_engine import ContextEngine
from ai.lsp_manager import LSPManager
from ai.lsp_context import LSPContextProvider
from ai.repo_map import RepoMap
from ai.vector_index import VectorIndex

from ui.theme import (apply_theme, get_theme, theme_signals,
                      build_status_bar_stylesheet,
                      build_editor_stylesheet,
                      build_dock_stylesheet,
                      build_tab_widget_stylesheet,
                      build_output_panel_stylesheet,
                      build_explain_error_btn_stylesheet,
                      build_tree_view_stylesheet)

from ui.menu import setup_menus
from ui.about_dialog import AboutDialog
from ui.find_replace import FindReplaceWidget
from ui.find_in_files import FindInFilesWidget
from ui.settings_manager import SettingsManager
from ui.settings_dialog import SettingsDialog
from ui.chat_renderer import ChatRenderer
from ui.memory_manager import MemoryManager
from ui.memory_panel import MemoryPanel
from ui.session_manager import save_session, load_session
from ui.session_intent import init_tracker
from ui.sliding_chat_panel import SlidingPanel
from ui.command_palette import CommandPalette
from ui.startup_progress import StartupProgress
from ui.autosave_manager import AutosaveManager, AUTOSAVE_INTERVAL_MS
from ui.split_container import SplitContainer, EditorPane

from editor.highlighter import registry
from ui.git_panel import GitDockWidget

MAX_FILE_SIZE = 6000  # characters


# ==========================================
# Custom File System Model
# ==========================================

class CustomFileSystemModel(QFileSystemModel):
    def __init__(self, theme_name: str = None):
        super().__init__()
        t = get_theme(theme_name)
        self._rebuild_icons(t)

    def _rebuild_icons(self, t: dict):
        bg = t['bg0_hard']
        self.folder_icon = self._create_icon(t['yellow'], bg,  is_folder=True)
        self.file_icon   = self._create_icon(t['fg4'],    bg,  is_folder=False)
        self.py_icon     = self._create_icon(t['blue'],   bg,  is_folder=False)
        self.html_icon   = self._create_icon(t['orange'], bg,  is_folder=False)

    @staticmethod
    def _create_icon(color: str, bg_hard: str, is_folder: bool) -> QIcon:
        """Pure function — no theme lookup, all colors passed explicitly."""
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
            painter.setBrush(QColor(bg_hard))
            painter.drawRect(5, 5, 6, 1)
            painter.drawRect(5, 8, 6, 1)
            painter.drawRect(5, 11, 4, 1)
        painter.end()
        return QIcon(pixmap)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DecorationRole:
            if self.isDir(index):
                return self.folder_icon
            filename = self.fileName(index).lower()
            if filename.endswith(".py"):
                return self.py_icon
            elif filename.endswith((".html", ".htm")):
                return self.html_icon
            return self.file_icon
        return super().data(index, role)


# ==========================================
# Main Application
# ==========================================

class CodeEditor(QMainWindow, ChatRenderer):
    def __init__(self):
        super().__init__()

        # 1. Load settings FIRST
        self.settings_manager = SettingsManager()

        # 2. Load memory
        self.memory_manager = MemoryManager()
        self.intent_tracker = init_tracker(self.memory_manager)
        
        # 3. LSP (graceful — works fine if pylsp not installed)
        self.lsp_manager = None
        self.lsp_context_provider = None
        self._start_lsp()
        self.vector_index = None
        self.repo_map = None
        # Built after session restore when the project root is known

        # 4. Basic App State
        self.setWindowTitle("QuillAI")
        try:
            icon_path = os.path.join(
                os.path.dirname(__file__), 'images', 'quillai_logo_min.svg'
            )
            if os.path.exists(icon_path):
                self.setWindowIcon(QIcon(icon_path))
        except Exception:
            pass

        self._is_loading = False
        self.inline_completion_enabled = True
        self.current_error_text = ""
        self.current_ai_raw_text = ""
        self._stream_start_pos = 0
        self._stream_buffer = ""
        self._ai_response_buffer = ""
        self._last_user_message = ""
        self.last_worker = None
        self.chat_worker = None
        self.active_threads = []
        
        # Autosave / crash recovery
        self.autosave_manager = AutosaveManager(
            get_editors_fn = self._get_all_editors_indexed,
            status_fn      = lambda msg, ms: self.statusBar().showMessage(msg, ms),
        )
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setInterval(AUTOSAVE_INTERVAL_MS)
        self._autosave_timer.timeout.connect(self.autosave_manager.save_all)
        self._autosave_timer.start()

        # Tab System
        self.split_container = SplitContainer()
        self.split_container.pane_activated.connect(self._on_active_pane_changed)
        self.split_container.tab_close_requested.connect(self._on_pane_tab_close)
        self.split_container.current_changed.connect(self._on_pane_current_changed)
        # Compatibility shim — self.tabs always points to the active pane
        self.tabs = self.split_container.active_pane()

        # Layout
        self.central_container = QWidget()
        self.central_layout = QVBoxLayout(self.central_container)
        self.central_layout.setContentsMargins(0, 0, 0, 0)
        self.central_layout.setSpacing(0)

        self.find_replace_panel = FindReplaceWidget(self)
        self.find_replace_panel.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed
        )
        self.find_replace_panel.hide()

        self.central_layout.addWidget(self.find_replace_panel)
        self.central_layout.addWidget(self.split_container)
        self.setCentralWidget(self.central_container)

        # Shortcuts
        QShortcut(QKeySequence("Ctrl+F"),       self).activated.connect(self.show_find_replace)
        QShortcut(QKeySequence("Ctrl+H"),       self).activated.connect(self.show_find_replace)
        QShortcut(QKeySequence("Ctrl+Shift+F"), self).activated.connect(self.show_project_search)
        QShortcut(QKeySequence("Ctrl+Space"),   self).activated.connect(self.request_manual_completion)
        # Split pane shortcuts
        QShortcut(QKeySequence("Ctrl+\\"),        self).activated.connect(
            lambda: self._split_active(Qt.Orientation.Horizontal)
        )
        QShortcut(QKeySequence("Ctrl+Shift+\\"),  self).activated.connect(
            lambda: self._split_active(Qt.Orientation.Vertical)
        )
        QShortcut(QKeySequence("Ctrl+Shift+W"),   self).activated.connect(
            self._close_active_pane
        )
        # Ctrl+K, Ctrl+Left/Right — move focus between panes
        QShortcut(QKeySequence("Ctrl+K, Left"),   self).activated.connect(
            lambda: self._focus_adjacent_pane(-1)
        )
        QShortcut(QKeySequence("Ctrl+K, Right"),  self).activated.connect(
            lambda: self._focus_adjacent_pane(1)
        )


        setup_menus(self)
        self.plugin_manager = PluginManager(self)
        
        # Status Bar
        self.status_bar = self.statusBar()
        self.status_bar.setSizeGripEnabled(False)
        self.status_bar.setStyleSheet(build_status_bar_stylesheet(get_theme()))

        self.branch_label = QLabel("")
        self.status_bar.addWidget(self.branch_label)

        sep = QLabel("|")
        sep.setStyleSheet("color: rgba(255,255,255,0.3); padding: 0 2px;")
        self.status_bar.addWidget(sep)
        
        self._startup = StartupProgress(self.status_bar, parent=self)

        self.filetype_label   = QLabel("")
        self.indent_label     = QLabel("")
        self.encoding_label   = QLabel("UTF-8")
        self.lineending_label = QLabel("LF")
        self.cursor_label     = QLabel("Ln 1, Col 1")

        for lbl in (self.filetype_label, self.indent_label,
                    self.encoding_label, self.lineending_label,
                    self.cursor_label):
            self.status_bar.addPermanentWidget(lbl)

        self.ai_mode_btn = QPushButton("🏠 LOCAL")
        self.ai_mode_btn.setCheckable(False)
        self.ai_mode_btn.setFlat(True)
        self.ai_mode_btn.setFixedWidth(90)
        self.ai_mode_btn.clicked.connect(self.toggle_ai_mode)
        self.update_mode_label(self.settings_manager.get_backend())
        self.status_bar.addPermanentWidget(self.ai_mode_btn)
        self.hide_loading_indicator()

        # Panels & docks
        self.setup_sidebar()
        self.setup_git_panel()
        self.setup_output_panel()
        self.setup_chat_panel()
        self.setup_memory_panel()
        self.setup_find_in_files_panel()
        
        self.plugin_manager.discover_and_load(
            os.path.join(os.path.dirname(__file__), "plugins", "features")
        )

        _plugins_dir = os.path.join(os.path.dirname(__file__), 'plugins')
        registry.auto_register_languages(
            os.path.join(_plugins_dir, 'languages')
        )

        # Command palette — Ctrl+P
        self.command_palette = CommandPalette(self)

        # Single theme-change handler for main-window-owned widgets
        theme_signals.theme_changed.connect(self._apply_theme_to_widgets)

        self.process = QProcess(self)
        self.process.readyReadStandardOutput.connect(self.handle_stdout)
        self.process.readyReadStandardError.connect(self.handle_stderr)
        self.process.finished.connect(self.process_finished)

        self._restore_window_state()
        self._restore_session()

        self.wiki_manager = None
        self.wiki_context_builder = None
        self.wiki_watcher = None
 
        project_root = (
            self.git_dock.repo_path
            if hasattr(self, "git_dock") and self.git_dock.repo_path
            else None
        )
        if project_root:
            self._init_wiki(project_root)

        self._lang_detect_timer = QTimer()
        self._lang_detect_timer.setSingleShot(True)
        self._lang_detect_timer.timeout.connect(self._fire_ai_lang_detect) 
        self._lang_detect_running = False
       
    @pyqtSlot()
    def _on_repo_map_ready(self):
        self._startup.complete("Repo Map")

    # ── Theme handling ────────────────────────────────────────────────────

    def _apply_theme_to_widgets(self, t: dict):
        """
        Re-applies styles to main-window-owned widgets that have
        inline stylesheets overriding the app-level sheet.
        All child dialogs/panels handle themselves via theme_signals.
        """
        self.status_bar.setStyleSheet(build_status_bar_stylesheet(t))
        for pane in self.split_container.all_panes():
            pane.setStyleSheet(build_tab_widget_stylesheet(t))
        self.output_editor.setStyleSheet(build_output_panel_stylesheet(t))
        self.explain_error_btn.setStyleSheet(build_explain_error_btn_stylesheet(t))
        self.tree_view.setStyleSheet(build_tree_view_stylesheet(t))
    
        dock_style = build_dock_stylesheet(t)
    
        # Shell-owned docks
        for dock in (self.sidebar_dock, self.output_dock,
                     self.search_dock):
            dock.setStyleSheet(dock_style)
    
        # Plugin-owned docks
        for label, (dock_attr, _) in self.plugin_manager.docks.items():
            dock = getattr(self, dock_attr, None)
            if dock:
                dock.setStyleSheet(dock_style)
    
        # Rebuild file model icons with new palette
        self.file_model._rebuild_icons(t)
        self.tree_view.viewport().update()
    
        # Re-apply syntax highlighting across ALL panes
        for _, editor in self.split_container.all_editors():
            if hasattr(editor, 'file_path') and editor.file_path:
                ext = os.path.splitext(editor.file_path)[1].lower()
                editor.highlighter = registry.get_highlighter(editor.document(), ext)

    # ── Mode / status bar ─────────────────────────────────────────────────

    def toggle_inline_completion(self, enabled):
        self.inline_completion_enabled = enabled

    def update_status_bar(self):
        editor = self.current_editor()
        if not editor:
            self.cursor_label.setText("")
            self.filetype_label.setText("")
            self.indent_label.setText("")
            return
    
        cursor = editor.textCursor()
        self.cursor_label.setText(
            f"Ln {cursor.blockNumber() + 1}, Col {cursor.columnNumber() + 1}"
        )
    
        if editor and hasattr(editor, "multi_cursor") and editor.multi_cursor.active:
            count = editor.multi_cursor.cursor_count()
            self.cursor_label.setText(
                f"Ln {cursor.blockNumber()+1}, Col {cursor.columnNumber()+1}"
                f"  ·  {count} cursors"
            )
    
        path = getattr(editor, 'file_path', None)
        if path:
            ext = os.path.splitext(path)[1].lower()
            type_map = {
                # Python
                '.py':    'Python',
                # Web
                '.html':  'HTML',
                '.htm':   'HTML',
                '.css':   'CSS',
                '.scss':  'SCSS',
                '.sass':  'Sass',
                '.less':  'Less',
                '.js':    'JavaScript',
                '.jsx':   'JavaScript',
                '.ts':    'TypeScript',
                '.tsx':   'TypeScript',
                # Data / config
                '.json':  'JSON',
                '.toml':  'TOML',
                '.xml':   'XML',
                '.yml':   'YAML',
                '.yaml':  'YAML',
                # Infrastructure
                '.tf':    'Terraform',
                '.tfvars':'Terraform Vars',
                '.hcl':   'HCL',
                '.nix':   'Nix',
                # Shell
                '.sh':    'Bash',
                '.bash':  'Bash',
                '.zsh':   'Zsh',
                '.fish':  'Fish',
                # Scripting
                '.pl':    'Perl',
                '.pm':    'Perl Module',
                '.t':     'Perl Test',
                '.lua':   'Lua',
                '.rb':    'Ruby',
                '.php':   'PHP',
                # Systems
                '.rs':    'Rust',
                '.go':    'Go',
                '.c':     'C',
                '.h':     'C Header',
                '.cpp':   'C++',
                '.hpp':   'C++ Header',
                '.java':  'Java',
                '.kt':    'Kotlin',
                '.swift': 'Swift',
                # Docs
                '.md':    'Markdown',
                '.rst':   'reStructuredText',
                '.txt':   'Text',
                '.tex':   'LaTeX',
                # SQL
                '.sql':   'SQL',
                # CI/CD
                '.gitlab-ci.yml':  'GitLab CI',
            }
            self.filetype_label.setText(
                type_map.get(ext, ext.lstrip('.').upper() or 'Plain Text')
            )
        else:
            self.filetype_label.setText('Plain Text')
    
        text = editor.toPlainText()
        tab_count   = sum(1 for l in text.split('\n') if l.startswith('\t'))
        space_count = sum(1 for l in text.split('\n') if l.startswith('    '))
        self.indent_label.setText("Tabs" if tab_count > space_count else "Spaces: 4")
    
        if '\r\n' in text:
            self.lineending_label.setText("CRLF")
        elif '\r' in text:
            self.lineending_label.setText("CR")
        else:
            self.lineending_label.setText("LF")
    
        if path and os.path.exists(path):
            try:
                import chardet
                with open(path, 'rb') as f:
                    raw_bytes = f.read(4096)
                detected = chardet.detect(raw_bytes)
                enc = (detected.get('encoding') or 'UTF-8').upper()
                enc = enc.replace('UTF-8-SIG', 'UTF-8 BOM').replace('ASCII', 'UTF-8')
                self.encoding_label.setText(enc)
            except ImportError:
                self.encoding_label.setText("UTF-8")
        else:
            self.encoding_label.setText("UTF-8")

    def update_git_branch(self):
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
                self.branch_label.setText(f"⎇  {result.stdout.strip()}")
            else:
                self.branch_label.setText("")
        except Exception:
            self.branch_label.setText("")

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

    # ── Workers ───────────────────────────────────────────────────────────

    def create_worker(self, prompt, editor_text="", cursor_pos=0,
                      generate_function=False, is_edit=False, is_chat=False):
        backend  = self.settings_manager.get_backend()
        model    = (self.settings_manager.get_chat_model() if is_chat
                    else self.settings_manager.get_inline_model())
        api_key  = self.settings_manager.get_api_key()
 
        # Build wiki context for all non-chat modes.                      
        # Chat mode gets it through ContextEngine.build() instead.        
        wiki_ctx = ""                                                      
        if not is_chat and hasattr(self, "wiki_context_builder") and self.wiki_context_builder:        
            editor = self.current_editor()                                
            fp = getattr(editor, "file_path", None) if editor else None  
            if fp:                                                         
                from pathlib import Path                                   
                wiki_ctx = self.wiki_context_builder.for_file(Path(fp))  
 
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
            wiki_context=wiki_ctx,                                         
        )

    # ── Language detection ────────────────────────────────────────────────

    def detect_language_from_content(self, text: str) -> str:
        if not text.strip() or len(text) < 20:
            return ""

        first_line = text.split('\n')[0].strip()

        shebang_map = {
            'python': '.py', 'node': '.js', 'bash': '.sh',
            'sh': '.sh', 'ruby': '.rb', 'perl': '.pl', 'php': '.php',
        }
        if first_line.startswith('#!'):
            for key, ext in shebang_map.items():
                if key in first_line:
                    return ext

        checks = [
            (r'^(import|from)\s+\w+|^def \w+\(|^class \w+\s*[:(]|^@\w+',            '.py'),
            (r'^---\s*$|^-\s+name:\s|^hosts:\s|^tasks:\s|^\s+ansible\.',             '.yml'),
            (r'interface\s+\w+\s*\{|:\s*(string|number|boolean|any)\b|<[A-Z]\w*>',   '.ts'),
            (r'\b(const|let|var)\s+\w+\s*=|=>\s*\{|require\s*\(|\.then\s*\(',        '.js'),
            (r'<html|<!DOCTYPE|<head>|<body>|<div',                                    '.html'),
            (r'nixpkgs|mkShell|buildInputs|stdenv\.mkDerivation|pkgs\.',              '.nix'),
            (r'^#{1,6}\s\w|\*\*\w+\*\*|\[.+\]\(https?://',                           '.md'),
            (r'^\s*(if|for|while|case)\s+.*;\s*(then|do)\b|^\s*fi\b|^\s*done\b',     '.sh'),
            (r'^\s*(?:use\s+strict|use\s+warnings|sub\s+\w+\s*\{|my\s+\$\w+)', '.pl'),
        ]
        for pattern, ext in checks:
            if re.search(pattern, text, re.MULTILINE):
                return ext
        return ""

    def _ai_detect_language(self, text: str):
        editor = self.current_editor()
        if not editor or editor.file_path:
            return
        if getattr(self, '_lang_detect_running', False):
            return
        self._lang_detect_running = True

        snippet = text[:800]
        prompt = (
            "Identify the programming language of the following code snippet. "
            "Reply with ONLY a single file extension including the dot, "
            "for example: .py  .js  .ts  .sh  .yml  .html  .nix  .md  .go  .rs  .cpp  .c  .lua\n"
            "If you cannot determine the language, reply with: unknown\n\n"
            f"```\n{snippet}\n```"
        )

        thread = QThread()
        worker = self.create_worker(prompt=prompt, is_chat=False)
        worker.moveToThread(thread)
        result_buf = []

        def on_update(text):
            result_buf.append(text)

        def on_finished():
            self._lang_detect_running = False
            raw = ''.join(result_buf).strip().lower()
            match = re.search(r'\.[a-z]+', raw)
            if not match:
                return
            ext = match.group(0)
            if ext not in registry.registered_extensions:
                return
            current_editor = self.current_editor()
            if not current_editor or current_editor.file_path:
                return
            if ext != getattr(current_editor, '_detected_ext', ''):
                current_editor._detected_ext = ext
                current_editor.highlighter = registry.get_highlighter(
                    current_editor.document(), ext
                )
                self.update_status_bar()
                self.statusBar().showMessage(
                    f"Language detected: {ext.lstrip('.')} (AI)", 3000
                )

        worker.update_ghost.connect(on_update)
        worker.finished.connect(on_finished)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.started.connect(worker.run)
        self.active_threads.append(thread)
        thread.finished.connect(
            lambda: self.active_threads.remove(thread)
            if thread in self.active_threads else None
        )
        thread.start()

    def _fire_ai_lang_detect(self):
        editor = self.current_editor()
        if not editor or editor.file_path:
            return
        text = editor.toPlainText()
        if len(text) > 40:
            self._ai_detect_language(text)

    def request_manual_completion(self):
        editor = self.current_editor()
        if editor and editor.hasFocus():
            editor.request_completion_hotkey()

    # ── Markdown preview ──────────────────────────────────────────────────

    def _refresh_markdown_preview(self, editor=None):
        if editor is None:
            editor = self.current_editor()
        if not editor:
            return
        path = getattr(editor, 'file_path', '') or ''
        if not path.lower().endswith(('.md', '.markdown')):
            return
        self.plugin_manager.emit("file_opened", path=path, editor=editor)
    
    def _sync_markdown_scroll(self):
        editor = self.current_editor()
        if not editor:
            return
        path = getattr(editor, 'file_path', '') or ''
        if not path.lower().endswith(('.md', '.markdown')):
            return
        first_visible = editor.firstVisibleBlock().blockNumber()
        total_lines   = editor.document().blockCount()
        self.plugin_manager.emit("editor_scrolled",
                                 first_visible=first_visible,
                                 total_lines=total_lines)

    # ── Window state ──────────────────────────────────────────────────────

    def _restore_window_state(self):
        geometry = self.settings_manager.get('window_geometry')
        if geometry:
            try:
                from PyQt6.QtCore import QByteArray
                self.restoreGeometry(QByteArray.fromHex(geometry.encode()))
            except Exception:
                pass
    
        dock_state = self.settings_manager.get('dock_state')
        if dock_state:
            try:
                from PyQt6.QtCore import QByteArray
                self.restoreState(QByteArray.fromHex(dock_state.encode()))
            except Exception:
                pass
    
        if hasattr(self, 'md_preview_dock') and self.md_preview_dock is not None:
            if self.settings_manager.get('md_preview_visible'):
                self.md_preview_dock.show()
            else:
                self.md_preview_dock.hide()
    
        if hasattr(self, 'chat_panel'):
            self.chat_panel.raise_()
    
        # Restore plugin dock visibility after Qt settles
        plugin_dock_state = self.settings_manager.get('plugin_dock_state') or {}
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

    # ── File management ───────────────────────────────────────────────────

    def open_file_in_tab(self, file_path, line_number=None):
        if os.path.isdir(file_path):
            return
 
        editor_to_focus = None
 
        # Search ALL panes for already-open file
        for pane in self.split_container.all_panes():
            for i in range(pane.count()):
                editor = pane.widget(i)
                if hasattr(editor, 'file_path') and editor.file_path == file_path:
                    self.split_container._set_active(pane)
                    self.tabs = pane
                    pane.setCurrentIndex(i)
                    editor_to_focus = editor
                    break
            if editor_to_focus:
                break
 
        if not editor_to_focus:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                filename = os.path.basename(file_path)
                editor_to_focus = self.add_new_tab(filename, content, file_path)
                ext = os.path.splitext(file_path)[1].lower()
                self._apply_editor_mode(editor_to_focus, ext)
            except Exception as e:
                print(f"Could not open file: {e}")
                return
 
        if editor_to_focus and line_number is not None:
            cursor = editor_to_focus.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            cursor.movePosition(
                QTextCursor.MoveOperation.NextBlock, n=line_number - 1
            )
            editor_to_focus.setTextCursor(cursor)
            editor_to_focus.ensureCursorVisible()
            editor_to_focus.setFocus()
            editor_to_focus.highlight_current_line()

    def _apply_editor_mode(self, editor, ext: str):
        from PyQt6.QtGui import QTextOption
        is_md = ext in ('.md', '.markdown')
        editor.setWordWrapMode(
            QTextOption.WrapMode.WordWrap if is_md else QTextOption.WrapMode.NoWrap
        )
        if hasattr(self, 'intent_tracker') and editor.file_path:
            self.intent_tracker.record_file_edit(editor.file_path)
        self._refresh_markdown_preview(editor)

    # ── Find / Replace ────────────────────────────────────────────────────

    def show_find_replace(self):
        self.find_replace_panel.show()
        self.find_replace_panel.focus_find()

    def setup_find_in_files_panel(self):
        self.search_dock = QDockWidget("Find in Files", self)
        self.search_dock.setStyleSheet(build_dock_stylesheet(get_theme()))
        self.find_in_files_widget = FindInFilesWidget(self)
        self.find_in_files_widget.open_file_request.connect(self.open_file_in_tab)
        self.search_dock.setWidget(self.find_in_files_widget)
        self.search_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable |
            QDockWidget.DockWidgetFeature.DockWidgetMovable
        )
        self.search_dock.setObjectName("search_dock")
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.search_dock)
        if hasattr(self, 'output_dock'):
            self.tabifyDockWidget(self.output_dock, self.search_dock)
        self.search_dock.hide()

    def show_project_search(self):
        self.search_dock.show()
        self.search_dock.raise_()
        self.find_in_files_widget.focus_search()

    # ── Settings ──────────────────────────────────────────────────────────

    def show_settings_dialog(self):
        dialog = SettingsDialog(self.settings_manager, self)
        if dialog.exec():
            self.statusBar().showMessage("Settings saved successfully.", 3000)

    # ── Tab management ────────────────────────────────────────────────────

    def current_editor(self):
        # Return focused editor across ALL panes, not just active tab
        focused = QApplication.focusWidget()
        from editor.ghost_editor import GhostEditor
        if isinstance(focused, GhostEditor):
            return focused
        # Fall back to active pane's current tab
        return self.split_container.active_pane().currentWidget()
        
    def _open_recovered_tab(self, name: str, content: str,
                            file_path, cursor_pos: int):
        """Open a recovered autosave entry as a new tab."""
        editor = self.add_new_tab(name, content, file_path)
        # Mark dirty so the tab title shows * and user knows it needs saving
        editor.original_text = ""
        cursor = editor.textCursor()
        cursor.setPosition(min(cursor_pos, len(content)))
        editor.setTextCursor(cursor)
        editor.ensureCursorVisible()

    def add_new_tab(self, name="Untitled", content="", path=None):
        # If the active pane has only one empty untitled tab, replace it
        active_pane = self.split_container.active_pane()
        if (path and active_pane.count() == 1):
            existing = active_pane.widget(0)
            if (existing and
                    getattr(existing, 'file_path', None) is None and
                    not existing.toPlainText().strip() and
                    active_pane.tabText(0).lstrip("⟳ ") == "Untitled"):
                # Replace it — reuse the slot
                active_pane.setTabText(0, name)
                existing.file_path = path
                self._is_loading = True
                existing.setPlainText(content)
                existing.set_original_state(content)
                self._is_loading = False
                if path:
                    self.intent_tracker.record_file_edit(path)
                ext = os.path.splitext(name)[1].lower()
                existing.highlighter = registry.get_highlighter(
                    existing.document(), ext
                )
                self._wire_editor_lsp(existing)
                existing.cursorPositionChanged.connect(self._sync_markdown_scroll)
                active_pane.setCurrentIndex(0)
                return existing
        editor = GhostEditor(settings_manager=self.settings_manager)
        self._is_loading = True
        editor.setPlainText(content)
        editor.set_original_state(content)
        editor.file_path = path
    
        if path:
            self.intent_tracker.record_file_edit(path)
    
        ext = os.path.splitext(name)[1].lower() if path else ""
        editor.highlighter = registry.get_highlighter(editor.document(), ext)
    
        editor.cursorPositionChanged.connect(self.update_status_bar)
        editor.cursorPositionChanged.connect(self._sync_markdown_scroll)
        editor.verticalScrollBar().valueChanged.connect(
            lambda _: self._sync_markdown_scroll()
        )
        editor.textChanged.connect(self.on_text_changed)
        editor.ai_started.connect(self.show_loading_indicator)
        editor.ai_finished.connect(self.hide_loading_indicator)
        editor.error_help_requested.connect(self.handle_editor_error_help)
        editor.send_to_chat_requested.connect(self.load_snippet_to_chat)
        editor.textChanged.connect(lambda e=editor: (
            self.plugin_manager.emit(
                "markdown_changed",
                text=e.toPlainText()
            ) if (getattr(e, 'file_path', '') or '').lower().endswith(('.md', '.markdown'))
            else None
        ))
    
        # ── Vector index — accepted completions ──────────────────────
        def _on_completion_accepted(text, ctx, e=editor):
            if self.vector_index:
                self.vector_index.index_completion(
                    text, ctx, getattr(e, "file_path", "") or ""
                )
        editor.completion_accepted.connect(_on_completion_accepted)
    
        index = self.tabs.addTab(editor, name)
        self.tabs.setCurrentIndex(index)
        self._is_loading = False
    
        self._wire_editor_lsp(editor)
    
        return editor

    def _on_active_pane_changed(self, pane: EditorPane):
        """Called when a different pane becomes active."""
        self.tabs = pane   # update shim
        self.update_status_bar()
        self.update_git_branch()
        self._refresh_markdown_preview()
        editor = pane.currentWidget()
 
    def _on_pane_tab_close(self, pane: EditorPane, index: int):
        """Route tab close from any pane — collapse pane if it becomes empty."""
        count_before = pane.count()   # capture BEFORE close_tab runs

        self.tabs = pane
        self.close_tab(index)

        count_after = pane.count()
        for i in range(pane.count()):
            w = pane.widget(i)
        
        self.tabs = self.split_container.active_pane()    
    
        all_panes = self.split_container.all_panes()
        if len(all_panes) <= 1:
            self.tabs = self.split_container.active_pane()
            return
    
        should_collapse = False
    
        if pane.count() == 0:
            should_collapse = True
    
        elif pane.count() == 1 and count_before == 1:
            # close_tab auto-created an Untitled because count hit 0
            # — remove it and collapse
            only = pane.widget(0)
            is_empty_untitled = (
                only is not None
                and getattr(only, 'file_path', None) is None
                and not only.toPlainText().strip()
                and pane.tabText(0).lstrip("⟳ ") == "Untitled"
            )
            if is_empty_untitled:
                if hasattr(only, 'teardown_lsp'):
                    only.teardown_lsp()
                only.deleteLater()
                pane.removeTab(0)
                should_collapse = True
    
        if should_collapse:
            self.split_container.close_pane(pane)
    
        self.tabs = self.split_container.active_pane()
 
    def _on_pane_current_changed(self, pane: EditorPane, index: int):
        """Called when tab selection changes in any pane."""
        if pane is self.split_container.active_pane():
            self._on_tab_changed(index)
 
    def _split_active(self, orientation: Qt.Orientation):
        """Split the active pane and open a new empty tab in the new pane."""
        self.split_container.split_active(orientation)
        # After split, the new pane is NOT yet active — activate it
        panes = self.split_container.all_panes()
        # The new pane is the one with 0 tabs
        for pane in panes:
            if pane.count() == 0:
                self.split_container._set_active(pane)
                self.tabs = pane
                self.add_new_tab("Untitled", "")
                break
 
    def _close_active_pane(self):
        """Close the active pane (must have 0 or 1 empty tab)."""
        pane = self.split_container.active_pane()
        # Close all tabs in the pane first
        while pane.count() > 0:
            editor = pane.widget(0)
            if editor and hasattr(editor, 'is_dirty') and editor.is_dirty():
                # Don't force-close dirty files
                self.statusBar().showMessage(
                    "Save or discard changes before closing pane.", 3000
                )
                return
            if editor:
                if hasattr(editor, 'teardown_lsp'):
                    editor.teardown_lsp()
                editor.deleteLater()
            pane.removeTab(0)
        self.split_container.close_pane(pane)
        self.tabs = self.split_container.active_pane()
 
    def _focus_adjacent_pane(self, direction: int):
        """Move keyboard focus to the next/previous pane."""
        panes = self.split_container.all_panes()
        if len(panes) < 2:
            return
        current = self.split_container.active_pane()
        try:
            idx = panes.index(current)
        except ValueError:
            return
        next_idx = (idx + direction) % len(panes)
        next_pane = panes[next_idx]
        self.split_container._set_active(next_pane)
        self.tabs = next_pane
        editor = next_pane.currentWidget()
        if editor:
            editor.setFocus()

    def handle_editor_error_help(self, error_msg, code, line_num):
        self.chat_panel.expand()
        self.chat_panel.switch_to_chat()

        user_text = f"I have a SyntaxError on line {line_num}: {error_msg}. Can you help me fix it?"
        prompt = f"""The user has encountered a SyntaxError in their Python file.

Error Message: {error_msg}
Error Location: Line {line_num}

Full Code:
```python
{code}
```

Instructions:
1. Briefly explain what the error means and why it happened.
2. Provide the corrected code for that line or block."""

        self._last_user_message = user_text
        self._append_user_message(user_text)
        self._ai_response_buffer = ""
        self.current_ai_raw_text = ""

        thread = QThread()
        self.chat_worker = self.create_worker(prompt=prompt, is_chat=True)
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

    def closeEvent(self, event):
        # Final autosave flush before checking for unsaved changes
        self.autosave_manager.save_all()
        if hasattr(self, "lsp_manager") and self.lsp_manager:
                self.lsp_manager.stop()
        unsaved = any(
            hasattr(editor, 'is_dirty') and editor.is_dirty()
            for _, editor in self.split_container.all_editors()
        )

        if unsaved:
            reply = QMessageBox.question(
                self, "Unsaved Changes",
                "You have unsaved files. Do you want to save them before exiting?",
                QMessageBox.StandardButton.SaveAll |
                QMessageBox.StandardButton.Discard |
                QMessageBox.StandardButton.Cancel
            )
            if reply == QMessageBox.StandardButton.SaveAll:
                for pane in self.split_container.all_panes():
                    self.tabs = pane
                    for i in range(pane.count()):
                        editor = pane.widget(i)
                        if hasattr(editor, 'is_dirty') and editor.is_dirty():
                            self.save_file(i)
                self.tabs = self.split_container.active_pane()
                event.accept()
            elif reply == QMessageBox.StandardButton.Discard:
                event.accept()
            else:
                event.ignore()
                return
        else:
            event.accept()

        if event.isAccepted():
            self.autosave_manager.clear_all()
            registry.deactivate_all_features()
            self._save_current_session()
            self.settings_manager.set(
                'dock_state', self.saveState().toHex().data().decode()
            )
            self.settings_manager.set(
                'window_geometry', self.saveGeometry().toHex().data().decode()
            )
            if hasattr(self, 'md_preview_dock') and self.md_preview_dock is not None:
                self.settings_manager.set(
                    'md_preview_visible', self.md_preview_dock.isVisible()
                )
            # Save plugin dock visibility BEFORE deactivating plugins
            plugin_dock_state = {}
            for label, (dock_attr, _) in self.plugin_manager.docks.items():
                dock = getattr(self, dock_attr, None)
                if dock is not None:
                    plugin_dock_state[dock_attr] = dock.isVisible()
            self.settings_manager.set('plugin_dock_state', plugin_dock_state)
        
            # Deactivate plugins LAST
            for plugin in self.plugin_manager._plugins:
                try:
                    plugin.deactivate()
                except Exception as e:
                    print(f"[PluginManager] Error deactivating {plugin.name}: {e}")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'chat_panel'):
            status_bar_height  = self.statusBar().height()
            menu_bar_height    = self.menuBar().height()
            available_height   = self.height() - status_bar_height - menu_bar_height
            self.chat_panel.setFixedHeight(available_height)
            self.chat_panel.move(
                self.width() - SlidingPanel.HANDLE_WIDTH, menu_bar_height
            )
            if self.chat_panel._expanded:
                self.chat_panel.move(
                    self.width() - self.chat_panel.PANEL_WIDTH, menu_bar_height
                )
            self.chat_panel.raise_()

    def close_tab(self, index):
        editor = self.tabs.widget(index)
        if not editor:
            return
    
        if hasattr(editor, 'is_dirty') and editor.is_dirty():
            filename = self.tabs.tabText(index).replace("*", "")
            reply = QMessageBox.question(
                self, "Unsaved Changes",
                f"Save changes to '{filename}' before closing?",
                QMessageBox.StandardButton.Save |
                QMessageBox.StandardButton.Discard |
                QMessageBox.StandardButton.Cancel
            )
            if reply == QMessageBox.StandardButton.Save:
                if not self.save_file(index):
                    return
            elif reply == QMessageBox.StandardButton.Cancel:
                return
    
        # Teardown and cleanup — get file_path BEFORE removing
        file_path = getattr(editor, "file_path", None)
    
        if hasattr(editor, "teardown_lsp"):
            editor.teardown_lsp()
    
        if file_path:
            self.autosave_manager.clear(file_path)
        else:
            self.autosave_manager.clear_untitled(index)
    
        # Single removal
        self.tabs.removeTab(index)
        editor.deleteLater()
    
        # Only add Untitled if this is the sole remaining pane and now empty
        if self.tabs.count() == 0 and len(self.split_container.all_panes()) == 1:
            self.add_new_tab("Untitled", "")

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

            detected_ext = getattr(editor, '_detected_ext', '')
            all_filters = {
                '.py': 'Python Files (*.py)', '.js': 'JavaScript Files (*.js)',
                '.ts': 'TypeScript Files (*.ts)', '.tsx': 'TypeScript JSX Files (*.tsx)',
                '.html': 'HTML Files (*.html)', '.htm': 'HTML Files (*.htm)',
                '.yml': 'YAML Files (*.yml)', '.yaml': 'YAML Files (*.yaml)',
                '.sh': 'Shell Scripts (*.sh)', '.bash': 'Bash Scripts (*.bash)',
                '.nix': 'Nix Files (*.nix)', '.md': 'Markdown Files (*.md)',
                '.json': 'JSON Files (*.json)', '.txt': 'Text Files (*.txt)',
            }

            if detected_ext and detected_ext in all_filters:
                first  = all_filters[detected_ext]
                rest   = [v for k, v in all_filters.items() if k != detected_ext]
                filter_str   = ';;'.join([first] + rest + ['All Files (*)'])
                default_name = os.path.join(start_dir, f"untitled{detected_ext}")
            else:
                filter_str   = ';;'.join(list(all_filters.values()) + ['All Files (*)'])
                default_name = start_dir

            path, _ = QFileDialog.getSaveFileName(
                self, "Save File", default_name, filter_str
            )
            if path:
                editor.file_path = path
                self.tabs.setTabText(index, os.path.basename(path))
                ext = os.path.splitext(path)[1].lower()
                editor.highlighter = registry.get_highlighter(editor.document(), ext)
                editor._detected_ext = ''
                self._lang_detect_timer.stop()
                self._lang_detect_running = False
                self._apply_editor_mode(editor, ext)
            else:
                return False

        try:
            code = editor.toPlainText()
            with open(editor.file_path, "w", encoding="utf-8") as f:
                f.write(code)

            editor.set_original_state(code)
            editor._detected_ext = ''
            # Invalidate repo map so next chat gets fresh structure
            if self.repo_map and editor.file_path:
                self.repo_map.invalidate(editor.file_path)
            if self.vector_index and editor.file_path:
                self.vector_index.index_file(editor.file_path)

            current_text = self.tabs.tabText(index)
            if current_text.endswith("*"):
                self.tabs.setTabText(index, current_text[:-1])

            ext = os.path.splitext(editor.file_path)[1].lower()
            editor.highlighter = registry.get_highlighter(editor.document(), ext)
            self._apply_editor_mode(editor, ext)

            if hasattr(self, 'git_dock'):
                self.git_dock.refresh_status()
                
            if editor.file_path:
                self.plugin_manager.emit("file_saved", path=editor.file_path)

            self.statusBar().showMessage(f"Saved: {editor.file_path}", 3000)
            self.autosave_manager.clear(editor.file_path)
            return True
        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"Could not save file: {e}")
            return False

    def _save_current_session(self):
        # Save active pane tabs only
        pane = self.split_container.active_pane()
        tabs = []
        for i in range(pane.count()):
            editor = pane.widget(i)
            path = getattr(editor, 'file_path', None)
            cursor_pos = editor.textCursor().position() if editor else 0
            tabs.append((path, cursor_pos))
 
        project_path = None
        if hasattr(self, 'git_dock') and self.git_dock.repo_path:
            project_path = self.git_dock.repo_path
 
        save_session(tabs, pane.currentIndex(), project_path)

    def _restore_session(self, project_path=None):
        self._startup.register("LSP")
        self._startup.register("Repo Map")
        self._startup.register("Vector Index")
        if project_path is None and hasattr(self, 'git_dock') and self.git_dock.repo_path:
            project_path = self.git_dock.repo_path

        session = load_session(project_path)

        if not session or not session.get("tabs"):
            self.add_new_tab("Untitled", "")
            return

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
            self._start_lsp(project_root=saved_project)
            self._init_repo_map(project_root=saved_project)
            self._init_vector_index(project_root=saved_project)
            self._init_wiki(project_root=saved_project)
            if hasattr(self, 'update_git_branch'):
                self.update_git_branch()
            self.plugin_manager.emit("project_opened", project_root=saved_project)

        restored = 0
        for tab_data in session.get("tabs", []):
            path       = tab_data.get("path")
            cursor_pos = tab_data.get("cursor", 0)
            if not path or not os.path.exists(path):
                continue
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                editor = self.add_new_tab(os.path.basename(path), content, path)
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
        # Crash recovery — restore any autosaved files silently
        self.autosave_manager.restore(self._open_recovered_tab) 

    def _close_all_tabs_for_switch(self):
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
            if (self.vector_index
                and hasattr(self, '_last_active_file')
                and self._last_active_file
                and self._last_active_file != editor.file_path):
                self.vector_index.index_edit(
                    self._last_active_file, editor.file_path
                )
            self._last_active_file = editor.file_path
    
        # Breadcrumb — connect to new active editor
        if hasattr(self, 'lsp_manager') and editor:
            if hasattr(editor, '_breadcrumb') and not editor._breadcrumb.isVisible():
                if self.lsp_manager and self.lsp_manager.is_supported(
                        getattr(editor, 'file_path', '') or ''):
                    editor.setup_breadcrumb(self.lsp_manager)
                    
        if editor:
            fp = getattr(editor, 'file_path', None)
            if fp:
                self.plugin_manager.emit("file_opened", path=fp, editor=editor)
         
        # Sync markdown preview scroll on tab switch
        self._sync_markdown_scroll() 
            
    def _get_all_editors_indexed(self):
        """Return list of (tab_index, editor) for all open tabs."""
        return self.split_container.all_editors()


    # ── Context building ──────────────────────────────────────────────────

    def estimate_tokens(self, text: str) -> int:
        return len(text) // 4

    def get_project_tree(self):
        root = self.file_model.filePath(self.tree_view.rootIndex())
        if not root or not os.path.isdir(root):
            return ""
        lines = []
        skip = {'__pycache__', 'node_modules', '.git', 'venv', '.venv', 'dist', 'build'}
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted([d for d in dirnames
                                   if not d.startswith('.') and d not in skip])
            level  = dirpath.replace(root, '').count(os.sep)
            indent = '  ' * level
            lines.append(f"{indent}{os.path.basename(dirpath)}/")
            for f in sorted(filenames):
                if not f.startswith('.') and not f.endswith(('.pyc', '.pyo')):
                    lines.append(f"{indent}  {f}")
        return "[Project Structure]\n" + "\n".join(lines)

    def get_open_editors(self):
        editors = []
        current = self.current_editor()
    
        for i in range(self.tabs.count()):
            editor = self.tabs.widget(i)
            if not editor or not hasattr(editor, 'file_path'):
                continue
            if editor is current or not editor.file_path:
                continue
            editors.append(editor)
    
        return editors

    def resolve_local_imports(self, code_text, _visited=None, _depth=0, _max_depth=3):
        if _visited is None:
            _visited = set()
        if _depth >= _max_depth:
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
                candidate_paths = [os.path.join(project_root, rel_path)]
                if editor.file_path:
                    candidate_paths.append(
                        os.path.join(os.path.dirname(editor.file_path), rel_path)
                    )

                for full_path in candidate_paths:
                    full_path = os.path.normpath(full_path)
                    if not os.path.exists(full_path) or full_path in _visited:
                        continue
                    _visited.add(full_path)
                    try:
                        with open(full_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                        display_path = os.path.relpath(full_path, project_root)
                        if len(content) > MAX_FILE_SIZE:
                            content = content[:500] + "\n...(truncated)...\n" + content[-1000:]
                        imported_context.append(
                            f"\n--- Imported file: {display_path} (depth {_depth + 1}) ---\n"
                            f"```python\n{content}\n```\n"
                        )
                        nested = self.resolve_local_imports(
                            content, _visited=_visited, _depth=_depth + 1
                        )
                        if nested:
                            imported_context.append(nested)
                    except Exception:
                        pass
                    break
        return "".join(imported_context)

    # ── Chat / sliding panel ──────────────────────────────────────────────

    def setup_chat_panel(self):
        self.chat_panel = SlidingPanel(self, settings_manager=self.settings_manager)
        self.chat_panel.message_sent.connect(self._on_chat_message)
        self.chat_panel.show()
        self.chat_panel.raise_()
        self.setContentsMargins(0, 0, SlidingPanel.HANDLE_WIDTH, 0)

        saved = self.memory_manager.load_chat_history()
        if saved:
            self.chat_panel.chat_history.setHtml(saved)
            self.chat_panel.chat_history.moveCursor(QTextCursor.MoveOperation.End)

        self.chat_history = self.chat_panel.chat_history
        self.chat_input   = self.chat_panel.chat_input
        self.chat_history.anchorClicked.connect(self.handle_chat_link)
            
    def _start_lsp(self, project_root: str = None):
        """Start (or restart) all available language servers."""
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
        # Wire any open editors that support the newly-ready server
        for i in range(self.tabs.count()):
            editor = self.tabs.widget(i)
            if editor:
                self._wire_editor_lsp(editor)
    
    def _wire_editor_lsp(self, editor):
        """Attach LSPManager to an editor if it supports the file type."""
        if not self.lsp_manager:
            return
        if not getattr(editor, "file_path", None):
            return
        if not self.lsp_manager.is_supported(editor.file_path):
            return
        if hasattr(editor, "_lsp_manager"):
            return   # already wired
        editor.setup_lsp(self.lsp_manager)
        editor.goto_file_requested.connect(self._goto_file)
        # Breadcrumb
        if hasattr(editor, 'setup_breadcrumb'):
            editor.setup_breadcrumb(self.lsp_manager)
    
    def _goto_file(self, file_path: str, line: int, col: int):
        self.open_file_in_tab(file_path)
        editor = self.current_editor()
        if editor and hasattr(editor, "lsp_jump_to"):
            editor.lsp_jump_to(line, col)
            
    def _init_repo_map(self, project_root: str):
        """Build or rebuild the repo map for a new project root."""
        self.repo_map = RepoMap(project_root)
        # Pass a callback that fires on the Qt thread when build completes
        def _build_and_notify():
            self.repo_map._build_all()   # run synchronously in this thread
            # Use QMetaObject to safely call back onto the Qt thread
            from PyQt6.QtCore import QMetaObject, Qt as _Qt
            QMetaObject.invokeMethod(
                self, "_on_repo_map_ready",
                _Qt.ConnectionType.QueuedConnection,
            )
        threading.Thread(target=_build_and_notify, daemon=True).start()
    def _check_vector_ready(self):
        if self.vector_index and self.vector_index.is_ready:
            self._vector_ready_timer.stop()
            self._startup.complete("Vector Index")
            
    def _init_vector_index(self, project_root: str):
        """Create or replace the vector index for a new project root."""
        if self.vector_index:
            self.vector_index.close()
        self.vector_index = VectorIndex(
            project_root     = project_root,
            settings_manager = self.settings_manager,
        )
        self.vector_index.index_project(project_root)
    
        # Poll until ready, then notify — avoids adding a signal to VectorIndex
        self._vector_ready_timer = QTimer(self)
        self._vector_ready_timer.setInterval(200)
        self._vector_ready_timer.timeout.connect(self._check_vector_ready)
        self._vector_ready_timer.start()

    def _init_wiki(self, project_root: str) -> None:
        """Create or replace the wiki manager/watcher for a new project root.
        No-ops silently if project_root is not a git repo."""
        from pathlib import Path
        from core.wiki_manager import WikiManager
        from core.wiki_watcher import WikiWatcher
        from core.wiki_context_builder import WikiContextBuilder
 
        # Tear down any existing watcher
        if hasattr(self, "wiki_watcher") and self.wiki_watcher:
            self.wiki_watcher.stop()
 
        self.wiki_manager = WikiManager(
            repo_root=Path(project_root),
            model=self.settings_manager.get_chat_model(),
            api_url=self.settings_manager.get_api_url(),
            api_key=self.settings_manager.get_api_key(),
            backend=self.settings_manager.get_backend(),
        )
 
        if not self.wiki_manager.enabled:
            self.wiki_context_builder = None
            self.wiki_watcher = None
            return
 
        self.wiki_context_builder = WikiContextBuilder(
            self.wiki_manager, char_budget=3000
        )
        self.wiki_watcher = WikiWatcher(self.wiki_manager, parent=self)
        self.wiki_watcher.update_finished.connect(
            lambda updated: self.statusBar().showMessage(
                f"Wiki: {len(updated)} page(s) updated"
                if updated else "Wiki: up to date", 3000
            )
        )
        self.wiki_watcher.start()
        QTimer.singleShot(2000, self.wiki_watcher.trigger_full_update)

    def _on_chat_message(self, user_text: str):
        self._last_user_message = user_text
        self._append_user_message(user_text)
        self.memory_manager.add_turn("user", user_text)
    
        editor = self.current_editor()
        active_code = editor.toPlainText() if editor else ""
        file_path   = getattr(editor, "file_path", None)
    
        if not hasattr(self, "context_engine"):
            from ai.context_engine import ContextEngine
            self.context_engine = ContextEngine(
                memory_manager=self.memory_manager,
                estimate_tokens_fn=self.estimate_tokens
            )
 
        def _launch(lsp_ctx):
            # ── Wiki context (replaces vector index for chat) ────────     
            wiki_ctx = ""                                                  
            if hasattr(self, "wiki_context_builder") and self.wiki_context_builder and file_path:   
                from pathlib import Path                                   
                wiki_ctx = self.wiki_context_builder.for_prompt(           
                    user_text, source_path=Path(file_path)                
                )                                                           
 
            context = self.context_engine.build(
                user_text      = user_text,
                active_code    = active_code,
                file_path      = file_path,
                open_tabs      = self.get_open_editors(),
                cursor_pos     = editor.textCursor().position() if editor else None,
                lsp_context    = lsp_ctx,
                repo_map       = (
                    self.repo_map.get_context(user_text)
                    if self.repo_map else None
                ),
                vector_context = wiki_ctx,
            )
            prompt_with_context = f"{user_text}\n\n{context}"

            self._ai_response_buffer = ""
            self.current_ai_raw_text = ""

            thread = QThread()
            self.chat_worker = self.create_worker(prompt=prompt_with_context, is_chat=True)
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

        # Always compute line/col — falls back to 0,0 if no editor
        line, col = (
            editor.cursor_lsp_position()
            if editor and hasattr(editor, "cursor_lsp_position")
            else (0, 0)
        )

        if (self.lsp_context_provider and editor and file_path
                and self.lsp_manager and self.lsp_manager.is_supported(file_path)):
            self.lsp_context_provider.fetch(file_path, line, col, callback=_launch)
        else:
            _launch({})

    def setup_memory_panel(self):
        self.memory_panel = MemoryPanel(self.memory_manager, self)
        self.memory_panel.restore_conversation_requested.connect(
            self._restore_conversation
        )
        QTimer.singleShot(100, lambda: self.chat_panel.set_memory_widget(
            self.memory_panel
        ))

    # ── Runner ────────────────────────────────────────────────────────────

    def _show_about(self):
        AboutDialog(self).exec()

    def setup_output_panel(self):
        output_container = QWidget()
        layout = QVBoxLayout(output_container)
        layout.setContentsMargins(0, 0, 0, 0)

        self.output_editor = QPlainTextEdit()
        self.output_editor.setReadOnly(True)
        self.output_editor.setStyleSheet(build_output_panel_stylesheet(get_theme()))

        self.explain_error_btn = QPushButton("💡 Explain Error")
        self.explain_error_btn.setStyleSheet(build_explain_error_btn_stylesheet(get_theme()))
        self.explain_error_btn.hide()
        self.explain_error_btn.clicked.connect(self.explain_error)

        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(5, 5, 5, 5)
        btn_layout.addStretch()
        btn_layout.addWidget(self.explain_error_btn)

        layout.addWidget(self.output_editor)
        layout.addLayout(btn_layout)

        self.output_dock = QDockWidget("Output", self)
        self.output_dock.setStyleSheet(build_dock_stylesheet(get_theme()))
        self.output_dock.setWidget(output_container)
        self.output_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable |
            QDockWidget.DockWidgetFeature.DockWidgetMovable
        )
        self.output_dock.setObjectName("output_dock")
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.output_dock)
        self.output_dock.hide()

    def run_script(self):
        editor = self.current_editor()
        if not editor:
            return

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
        self.chat_panel.switch_to_chat()
        self.explain_error_btn.hide()

        user_text = "My script crashed with an error. Can you explain what went wrong and how to fix it?"
        context   = self.build_chat_context(
            user_text,
            self.current_editor().toPlainText() if self.current_editor() else ""
        )
        prompt = f"""{user_text}

[Error Trace]
{self.current_error_text[:8000]}

{context}

Instructions:
- Explain the error clearly
- Identify the root cause
- Show how to fix it
- Include corrected code if possible
"""
        self._last_user_message = user_text
        self._append_user_message(user_text)
        self._ai_response_buffer = ""
        self.current_ai_raw_text = ""

        thread = QThread()
        self.chat_worker = self.create_worker(prompt=prompt, is_chat=True)
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

    def handle_stdout(self):
        data   = self.process.readAllStandardOutput()
        stdout = bytes(data).decode("utf8")
        self.output_editor.insertPlainText(stdout)
        self.output_editor.ensureCursorVisible()

    def process_finished(self):
        self.output_editor.appendPlainText("\n>>> Process finished.")
        if hasattr(self, 'temp_file') and self.temp_file:
            try:
                os.remove(self.temp_file.name)
            except Exception:
                pass
            self.temp_file = None

    # ── Sidebar ───────────────────────────────────────────────────────────

    def setup_sidebar(self):
        self.file_model = CustomFileSystemModel(
            theme_name=self.settings_manager.get('theme')
        )
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
            
    def setup_symbol_outline(self):
        self.symbol_dock = SymbolOutlineDock(self)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.symbol_dock)
        self.tabifyDockWidget(self.sidebar_dock, self.symbol_dock)
        self.symbol_dock.hide()

    # ── AI loading indicator ──────────────────────────────────────────────

    def show_loading_indicator(self):
        pane  = self.split_container.active_pane()
        index = pane.currentIndex()
        if index >= 0:
            title = pane.tabText(index)
            if not title.startswith("⟳ "):
                pane.setTabText(index, "⟳ " + title)
 
    def hide_loading_indicator(self):
        for pane in self.split_container.all_panes():
            for i in range(pane.count()):
                title = pane.tabText(i)
                if title.startswith("⟳ "):
                    pane.setTabText(i, title[2:])

    def on_text_changed(self):
        editor = self.current_editor()
        if not editor or getattr(self, '_is_loading', False) or editor.function_active or not editor.hasFocus():
            return

        if not editor.file_path:
            text = editor.toPlainText()
            if len(text) > 20:
                ext         = self.detect_language_from_content(text)
                current_ext = getattr(editor, '_detected_ext', '')

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

        if hasattr(editor, 'is_dirty'):
            index         = self.tabs.indexOf(editor)
            current_title = self.tabs.tabText(index)
            if editor.is_dirty() and not current_title.endswith("*"):
                self.tabs.setTabText(index, current_title + "*")
            elif not editor.is_dirty() and current_title.endswith("*"):
                self.tabs.setTabText(index, current_title[:-1])

        editor.clear_ghost_text()
        
        # Cancel any in-flight completion (user is typing → invalidate it)
        if self.last_worker:
            self.last_worker.cancel()

    def ask_ai(self):
        editor = self.current_editor()
        if not self.inline_completion_enabled or not editor or not editor.hasFocus():
            return

        cursor    = editor.textCursor()
        line_text = cursor.block().text()
        if line_text.strip().endswith(":") or line_text.strip().endswith(")"):
            return

        text       = editor.toPlainText()
        cursor_pos = int(cursor.position())
        context    = text[max(0, cursor_pos - 1500):cursor_pos]
        cross_file_context = self.resolve_local_imports(text)

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

        current_symbol = self.intent_tracker.get_current_symbol(text, cursor_pos)
        if current_symbol:
            self.intent_tracker.record_cursor_symbol(current_symbol)

        intent_ctx = self.intent_tracker.build_intent_context(
            current_file_path=editor.file_path or "",
            language=lang,
        )

        prompt = (
            f"{intent_ctx}\n"
            f"{cross_file_context}\n"
            f"Complete the following {lang} code:\n\n{context}"
        )

        thread = QThread()
        worker = self.create_worker(
            prompt=prompt, editor_text=text, cursor_pos=cursor_pos,
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
    QApplication.setApplicationName("QuillAI")
    QApplication.setApplicationDisplayName("QuillAI")
    QApplication.setOrganizationName("GSSparks")

    app = QApplication(sys.argv)

    icon_path = os.path.join(
        os.path.dirname(__file__), 'images', 'quillai_logo_min.svg'
    )
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    sm = SettingsManager()
    apply_theme(app, sm.get('theme') or 'gruvbox_dark')

    window = CodeEditor()
    window.resize(1000, 700)
    window.show()
    sys.exit(app.exec())