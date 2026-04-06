"""
plugins/features/run_analyzer/main.py

Run Analyzer plugin — watches terminal output, surfaces errors,
indexes failures into vector memory, and offers AI-assisted fixes.
"""

import os
from PyQt6.QtCore import Qt, QTimer
from core.plugin_base import FeaturePlugin
from core.events import (
    EVT_TERMINAL_OUTPUT, EVT_PROJECT_OPENED,
    EVT_RUN_FAILURE, EVT_RUN_COMPLETE,
)
from plugins.features.run_analyzer.analyzer import RunAnalyzer
from plugins.features.run_analyzer.panel import RunAnalyzerPanel
from plugins.features.run_analyzer.parsers import RunEvent, Severity


class RunAnalyzerPlugin(FeaturePlugin):
    name = "run_analyzer"
    description = "Parses Ansible/Terraform output, surfaces errors, AI-assisted fixes"
    enabled = True

    def activate(self):
        self._panel = RunAnalyzerPanel(self.app)
        self.app.run_analyzer_dock = self._panel
        self.app.addDockWidget(
            Qt.DockWidgetArea.BottomDockWidgetArea, self._panel
        )

        # Tabify with output dock if present
        if hasattr(self.app, 'output_dock'):
            self.app.tabifyDockWidget(self.app.output_dock, self._panel)

        self._panel.hide()

        self.app.plugin_manager.register_dock(
            "Run Analyzer", "run_analyzer_dock"
        )

        self._analyzer = RunAnalyzer(
            on_event    = self._on_run_event,
            on_failure  = self._on_failure,
            on_complete = self._on_complete,
        )

        self._panel.jump_requested.connect(self._on_jump_requested)
        self._panel.fix_requested.connect(self._on_fix_requested)

        self.on(EVT_TERMINAL_OUTPUT, self._on_terminal_output)
        self.on(EVT_PROJECT_OPENED,  self._on_project_opened)

    # ── Terminal output ───────────────────────────────────────────────────

    def _on_terminal_output(self, text: str = "", **kwargs):
        self._analyzer.feed(text)

    # ── Run events ────────────────────────────────────────────────────────

    def _on_run_event(self, event: RunEvent):
        QTimer.singleShot(0, lambda e=event: self._panel.add_event(e))

    def _on_failure(self, event: RunEvent):
        """Called immediately when a fatal error is detected."""
        QTimer.singleShot(0, lambda e=event: self._handle_failure(e))

    def _handle_failure(self, event: RunEvent):
        # Find the relevant file
        file_path, code = self._find_task_file(event)

        # Query vector memory for past similar failures
        past_fix = self._query_past_fix(event)

        # Show inline suggestion banner
        self._panel.show_suggestion(event, past_fix=past_fix)

        # Index this failure into vector memory
        self._index_failure(event, file_path, code)

        # Emit plugin event for other plugins to hook into
        self.app.plugin_manager.emit(
            EVT_RUN_FAILURE,
            run_event  = event,
            code       = code,
            file_path  = file_path,
        )

    def _on_complete(self, tool: str, success: bool, summary: str):
        """Called when PLAY RECAP is detected."""
        QTimer.singleShot(0, lambda: self._handle_complete(tool, success, summary))

    def _handle_complete(self, tool: str, success: bool, summary: str):
        if success:
            self._panel.hide_suggestion()
        self.emit(
            EVT_RUN_COMPLETE,
            tool    = tool,
            success = success,
            summary = summary,
        )

    # ── Memory ────────────────────────────────────────────────────────────

    def _index_failure(self, event: RunEvent, file_path: str, code: str):
        """Index this failure into the vector store for future recall."""
        vi = getattr(self.app, 'vector_index', None)
        if not vi or not vi.is_ready:
            return
        try:
            accepted_text = (
                f"[run_failure] tool={event.tool}\n"
                f"task={event.task_name or event.title}\n"
                f"error={event.detail}\n"
                f"code_snippet={code[:500] if code else ''}"
            )
            context_before = f"ansible failure: {event.task_name or event.title}"
            vi.index_completion(
                accepted_text  = accepted_text,
                context_before = context_before,
                file_path      = file_path or "",
            )
        except Exception as e:
            print(f"[RunAnalyzer] Failed to index failure: {e}")

    def _query_past_fix(self, event: RunEvent) -> str | None:
        """Search vector memory for a past similar failure and fix."""
        vi = getattr(self.app, 'vector_index', None)
        if not vi or not vi.is_ready:
            return None
        try:
            query = (
                f"ansible failure {event.task_name or event.title} "
                f"{event.detail[:100]}"
            )
            result = vi.query(query)
            if result and "[run_failure]" in result:
                return result
        except Exception:
            pass
        return None

    # ── AI fix ────────────────────────────────────────────────────────────

    def _on_fix_requested(self, event: RunEvent):
        """User clicked 'Ask AI to fix' — pre-fill chat with context."""
        file_path, code = self._find_task_file(event)
        past_fix        = self._query_past_fix(event)

        # Build a rich prompt
        task  = event.task_name or event.title
        error = event.detail or "Unknown error"

        prompt_parts = [
            f"I have an Ansible failure I need help fixing.\n",
            f"**Task:** `{task}`",
            f"**Error:**\n```\n{error}\n```",
        ]

        if code:
            fname = os.path.basename(file_path) if file_path else "task file"
            prompt_parts.append(f"**Relevant task file ({fname}):**\n```yaml\n{code}\n```")

        if past_fix:
            prompt_parts.append(
                f"**Note:** I've seen a similar failure before:\n{past_fix[:300]}"
            )

        prompt_parts.append(
            "\nPlease explain what went wrong and show me the corrected task."
        )

        prompt = "\n\n".join(prompt_parts)

        # Open chat and pre-fill
        if hasattr(self.app, 'chat_panel'):
            self.app.chat_panel.expand()
            self.app.chat_panel.switch_to_chat()
            # Use load_snippet_to_chat if available, otherwise set input text
            if hasattr(self.app, 'load_snippet_to_chat'):
                self.app.load_snippet_to_chat(prompt)
            elif hasattr(self.app, 'chat_input'):
                self.app.chat_input.setPlainText(prompt)
                self.app.chat_input.setFocus()

        self._panel.hide_suggestion()

    # ── File finding ──────────────────────────────────────────────────────

    def _find_task_file(self, event: RunEvent) -> tuple[str, str]:
        """Find the file and code for a failure event."""
        project_root = self._get_project_root()
        if not project_root:
            return "", ""

        hint = event.file_hint or event.task_name or ""
        if not hint:
            return "", ""

        hint_lower = hint.lower().split('|')[0].strip()
        skip       = {'__pycache__', 'node_modules', '.git', '.terraform'}
        candidates = []

        for dirpath, dirnames, filenames in os.walk(project_root):
            dirnames[:] = [d for d in dirnames if d not in skip]
            for fn in filenames:
                if fn.endswith(('.yml', '.yaml', '.tf', '.nix', '.py')):
                    full = os.path.join(dirpath, fn)
                    rel  = os.path.relpath(full, project_root).lower()
                    if hint_lower in rel:
                        candidates.append(full)

        if not candidates:
            return "", ""

        best = sorted(candidates, key=lambda p: (
            0 if 'tasks' in p and 'main' in p else
            1 if 'tasks' in p else 2
        ))[0]

        try:
            with open(best, 'r', encoding='utf-8') as f:
                code = f.read()
            return best, code
        except Exception:
            return best, ""

    def _get_project_root(self) -> str:
        if hasattr(self.app, 'git_dock') and self.app.git_dock.repo_path:
            return self.app.git_dock.repo_path
        if hasattr(self.app, 'file_model') and hasattr(self.app, 'tree_view'):
            root = self.app.file_model.filePath(self.app.tree_view.rootIndex())
            if root:
                return root
        return ""

    # ── Project change ────────────────────────────────────────────────────

    def _on_jump_requested(self, hint: str):
        project_root = self._get_project_root()
        if not project_root:
            return

        hint_lower = hint.lower()
        skip       = {'__pycache__', 'node_modules', '.git', '.terraform'}
        candidates = []

        for dirpath, dirnames, filenames in os.walk(project_root):
            dirnames[:] = [d for d in dirnames if d not in skip]
            for fn in filenames:
                if fn.endswith(('.yml', '.yaml', '.tf', '.nix', '.py')):
                    full = os.path.join(dirpath, fn)
                    rel  = os.path.relpath(full, project_root).lower()
                    if hint_lower in rel:
                        candidates.append(full)

        if candidates:
            best = sorted(candidates, key=lambda p: (
                0 if 'tasks' in p and 'main' in p else
                1 if 'tasks' in p else 2
            ))[0]
            self.app.open_file_in_tab(best)
        else:
            if hasattr(self.app, 'search_dock'):
                self.app.search_dock.show()
                self.app.search_dock.raise_()
                if hasattr(self.app, 'find_in_files_widget'):
                    self.app.find_in_files_widget.set_search_text(hint)
                    self.app.find_in_files_widget.focus_search()

    def _on_project_opened(self, project_root: str = None, **kwargs):
        self._analyzer.reset()
        self._panel.clear()

    def deactivate(self):
        self._panel.close()
        self.app.run_analyzer_dock = None