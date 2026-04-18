"""
editor/code_editor.py

CodeEditor — main application window.

Behaviour is implemented in focused mixin modules:
  TabMixin        — tab/pane management
  FileMixin       — file open/save/watch
  SessionMixin    — session save/restore
  LspMixin        — LSP setup and wiring
  WikiMixin       — wiki and repo map
  RunMixin        — script execution
  SidebarMixin    — file explorer
  ChatMixin       — chat message handling
  StatusBarMixin  — status bar, AI mode, loading

ChatRenderer (ui/chat_renderer.py) handles chat rendering.
"""

import os
import sys

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QSizePolicy, QApplication,
    QDockWidget, QPlainTextEdit, QFileDialog, QMessageBox,
)
from PyQt6.QtCore import (
    Qt, QTimer, QThread, QDir, QProcess, QFileSystemWatcher,
    pyqtSlot,
)
from PyQt6.QtGui import (
    QAction, QKeySequence, QTextCursor, QIcon, QShortcut, QFont,
)

# ── Core ──────────────────────────────────────────────────────────────────────
from core.plugin_manager import PluginManager
from core.faq_manager import FAQManager
from core.project_settings import ProjectSettings

# ── AI ────────────────────────────────────────────────────────────────────────
from ai.worker import AIWorker
from ai.context_engine import ContextEngine
from ai.lsp_manager import LSPManager
from ai.lsp_context import LSPContextProvider
from ai.llm_fn import make_llm_fn

# ── UI ────────────────────────────────────────────────────────────────────────
from ui.theme import (
    apply_theme, get_theme, theme_signals,
    build_status_bar_stylesheet, build_editor_stylesheet,
    build_dock_stylesheet, build_tab_widget_stylesheet,
    build_output_panel_stylesheet, build_explain_error_btn_stylesheet,
    build_tree_view_stylesheet,
)
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
from ui.log_viewer import LogViewerDock
from ui.status_bar_buttons import (
    setup_ins_ovr_btn, setup_indent_btn,
    setup_encoding_btn, setup_lineending_btn, setup_filetype_btn,
)

# ── Editor ────────────────────────────────────────────────────────────────────
from editor.ghost_editor import GhostEditor
from editor.highlighter import registry

# ── Mixins ────────────────────────────────────────────────────────────────────
from editor.tab_mixin     import TabMixin
from editor.file_mixin    import FileMixin
from editor.session_mixin import SessionMixin
from editor.lsp_mixin     import LspMixin
from editor.wiki_mixin    import WikiMixin
from editor.run_mixin     import RunMixin
from ui.sidebar_mixin     import SidebarMixin
from ui.chat_mixin        import ChatMixin, _query_wants_diff
from ui.status_bar_mixin  import StatusBarMixin

MAX_FILE_SIZE = 6000


