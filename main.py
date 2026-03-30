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

from ui.theme import (apply_theme, get_theme, theme_signals,
                      build_status_bar_stylesheet,
                      build_editor_stylesheet,
                      build_dock_stylesheet,
                      build_tab_widget_stylesheet,
                      build_output_panel_stylesheet,
                      build_explain_error_btn_stylesheet,
                      build_tree_view_stylesheet)

from ui.menu import setup_file_menu
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
from ui.markdown_preview import MarkdownPreviewDock
from ui.command_palette import CommandPalette
from ui.terminal import TerminalDock
from ui.command_palette import CommandPalette
from ui.terminal import TerminalDock

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

        # 3. Basic App State
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

        # Tab System
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(lambda _: self._refresh_markdown_preview())
        self.tabs.currentChanged.connect(lambda _: self.update_status_bar())
        self.tabs.currentChanged.connect(lambda _: self.update_git_branch())
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.tabs.setStyleSheet(build_tab_widget_stylesheet(get_theme()))

        # Layout
        self.central_container = QWidget()
        self.central_layout = QVBoxLayout(self.central_container)
        self.central_layout.setContentsMargins(0, 0, 0, 0)
        self.central_layout.setSpacing(0)

        self.find_replace_panel = FindReplaceWidget(self)
        self.find_replace_panel.hide()

        self.central_layout.addWidget(self.find_replace_panel)
        self.central_layout.addWidget(self.tabs)
        self.setCentralWidget(self.central_container)

        # Shortcuts
        QShortcut(QKeySequence("Ctrl+F"),       self).activated.connect(self.show_find_replace)
        QShortcut(QKeySequence("Ctrl+H"),       self).activated.connect(self.show_find_replace)
        QShortcut(QKeySequence("Ctrl+Shift+F"), self).activated.connect(self.show_project_search)
        QShortcut(QKeySequence("Ctrl+Space"),   self).activated.connect(self.request_manual_completion)

        self.timer = QTimer()
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.ask_ai)

        setup_file_menu(self)
        self.setup_run_menu()
        self.setup_view_menu()
        self.setup_help_menu()

        # Status Bar
        self.status_bar = self.statusBar()
        self.status_bar.setSizeGripEnabled(False)
        self.status_bar.setStyleSheet(build_status_bar_stylesheet(get_theme()))

        self.branch_label = QLabel("")
        self.status_bar.addWidget(self.branch_label)

        sep = QLabel("|")
        sep.setStyleSheet("color: rgba(255,255,255,0.3); padding: 0 2px;")
        self.status_bar.addWidget(sep)

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
        self.setup_markdown_preview()
        self.setup_find_in_files_panel()

        _plugins_dir = os.path.join(os.path.dirname(__file__), 'plugins')
        registry.auto_register_languages(
            os.path.join(_plugins_dir, 'languages')
        )

        # Command palette — Ctrl+P
        self.command_palette = CommandPalette(self)
        QShortcut(QKeySequence("Ctrl+P"), self).activated.connect(
            self.command_palette.show_palette
        )

        # Terminal — Ctrl+`
        self.setup_terminal()
        QShortcut(QKeySequence("Ctrl+`"), self).activated.connect(
            self.toggle_terminal
        )

        # Single theme-change handler for main-window-owned widgets
        theme_signals.theme_changed.connect(self._apply_theme_to_widgets)

        self.process = QProcess(self)
        self.process.readyReadStandardOutput.connect(self.handle_stdout)
        self.process.readyReadStandardError.connect(self.handle_stderr)
        self.process.finished.connect(self.process_finished)

        self._restore_window_state()
        self._restore_session()

        registry.auto_register_features(
            os.path.join(os.path.dirname(__file__), 'plugins', 'features'),
            self
        )

        self._lang_detect_timer = QTimer()
        self._lang_detect_timer.setSingleShot(True)
        self._lang_detect_timer.timeout.connect(self._fire_ai_lang_detect)
        self._lang_detect_running = False

    # ── Theme handling ────────────────────────────────────────────────────

    def _apply_theme_to_widgets(self, t: dict):
        """
        Re-applies styles to main-window-owned widgets that have
        inline stylesheets overriding the app-level sheet.
        All child dialogs/panels handle themselves via theme_signals.
        """
        self.status_bar.setStyleSheet(build_status_bar_stylesheet(t))
        self.tabs.setStyleSheet(build_tab_widget_stylesheet(t))
        self.output_editor.setStyleSheet(build_output_panel_stylesheet(t))
        self.explain_error_btn.setStyleSheet(build_explain_error_btn_stylesheet(t))
        self.tree_view.setStyleSheet(build_tree_view_stylesheet(t))

        dock_style = build_dock_stylesheet(t)
        for dock in (self.sidebar_dock, self.output_dock,
                     self.search_dock, self.md_preview_dock,
                     self.terminal_dock):
            dock.setStyleSheet(dock_style)

        # Rebuild file model icons with new palette
        self.file_model._rebuild_icons(t)
        self.tree_view.viewport().update()

        # Terminal
        if hasattr(self, 'terminal_dock'):
            self.terminal_dock.apply_styles(t)

        # Re-apply syntax highlighting to all open editors
        for i in range(self.tabs.count()):
            editor = self.tabs.widget(i)
            if editor and hasattr(editor, 'file_path') and editor.file_path:
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

        path = getattr(editor, 'file_path', None)
        if path:
            ext = os.path.splitext(path)[1].lower()
            type_map = {
                '.py': 'Python', '.md': 'Markdown', '.html': 'HTML',
                '.htm': 'HTML', '.yml': 'YAML', '.yaml': 'YAML',
                '.nix': 'Nix', '.sh': 'Bash', '.bash': 'Bash',
                '.js': 'JavaScript', '.ts': 'TypeScript', '.json': 'JSON',
                '.toml': 'TOML', '.txt': 'Text',
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

    def setup_markdown_preview(self):
        self.md_preview_dock = MarkdownPreviewDock(self)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.md_preview_dock)
        self.md_preview_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable |
            QDockWidget.DockWidgetFeature.DockWidgetMovable |
            QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        self.md_preview_dock.setObjectName("md_preview_dock")
        self.md_preview_dock.hide()

    def _refresh_markdown_preview(self, editor=None):
        if editor is None:
            editor = self.current_editor()
        if not editor:
            return
        path = getattr(editor, 'file_path', '') or ''
        if not path.lower().endswith(('.md', '.markdown')):
            return
        if hasattr(self, 'md_preview_dock'):
            self.md_preview_dock.show()
            self.md_preview_dock.raise_()
            self.md_preview_dock.update_preview(editor.toPlainText())

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

        if hasattr(self, 'md_preview_dock'):
            if self.settings_manager.get('md_preview_visible'):
                self.md_preview_dock.show()
            else:
                self.md_preview_dock.hide()

        if hasattr(self, 'chat_panel'):
            self.chat_panel.raise_()

    # ── File management ───────────────────────────────────────────────────

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
                ext = os.path.splitext(file_path)[1].lower()
                self._apply_editor_mode(editor_to_focus, ext)
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
        return self.tabs.currentWidget()

    def add_new_tab(self, name="Untitled", content="", path=None):
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
        unsaved = any(
            hasattr(self.tabs.widget(i), 'is_dirty') and self.tabs.widget(i).is_dirty()
            for i in range(self.tabs.count())
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

        if event.isAccepted():
            registry.deactivate_all_features()
            self._save_current_session()
            self.settings_manager.set(
                'dock_state', self.saveState().toHex().data().decode()
            )
            self.settings_manager.set(
                'window_geometry', self.saveGeometry().toHex().data().decode()
            )
            if hasattr(self, 'md_preview_dock'):
                self.settings_manager.set(
                    'md_preview_visible', self.md_preview_dock.isVisible()
                )

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

        widget = self.tabs.widget(index)
        if widget:
            widget.deleteLater()
        self.tabs.removeTab(index)
        if self.tabs.count() == 0:
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

            current_text = self.tabs.tabText(index)
            if current_text.endswith("*"):
                self.tabs.setTabText(index, current_text[:-1])

            ext = os.path.splitext(editor.file_path)[1].lower()
            editor.highlighter = registry.get_highlighter(editor.document(), ext)
            self._apply_editor_mode(editor, ext)

            if hasattr(self, 'git_dock'):
                self.git_dock.refresh_status()

            self.statusBar().showMessage(f"Saved: {editor.file_path}", 3000)
            return True
        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"Could not save file: {e}")
            return False

    def _save_current_session(self):
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
            if hasattr(self, 'update_git_branch'):
                self.update_git_branch()

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

    # ── Context building ──────────────────────────────────────────────────

    def estimate_tokens(self, text: str) -> int:
        return len(text) // 4

    def build_chat_context(self, user_text: str, active_code: str) -> str:
        TOKEN_BUDGET = 28000
        used = self.estimate_tokens(user_text)

        memory_ctx = self.memory_manager.build_memory_context(query=user_text)
        used += self.estimate_tokens(memory_ctx)

        active_budget = 6000
        active_chars  = active_budget * 4
        if len(active_code) > active_chars:
            head = active_code[:active_chars // 3]
            tail = active_code[-(active_chars * 2 // 3):]
            active_code_ctx = head + "\n...(truncated)...\n" + tail
        else:
            active_code_ctx = active_code
        used += self.estimate_tokens(active_code_ctx)

        import_ctx = ""
        if used < TOKEN_BUDGET:
            import_budget = TOKEN_BUDGET - used - 8000
            raw_imports   = self.resolve_local_imports(active_code, _max_depth=1)
            import_chars  = import_budget * 4
            import_ctx = (raw_imports[:import_chars] + "\n...(imports truncated)..."
                          if len(raw_imports) > import_chars else raw_imports)
            used += self.estimate_tokens(import_ctx)

        tabs_ctx = ""
        if used < TOKEN_BUDGET:
            tabs_budget = TOKEN_BUDGET - used - 2000
            tabs_chars  = tabs_budget * 4
            raw_tabs    = self.get_open_tabs_context()
            tabs_ctx    = (raw_tabs[:tabs_chars] + "\n...(tabs truncated)..."
                           if len(raw_tabs) > tabs_chars else raw_tabs)
            used += self.estimate_tokens(tabs_ctx)

        tree_ctx = ""
        if used < TOKEN_BUDGET:
            tree_ctx = self.get_project_tree()
            if self.estimate_tokens(tree_ctx) + used > TOKEN_BUDGET:
                tree_ctx = ""

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

    def get_open_tabs_context(self):
        context = []
        current_editor = self.current_editor()
        for i in range(self.tabs.count()):
            editor = self.tabs.widget(i)
            if not editor or not hasattr(editor, 'file_path'):
                continue
            if editor is current_editor or not editor.file_path:
                continue
            content = editor.toPlainText()
            if not content.strip():
                continue
            if len(content) > 1500:
                content = content[:500] + "\n...(truncated)...\n" + content[-1000:]
            rel_path = os.path.relpath(editor.file_path)
            context.append(f"--- Open tab: {rel_path} ---\n```python\n{content}\n```")
        return "[Other Open Files]\n" + "\n\n".join(context) if context else ""

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

    def _on_chat_message(self, user_text: str):
        self._last_user_message = user_text
        self._append_user_message(user_text)

        editor = self.current_editor()
        active_code = editor.toPlainText() if editor else ""
        context = self.build_chat_context(user_text, active_code)
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

    def setup_memory_panel(self):
        self.memory_panel = MemoryPanel(self.memory_manager, self)
        self.memory_panel.restore_conversation_requested.connect(
            self._restore_conversation
        )
        QTimer.singleShot(100, lambda: self.chat_panel.set_memory_widget(
            self.memory_panel
        ))

    def setup_terminal(self):
        self.terminal_dock = TerminalDock(self)
        self.addDockWidget(
            Qt.DockWidgetArea.BottomDockWidgetArea, self.terminal_dock
        )
        if hasattr(self, 'output_dock'):
            self.tabifyDockWidget(self.output_dock, self.terminal_dock)
        self.terminal_dock.hide()

    def toggle_terminal(self):
        if self.terminal_dock.isVisible():
            self.terminal_dock.hide()
        else:
            self.terminal_dock.show()
            self.terminal_dock.raise_()
            term = self.terminal_dock._terminal
            if hasattr(term, 'input_line'):
                term.input_line.setFocus()
            elif hasattr(term, '_term'):
                term._term.setFocus()

    # ── Runner ────────────────────────────────────────────────────────────

    def setup_run_menu(self):
        run_menu = self.menuBar().addMenu("Run")
        run_action = QAction("Run Script", self)
        run_action.setShortcut(QKeySequence("F5"))
        run_action.triggered.connect(self.run_script)
        run_menu.addAction(run_action)

    def setup_view_menu(self):
        view_menu = self.menuBar().addMenu("View")
        panels = [
            ("Chat",             lambda: self.chat_panel.switch_to_chat()),
            ("Memory",           lambda: self.chat_panel.switch_to_memory()),
            ("Terminal",         lambda: self.toggle_terminal()),
            ("Markdown Preview", lambda: (self.md_preview_dock.show(),
                                          self.md_preview_dock.raise_(),
                                          self._refresh_markdown_preview())),
            ("Explorer",         lambda: (self.sidebar_dock.show(),
                                          self.sidebar_dock.raise_())),
            ("Source Control",   lambda: (self.git_dock.show(),
                                          self.git_dock.raise_())),
            ("Output",           lambda: (self.output_dock.show(),
                                          self.output_dock.raise_())),
            ("Find in Files",    lambda: (self.search_dock.show(),
                                          self.search_dock.raise_())),
        ]
        for name, fn in panels:
            action = QAction(name, self)
            action.triggered.connect(fn)
            view_menu.addAction(action)

        toggle_completion = QAction("Toggle In-line Completion", self)
        toggle_completion.setCheckable(True)
        toggle_completion.setChecked(True)
        toggle_completion.toggled.connect(self.toggle_inline_completion)
        view_menu.addAction(toggle_completion)

    def setup_help_menu(self):
        help_menu = self.menuBar().addMenu("Help")
        about_action = QAction("About QuillAI", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

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

    # ── AI loading indicator ──────────────────────────────────────────────

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

        self.timer.start(500)
        editor.clear_ghost_text()

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