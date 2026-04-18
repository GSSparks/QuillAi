"""
ui/chat_mixin.py

ChatMixin — _on_chat_message, _relaunch_as_agent, agent session management.
Mixed into CodeEditor.
"""

import os
import re
from pathlib import Path

from PyQt6.QtCore import Qt, QThread


# Phrases that indicate the user wants git diff context
_DIFF_TRIGGERS = [
    "what did i change", "what have i changed", "my changes",
    "recent changes", "what changed", "diff",
    "why did i break", "why is it broken", "what broke",
    "review my", "review the change", "look at my change",
    "bug i introduced", "regression", "since my last",
    "what i modified", "what was modified", "uncommitted",
    "staged", "unstaged", "working tree",
    "just added", "just changed", "just modified",
    "i added", "i changed", "i modified", "i wrote",
    "not working after", "stopped working", "broke after",
    "something i did", "error after", "failing after",
]


def _query_wants_diff(text: str) -> bool:
    t = text.lower()
    return any(trigger in t for trigger in _DIFF_TRIGGERS)


class ChatMixin:

    def _on_chat_message(self, user_text: str):
        # Check if this is an editor write request
        from ai.ai_editor_worker import wants_editor_write
        editor = self.current_editor()
        if (editor and editor.file_path
                and wants_editor_write(user_text)):
            self._launch_ai_editor(user_text)
            return

        self._last_user_message = user_text
        self._append_user_message(user_text)
        self.memory_manager.add_turn("user", user_text)

        editor      = self.current_editor()
        active_code = editor.toPlainText() if editor else ""
        file_path   = getattr(editor, "file_path", None)

        if not hasattr(self, "context_engine"):
            from ai.context_engine import ContextEngine
            self.context_engine = ContextEngine(
                memory_manager    = self.memory_manager,
                estimate_tokens_fn= self.estimate_tokens,
                settings_manager  = self.settings_manager,
            )

        def _launch(lsp_ctx):
            gitlab_ctx = ""
            if (file_path and ".gitlab-ci.yml" in file_path
                    and hasattr(self, "gitlab_dock") and self.gitlab_dock):
                gitlab_ctx = self._get_gitlab_pipeline_context()

            faq_ctx = ""
            if hasattr(self, "faq_manager") and self.faq_manager:
                faq_ctx = self.faq_manager.build_context(user_text)

            symbol_ctx = ""
            if (hasattr(self, "wiki_context_builder")
                    and self.wiki_context_builder
                    and self.wiki_context_builder._repo_map):
                from core.wiki_context_builder import _extract_symbol_names
                for sym in _extract_symbol_names(user_text):
                    for rel in self.wiki_context_builder._repo_map.find_symbol(sym):
                        block = self.wiki_context_builder._repo_map.get_symbol_source(rel, sym)
                        if block:
                            symbol_ctx += block + "\n\n"
                            break

            wiki_ctx = ""
            if (hasattr(self, "wiki_context_builder")
                    and self.wiki_context_builder and file_path):
                wiki_ctx = self.wiki_context_builder.for_prompt(
                    user_text, source_path=Path(file_path)
                )

            context = self.context_engine.build(
                user_text   = user_text,
                active_code = active_code,
                file_path   = file_path,
                open_tabs   = self.get_open_editors(),
                cursor_pos  = None,
                lsp_context = lsp_ctx,
                repo_map    = (self.repo_map.get_context(user_text)
                               if self.repo_map else None),
            )

            diff_block = ""
            if (hasattr(self, "git_dock") and self.git_dock
                    and self.git_dock.repo_path
                    and _query_wants_diff(user_text)):
                diff = self.git_dock.get_current_diff(cap=3000)
                if diff:
                    diff_block = f"\n\n[Recent Changes]\n```diff\n{diff}\n```"

            faq_block    = f"\n\n{faq_ctx}"    if faq_ctx    else ""
            gitlab_block = f"\n\n{gitlab_ctx}" if gitlab_ctx else ""
            symbol_block = symbol_ctx + "\n\n"  if symbol_ctx else ""

            prompt_with_context = (
                f"{user_text}\n\n"
                f"{symbol_block}{context}{faq_block}{gitlab_block}{diff_block}"
            )

            self._ai_response_buffer      = ""
            self.current_ai_raw_text      = ""
            self._last_prompt_with_context = prompt_with_context

            if getattr(self, "_agent_session_active", False):
                self._relaunch_as_agent(user_text)
                return

            thread = QThread()
            self.chat_worker = self.create_worker(
                prompt=prompt_with_context, is_chat=True
            )
            self.chat_worker.moveToThread(thread)
            self.chat_worker.chat_update.connect(
                self.append_chat_stream, Qt.ConnectionType.QueuedConnection)
            self.chat_worker.finished.connect(
                self.chat_stream_finished, Qt.ConnectionType.QueuedConnection)
            self.chat_worker.finished.connect(thread.quit)
            self.chat_worker.finished.connect(self.chat_worker.deleteLater)
            thread.finished.connect(thread.deleteLater)
            self.show_loading_indicator()
            self.chat_worker.finished.connect(
                self.hide_loading_indicator, Qt.ConnectionType.QueuedConnection)
            self.active_threads.append(thread)
            thread.finished.connect(
                lambda: self.active_threads.remove(thread)
                if thread in self.active_threads else None
            )
            thread.started.connect(self.chat_worker.run)
            thread.start()

        line, col = (
            editor.cursor_lsp_position()
            if editor and hasattr(editor, "cursor_lsp_position") else (0, 0)
        )
        if (self.lsp_context_provider and editor and file_path
                and self.lsp_manager and self.lsp_manager.is_supported(file_path)):
            self.lsp_context_provider.fetch(file_path, line, col, callback=_launch)
        else:
            _launch({})

    def _relaunch_as_agent(self, user_text: str):
        self._agent_session_active = True
        from ai.agent_worker import AgentWorker

        root    = (self.git_dock.repo_path
                   if hasattr(self, "git_dock") and self.git_dock.repo_path
                   else os.getcwd())
        context = getattr(self, "_last_prompt_with_context", user_text)
        thread  = QThread()
        worker  = AgentWorker(
            user_text        = user_text,
            context          = context,
            project_root     = root,
            model            = self.settings_manager.get_active_model(),
            api_url          = self.settings_manager.get_llm_url(),
            api_key          = self.settings_manager.get_api_key(),
            backend          = self.settings_manager.get_backend(),
            repo_map         = getattr(self, "repo_map", None),
            settings_manager = self.settings_manager,
            plugin_manager   = self.plugin_manager,
            prior_messages   = getattr(self, "_agent_history", []),
        )
        self.chat_worker = worker
        worker.moveToThread(thread)
        worker.chat_update.connect(
            self.append_chat_stream, Qt.ConnectionType.QueuedConnection)
        worker.history_ready.connect(
            lambda msgs: setattr(self, "_agent_history", msgs),
            Qt.ConnectionType.QueuedConnection)
        worker.tool_status.connect(
            self.append_agent_status, Qt.ConnectionType.QueuedConnection)
        worker.write_ops.connect(
            self._on_agent_write_ops, Qt.ConnectionType.QueuedConnection)
        worker.finished.connect(
            lambda: setattr(self, "_skip_stream_finished", True))
        worker.finished.connect(
            self.chat_stream_finished, Qt.ConnectionType.QueuedConnection)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        self.show_loading_indicator()
        worker.finished.connect(
            self.hide_loading_indicator, Qt.ConnectionType.QueuedConnection)
        self.active_threads.append(thread)
        thread.finished.connect(
            lambda: self.active_threads.remove(thread)
            if thread in self.active_threads else None
        )
        thread.started.connect(worker.run)
        thread.start()

    def _get_gitlab_pipeline_context(self) -> str:
        try:
            plugin = getattr(self, "gitlab_dock", None)
            if not plugin:
                return ""
            pipelines = getattr(plugin, "_pipelines", [])
            if not pipelines:
                return ""
            from plugins.features.gitlab_ci.client import format_pipeline_summary
            return f"[Last Pipeline Run]\n{format_pipeline_summary(pipelines[0])}"
        except Exception as e:
            print(f"[GitLab] context error: {e}")
            return ""

    def _launch_ai_editor(self, user_text: str):
        """Launch AIEditorWorker to stream code directly into the editor."""
        from ai.ai_editor_worker import AIEditorWorker
        from PyQt6.QtCore import QThread, Qt

        editor = self.current_editor()
        if not editor:
            return

        file_content = editor.toPlainText()
        file_path    = editor.file_path or ""

        # Show "AI is typing..." indicator
        self._show_ai_typing_indicator(user_text)

        import threading
        from PyQt6.QtCore import QTimer

        worker = AIEditorWorker(
            user_request = user_text,
            file_content = file_content,
            file_path    = file_path,
            model        = self.settings_manager.get_active_model(),
            api_url      = self.settings_manager.get_llm_url(),
            api_key      = self.settings_manager.get_api_key(),
            backend      = self.settings_manager.get_backend(),
        )
        self._ai_editor_worker = worker  # prevent GC

        def on_insertion_ready(pos):
            QTimer.singleShot(0, lambda: (
                self.current_editor().start_ai_cursor(pos)
                if self.current_editor() else None
            ))

        def on_chunk(text):
            QTimer.singleShot(0, lambda t=text: (
                self.current_editor().insert_ai_chunk(t)
                if self.current_editor() else None
            ))

        def on_finished():
            def _done():
                ed = self.current_editor()
                if ed:
                    ed.stop_ai_cursor()
                self._hide_ai_typing_indicator()
                self.append_chat_stream("\n\u2713 Done \u2014 code inserted.")
                self.chat_stream_finished()
            QTimer.singleShot(0, _done)

        def on_error(msg):
            def _err():
                ed = self.current_editor()
                if ed:
                    ed.stop_ai_cursor()
                self._hide_ai_typing_indicator()
                self.statusBar().showMessage(f"AI editor error: {msg}", 5000)
            QTimer.singleShot(0, _err)

        worker.insertion_ready.connect(on_insertion_ready)
        worker.chunk_ready.connect(on_chunk)
        worker.finished.connect(on_finished)
        worker.error.connect(on_error)

        def _run():
            worker._run_impl()

        self._ai_editor_thread = threading.Thread(target=_run, daemon=True)
        self._ai_editor_thread.start()
    def _show_ai_typing_indicator(self, user_text: str):
        """Show iMessage-style 'AI is typing...' indicator in the chat."""
        self._append_user_message(user_text)
        # Animate dots in status bar
        if not hasattr(self, "_ai_typing_timer"):
            from PyQt6.QtCore import QTimer
            self._ai_typing_timer  = QTimer(self)
            self._ai_typing_dots   = 0
            self._ai_typing_timer.timeout.connect(self._tick_ai_typing)
        self._ai_typing_dots = 0
        self._ai_typing_timer.start(400)
        self.statusBar().showMessage("AI is typing·", 0)

    def _tick_ai_typing(self):
        self._ai_typing_dots = (self._ai_typing_dots + 1) % 4
        dots = "·" * (self._ai_typing_dots + 1)
        self.statusBar().showMessage(f"AI is typing{dots}", 0)

    def _hide_ai_typing_indicator(self):
        if hasattr(self, "_ai_typing_timer"):
            self._ai_typing_timer.stop()
        self.statusBar().showMessage("", 0)