class CodeEditor(
    QMainWindow, ChatRenderer,
    TabMixin, FileMixin, SessionMixin,
    LspMixin, WikiMixin, RunMixin,
    SidebarMixin, ChatMixin, StatusBarMixin,
):
    def __init__(self):
        super().__init__()

        # ── 1. Settings ───────────────────────────────────────────────
        self.settings_manager = SettingsManager()

        # ── 2. Memory / FAQ ───────────────────────────────────────────
        _llm_fn = make_llm_fn(self.settings_manager)
        self.memory_manager  = MemoryManager(llm_fn=_llm_fn)
        self.faq_manager     = FAQManager(project_path=None, llm_fn=_llm_fn)
        self.project_settings = ProjectSettings()
        self.intent_tracker  = init_tracker(self.memory_manager)

        # ── 3. LSP / Repo map placeholders ────────────────────────────
        self.lsp_manager          = None
        self.lsp_context_provider = None
        self._start_lsp()
        self.repo_map     = None
        self.wiki_indexer = None

        # ── 4. App state ──────────────────────────────────────────────
        self.setWindowTitle("QuillAI")
        try:
            icon_path = os.path.join(
                os.path.dirname(__file__), "..", "images", "quillai_logo_min.svg"
            )
            if os.path.exists(icon_path):
                self.setWindowIcon(QIcon(icon_path))
        except Exception:
            pass

        self._is_loading              = False
        self.inline_completion_enabled = True
        self.current_error_text        = ""
        self._terminal_output_buffer: list[str] = []
        self._terminal_error_text      = ""
        self.current_ai_raw_text       = ""
        self._stream_start_pos         = 0
        self._stream_buffer            = ""
        self._ai_response_buffer       = ""
        self._last_user_message        = ""
        self._agent_session_active     = False
        self._agent_history: list      = []
        self.last_worker               = None
        self.chat_worker               = None
        self.active_threads            = []

        # ── 5. File watcher ───────────────────────────────────────────
        self._file_watcher = QFileSystemWatcher(self)
        self._file_watcher.fileChanged.connect(self._on_file_changed_externally)
        self._watch_debounce: dict[str, QTimer] = {}

        # ── 6. Autosave ───────────────────────────────────────────────
        self.autosave_manager = AutosaveManager(
            get_editors_fn = self._get_all_editors_indexed,
            status_fn      = lambda msg, ms: self.statusBar().showMessage(msg, ms),
        )
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setInterval(AUTOSAVE_INTERVAL_MS)
        self._autosave_timer.timeout.connect(self.autosave_manager.save_all)
        self._autosave_timer.start()

        # ── 7. Tab / split container ──────────────────────────────────
        self.split_container = SplitContainer()
        self.split_container.pane_activated.connect(self._on_active_pane_changed)
        self.split_container.tab_close_requested.connect(self._on_pane_tab_close)
        self.split_container.current_changed.connect(self._on_pane_current_changed)
        self.tabs = self.split_container.active_pane()

        # ── 8. Central layout ─────────────────────────────────────────
        self.central_container = QWidget()
        self.central_layout    = QVBoxLayout(self.central_container)
        self.central_layout.setContentsMargins(0, 0, 0, 0)
        self.central_layout.setSpacing(0)
        self.find_replace_panel = FindReplaceWidget(self)
        self.find_replace_panel.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.find_replace_panel.hide()
        self.central_layout.addWidget(self.find_replace_panel)
        self.central_layout.addWidget(self.split_container)
        self.setCentralWidget(self.central_container)

        # ── 9. Shortcuts ──────────────────────────────────────────────
        QShortcut(QKeySequence("Ctrl+F"),       self).activated.connect(self.show_find_replace)
        QShortcut(QKeySequence("Ctrl+H"),       self).activated.connect(self.show_find_replace)
        QShortcut(QKeySequence("Ctrl+Shift+F"), self).activated.connect(self.show_project_search)
        QShortcut(QKeySequence("Ctrl+Space"),   self).activated.connect(self.request_manual_completion)
        QShortcut(QKeySequence("Ctrl+Shift+W"), self).activated.connect(self._close_active_pane)
        QShortcut(QKeySequence("Ctrl+K, Left"), self).activated.connect(
            lambda: self._focus_adjacent_pane(-1))
        QShortcut(QKeySequence("Ctrl+K, Right"), self).activated.connect(
            lambda: self._focus_adjacent_pane(1))

        # ── 10. Menus + plugins ───────────────────────────────────────
        setup_menus(self)
        self.plugin_manager = PluginManager(self)

        # ── 11. Status bar ────────────────────────────────────────────
        self.status_bar = self.statusBar()
        self.status_bar.setSizeGripEnabled(False)
        self.status_bar.setStyleSheet(build_status_bar_stylesheet(get_theme()))

        self.branch_label = QLabel("")
        self.status_bar.addWidget(self.branch_label)
        sep = QLabel("|")
        sep.setStyleSheet("color: rgba(255,255,255,0.3); padding: 0 2px;")
        self.status_bar.addWidget(sep)

        self._startup         = StartupProgress(self.status_bar, parent=self)
        self.cursor_label     = QLabel("Ln 1, Col 1")
        self.filetype_btn     = setup_filetype_btn(self)
        self.indent_btn       = setup_indent_btn(self)
        self.encoding_btn     = setup_encoding_btn(self)
        self.lineending_btn   = setup_lineending_btn(self)
        self.ins_ovr_btn      = setup_ins_ovr_btn(self)
        for w in (self.cursor_label, self.filetype_btn, self.indent_btn,
                  self.encoding_btn, self.lineending_btn, self.ins_ovr_btn):
            self.status_bar.addPermanentWidget(w)
        # Legacy aliases
        self.filetype_label   = self.filetype_btn
        self.indent_label     = self.indent_btn
        self.encoding_label   = self.encoding_btn
        self.lineending_label = self.lineending_btn

        self.ai_mode_btn = QPushButton("\U0001f3e0 LOCAL")
        self.ai_mode_btn.setCheckable(False)
        self.ai_mode_btn.setFlat(True)
        self.ai_mode_btn.setFixedWidth(110)
        self.ai_mode_btn.clicked.connect(self.toggle_ai_mode)
        self.update_mode_label(self.settings_manager.get_backend())

        self.terminal_error_btn = QPushButton("\U0001f4a1 Terminal Error")
        self.terminal_error_btn.setFlat(True)
        self.terminal_error_btn.setFixedWidth(130)
        self.terminal_error_btn.setVisible(False)
        self.terminal_error_btn.clicked.connect(self._explain_terminal_error)

        self.status_bar.addPermanentWidget(self.terminal_error_btn)
        self.status_bar.addPermanentWidget(self.ai_mode_btn)
        self.hide_loading_indicator()

        # ── 12. Panels and docks ──────────────────────────────────────
        self.setup_sidebar()
        self.setup_git_panel()
        self.setup_output_panel()
        self.setup_chat_panel()
        self.setup_memory_panel()
        self.setup_find_in_files_panel()

        # ── 13. Plugins + languages ───────────────────────────────────
        self.plugin_manager.discover_and_load(
            os.path.join(os.path.dirname(__file__), "..", "plugins", "features")
        )
        registry.auto_register_languages(
            os.path.join(os.path.dirname(__file__), "..", "plugins", "languages")
        )

        # ── 14. Command palette ───────────────────────────────────────
        self.command_palette = CommandPalette(self)

        # ── 15. Theme + terminal events ───────────────────────────────
        theme_signals.theme_changed.connect(self._apply_theme_to_widgets)
        from core.events import EVT_TERMINAL_OUTPUT
        self.plugin_manager.subscribe(EVT_TERMINAL_OUTPUT, self._on_terminal_output)

        # ── 16. Process (run script) ──────────────────────────────────
        self.process = QProcess(self)
        self.process.readyReadStandardOutput.connect(self.handle_stdout)
        self.process.readyReadStandardError.connect(self.handle_stderr)
        self.process.finished.connect(self.process_finished)

        # ── 17. Language detect timer ─────────────────────────────────
        self._lang_detect_timer = QTimer(self)
        self._lang_detect_timer.setSingleShot(True)
        self._lang_detect_timer.timeout.connect(self._fire_ai_lang_detect)
        self._lang_detect_running = False

        # ── 18. Restore ───────────────────────────────────────────────
        self._restore_window_state()
        self._restore_session()

        self.wiki_manager         = None
        self.wiki_context_builder = None
        self.wiki_watcher         = None

        project_root = (
            self.git_dock.repo_path
            if hasattr(self, "git_dock") and self.git_dock.repo_path
            else None
        )
        if project_root:
            self._init_wiki(project_root)

    # ── Methods that don't fit cleanly in a single mixin ─────────────────────

    def _update_window_title(self, project_path: str = None):
        if project_path:
            self.setWindowTitle(f"QuillAI — {os.path.basename(project_path)}")
        else:
            self.setWindowTitle("QuillAI")

    def estimate_tokens(self, text: str) -> int:
        return len(text) // 4

    def get_project_tree(self):
        root = (self.git_dock.repo_path
                if hasattr(self, "git_dock") and self.git_dock.repo_path
                else QDir.currentPath())
        return root

    def _apply_theme_to_widgets(self, t: dict):
        self.status_bar.setStyleSheet(build_status_bar_stylesheet(t))
        for pane in self.split_container.all_panes():
            pane.setStyleSheet(build_tab_widget_stylesheet(t))
        self.output_editor.setStyleSheet(build_output_panel_stylesheet(t))
        self.explain_error_btn.setStyleSheet(build_explain_error_btn_stylesheet(t))
        self.tree_view.setStyleSheet(build_tree_view_stylesheet(t))
        dock_style = build_dock_stylesheet(t)
        for dock in (self.sidebar_dock, self.output_dock, self.search_dock):
            dock.setStyleSheet(dock_style)
        for label, (dock_attr, _) in self.plugin_manager.docks.items():
            dock = getattr(self, dock_attr, None)
            if dock:
                dock.setStyleSheet(dock_style)
        self.file_model._rebuild_icons(t)
        self.tree_view.viewport().update()
        for _, editor in self.split_container.all_editors():
            if hasattr(editor, "file_path") and editor.file_path:
                ext = os.path.splitext(editor.file_path)[1].lower()
                editor.highlighter = registry.get_highlighter(editor.document(), ext)

    def closeEvent(self, event):
        self.autosave_manager.save_all()
        if hasattr(self, "lsp_manager") and self.lsp_manager:
            self.lsp_manager.stop()
        unsaved = any(
            hasattr(e, "is_dirty") and e.is_dirty()
            for _, e in self.split_container.all_editors()
        )
        if unsaved:
            from PyQt6.QtWidgets import QMessageBox
            reply = QMessageBox.question(
                self, "Unsaved Changes",
                "You have unsaved files. Save before exiting?",
                QMessageBox.StandardButton.SaveAll |
                QMessageBox.StandardButton.Discard |
                QMessageBox.StandardButton.Cancel,
            )
            if reply == QMessageBox.StandardButton.SaveAll:
                for pane in self.split_container.all_panes():
                    self.tabs = pane
                    for i in range(pane.count()):
                        e = pane.widget(i)
                        if hasattr(e, "is_dirty") and e.is_dirty():
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
                "dock_state", self.saveState().toHex().data().decode()
            )
            self.settings_manager.set(
                "window_geometry", self.saveGeometry().toHex().data().decode()
            )
            if hasattr(self, "md_preview_dock") and self.md_preview_dock:
                self.settings_manager.set(
                    "md_preview_visible", self.md_preview_dock.isVisible()
                )
            plugin_dock_state = {}
            for label, (dock_attr, _) in self.plugin_manager.docks.items():
                dock = getattr(self, dock_attr, None)
                if dock:
                    plugin_dock_state[dock_attr] = dock.isVisible()
            self.settings_manager.set("plugin_dock_state", plugin_dock_state)
            for plugin in self.plugin_manager._plugins:
                try:
                    plugin.deactivate()
                except Exception as e:
                    print(f"[PluginManager] Error deactivating {plugin.name}: {e}")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "chat_panel"):
            status_bar_height = self.statusBar().height()
            menu_bar_height   = self.menuBar().height() if self.menuBar() else 0
            h = self.height() - status_bar_height - menu_bar_height
            self.chat_panel.setFixedHeight(max(h, 100))
            self.chat_panel.move(
                self.width() - self.chat_panel.width() - 0,
                menu_bar_height,
            )

    # ── Remaining small methods that reference multiple mixins ────────────────

    def show_find_replace(self):
        self.find_replace_panel.show()
        self.find_replace_panel.focus_find()

    def show_project_search(self):
        if hasattr(self, "search_dock"):
            self.search_dock.show()
            self.search_dock.raise_()

    def show_settings_dialog(self):
        from ui.settings_dialog import SettingsDialog
        dialog = SettingsDialog(
            self.settings_manager, self,
            project_settings=getattr(self, "project_settings", None),
        )
        dialog.exec()

    def _show_about(self):
        AboutDialog(self).exec()

    def toggle_inline_completion(self, enabled):
        self.inline_completion_enabled = enabled

    def _transform_case(self, mode: str):
        editor = self.current_editor()
        if not editor:
            return
        cursor = editor.textCursor()
        if not cursor.hasSelection():
            return
        text = cursor.selectedText()
        cursor.insertText(
            text.upper() if mode == "upper" else
            text.lower() if mode == "lower" else
            text.title()
        )

    def _sort_lines(self, reverse: bool = False):
        editor = self.current_editor()
        if not editor:
            return
        cursor = editor.textCursor()
        if not cursor.hasSelection():
            return
        lines = cursor.selectedText().split("\u2029")
        lines.sort(key=str.casefold, reverse=reverse)
        cursor.insertText("\u2029".join(lines))

    def _toggle_show_whitespace(self):
        editor = self.current_editor()
        if editor and hasattr(editor, "toggle_show_whitespace"):
            editor.toggle_show_whitespace()

# ── Panel setup ───────────────────────────────────────────────────────────

    def setup_chat_panel(self):
        from ui.sliding_chat_panel import SlidingPanel
        from PyQt6.QtGui import QTextCursor
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

    def setup_output_panel(self):
        from PyQt6.QtWidgets import (QDockWidget, QWidget, QVBoxLayout,
                                      QHBoxLayout, QPlainTextEdit, QPushButton)
        from ui.theme import (get_theme, build_dock_stylesheet,
                              build_output_panel_stylesheet,
                              build_explain_error_btn_stylesheet)
        from PyQt6.QtCore import Qt
        output_container = QWidget()
        layout = QVBoxLayout(output_container)
        layout.setContentsMargins(0, 0, 0, 0)
        self.output_editor = QPlainTextEdit()
        self.output_editor.setReadOnly(True)
        self.output_editor.setStyleSheet(build_output_panel_stylesheet(get_theme()))
        self.explain_error_btn = QPushButton("\U0001f4a1 Explain Error")
        self.explain_error_btn.setStyleSheet(
            build_explain_error_btn_stylesheet(get_theme()))
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

    def setup_find_in_files_panel(self):
        from PyQt6.QtWidgets import QDockWidget
        from PyQt6.QtCore import Qt
        from ui.theme import get_theme, build_dock_stylesheet
        from ui.find_in_files import FindInFilesWidget
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
        if hasattr(self, "output_dock"):
            self.tabifyDockWidget(self.output_dock, self.search_dock)
        self.search_dock.hide()

    def setup_memory_panel(self):
        from PyQt6.QtCore import QTimer
        from ui.memory_panel import MemoryPanel
        self.memory_panel = MemoryPanel(self.memory_manager, self)
        self.memory_panel.restore_conversation_requested.connect(
            self._restore_conversation
        )
        QTimer.singleShot(100, lambda: self.chat_panel.set_memory_widget(
            self.memory_panel
        ))
        from ui.faq_panel import FAQPanel
        faq_widget = FAQPanel(self.faq_manager, self)
        QTimer.singleShot(100, lambda: self.chat_panel.set_faq_widget(faq_widget))

    # ── Language detection ────────────────────────────────────────────────────

    def detect_language_from_content(self, text: str) -> str:
        import re
        if not text.strip() or len(text) < 20:
            return ""
        first_line = text.split("\n")[0].strip()
        shebang_map = {
            "python": ".py", "node": ".js", "bash": ".sh",
            "sh": ".sh", "ruby": ".rb", "perl": ".pl", "php": ".php",
        }
        if first_line.startswith("#!"):
            for key, ext in shebang_map.items():
                if key in first_line:
                    return ext
        checks = [
            (r"^(import|from)\s+\w+|^def \w+\(|^class \w+\s*[:(]|^@\w+", ".py"),
            (r"^---\s*$|^-\s+name:\s|^hosts:\s|^tasks:\s|^\s+ansible\.",   ".yml"),
            (r"interface\s+\w+\s*\{|:\s*(string|number|boolean|any)\b",     ".ts"),
            (r"\b(const|let|var)\s+\w+\s*=|=>\s*\{|require\s*\(",         ".js"),
            (r"<html|<!DOCTYPE|<head>|<body>|<div",                                 ".html"),
            (r"nixpkgs|mkShell|buildInputs|stdenv\.mkDerivation",                 ".nix"),
            (r"^#{1,6}\s\w|\*\*\w+\*\*|\[.+\]\(https?://",             ".md"),
            (r"^\s*(if|for|while|case)\s+.*;\s*(then|do)\b|^\s*fi\b",       ".sh"),
            (r"^\s*(?:use\s+strict|sub\s+\w+\s*\{|my\s+\$\w+)",         ".pl"),
        ]
        for pattern, ext in checks:
            if re.search(pattern, text, re.MULTILINE):
                return ext
        return ""

    def _ai_detect_language(self, text: str):
        import re
        from PyQt6.QtCore import QThread
        from editor.highlighter import registry
        editor = self.current_editor()
        if not editor or editor.file_path:
            return
        if getattr(self, "_lang_detect_running", False):
            return
        self._lang_detect_running = True
        snippet = text[:800]
        prompt  = (
            "Identify the programming language of the following code snippet. "
            "Reply with ONLY a single file extension including the dot, "
            "for example: .py  .js  .ts  .sh  .yml  .html  .nix  .md\n"
            "If you cannot determine the language, reply with: unknown\n\n"
            f"```\n{snippet}\n```"
        )
        thread     = QThread()
        worker     = self.create_worker(prompt=prompt, is_chat=False)
        result_buf = []
        worker.moveToThread(thread)

        def on_update(t):
            result_buf.append(t)

        def on_finished():
            self._lang_detect_running = False
            raw   = "".join(result_buf).strip().lower()
            match = re.search(r"\.[a-z]+", raw)
            if not match:
                return
            ext = match.group(0)
            if ext not in registry.registered_extensions:
                return
            ce = self.current_editor()
            if not ce or ce.file_path:
                return
            if ext != getattr(ce, "_detected_ext", ""):
                ce._detected_ext = ext
                ce.highlighter   = registry.get_highlighter(ce.document(), ext)
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

    # ── Markdown preview ──────────────────────────────────────────────────────

    def _refresh_markdown_preview(self, editor=None):
        if editor is None:
            editor = self.current_editor()
        if not editor:
            return
        path = getattr(editor, "file_path", "") or ""
        if not path.lower().endswith((".md", ".markdown")):
            return
        self.plugin_manager.emit("file_opened", path=path, editor=editor)

    def _sync_markdown_scroll(self):
        editor = self.current_editor()
        if not editor:
            return
        path = getattr(editor, "file_path", "") or ""
        if not path.lower().endswith((".md", ".markdown")):
            return
        first_visible = editor.firstVisibleBlock().blockNumber()
        total_lines   = editor.document().blockCount()
        self.plugin_manager.emit("editor_scrolled",
                                 first_visible=first_visible,
                                 total_lines=total_lines)

    # ── Import resolution ─────────────────────────────────────────────────────

    def resolve_local_imports(self, code_text, _visited=None, _depth=0, _max_depth=3):
        import ast as _ast, os
        if _visited is None:
            _visited = set()
        if _depth >= _max_depth:
            return ""
        editor = self.current_editor()
        if not editor:
            return ""
        try:
            tree = _ast.parse(code_text)
        except Exception:
            return ""
        if hasattr(self, "tree_view") and self.file_model:
            project_root = self.file_model.filePath(self.tree_view.rootIndex())
        elif editor.file_path:
            project_root = os.path.dirname(editor.file_path)
        else:
            return ""
        imported_context = []
        MAX_FILE_SIZE = 6000
        for node in _ast.walk(tree):
            modules = []
            if isinstance(node, _ast.ImportFrom) and node.module:
                modules.append(node.module)
            elif isinstance(node, _ast.Import):
                for alias in node.names:
                    modules.append(alias.name)
            for mod in modules:
                rel_path        = mod.replace(".", os.sep) + ".py"
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
                        content      = open(full_path, "r", encoding="utf-8").read()
                        display_path = os.path.relpath(full_path, project_root)
                        if len(content) > MAX_FILE_SIZE:
                            content = content[:500] + "\n...(truncated)...\n" + content[-1000:]
                        imported_context.append(
                            f"\n--- Imported file: {display_path} (depth {_depth+1}) ---\n"
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

    # ── Misc ──────────────────────────────────────────────────────────────────

    def handle_editor_error_help(self, error_msg, code, line_num):
        self.chat_panel.expand()
        self.chat_panel.switch_to_chat()
        user_text = (
            f"I have a SyntaxError on line {line_num}: {error_msg}. "
            "Can you help me fix it?"
        )
        self._on_chat_message(user_text)

    def ask_ai(self):
        from PyQt6.QtCore import QThread
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
        cross_file = self.resolve_local_imports(text)
        lang       = "code"
        if editor.file_path:
            ext_map = {
                ".py": "Python", ".sh": "Bash", ".bash": "Bash",
                ".yml": "YAML", ".yaml": "YAML", ".nix": "Nix",
                ".html": "HTML", ".js": "JavaScript", ".ts": "TypeScript",
            }
            for ext, name in ext_map.items():
                if editor.file_path.lower().endswith(ext):
                    lang = name
                    break
        current_symbol = self.intent_tracker.get_current_symbol(text, cursor_pos)
        if current_symbol:
            self.intent_tracker.record_cursor_symbol(current_symbol)
        intent_ctx = self.intent_tracker.build_intent_context(
            current_file_path=editor.file_path or "", language=lang,
        )
        prompt = (
            f"{intent_ctx}\n{cross_file}\n"
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

    def load_snippet_to_chat(self, text: str):
        """Pre-fill the chat input with text."""
        if hasattr(self, "chat_input"):
            self.chat_input.setPlainText(text)
            self.chat_input.setFocus()
        if hasattr(self, "chat_panel"):
            self.chat_panel.expand()
            self.chat_panel.switch_to_chat()

    def create_worker(self, prompt, editor_text="", cursor_pos=0,
                      generate_function=False, is_edit=False, is_chat=False):
        from ai.worker import AIWorker
        backend  = self.settings_manager.get_backend()
        model    = (self.settings_manager.get_active_model() if is_chat
                    else self.settings_manager.get_inline_model())
        api_key  = self.settings_manager.get_api_key()
        wiki_ctx = ""
        if not is_chat and hasattr(self, "wiki_context_builder") and self.wiki_context_builder:
            editor = self.current_editor()
            fp = getattr(editor, "file_path", None) if editor else None
            if fp:
                from pathlib import Path as _Path
                wiki_ctx = self.wiki_context_builder.for_file(_Path(fp))
        context_obj = {
            "prompt": prompt, "editor_text_len": len(editor_text) if editor_text else 0,
            "cursor_pos": cursor_pos, "generate_function": generate_function,
            "is_edit": is_edit, "is_chat": is_chat, "backend": backend,
            "model": model, "wiki_context_len": len(wiki_ctx), "has_wiki": bool(wiki_ctx),
        }
        if hasattr(self, "plugin_manager"):
            self.plugin_manager.emit("context_built", context=context_obj, prompt=prompt)
        return AIWorker(
            prompt=prompt, editor_text=editor_text, cursor_pos=cursor_pos,
            generate_function=generate_function, is_edit=is_edit, is_chat=is_chat,
            model=model, api_url=self.settings_manager.get_llm_url(),
            api_key=api_key, backend=backend, wiki_context=wiki_ctx,
        )
