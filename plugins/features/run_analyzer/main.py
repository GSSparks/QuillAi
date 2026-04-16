"""
plugins/features/run_analyzer/main.py

Ansible Playbook Debugger plugin — watches terminal output, shows a
live host×task execution matrix, surfaces errors with full verbose
detail, indexes failures into memory, and offers AI-assisted fixes.
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
from plugins.features.run_analyzer.parsers import RunEvent, Severity, HostResult


class RunAnalyzerPlugin(FeaturePlugin):
    name = "run_analyzer"
    description = "Ansible Playbook Debugger — live host×task matrix, verbose detail, AI fixes"
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
            "Playbook Debugger", "run_analyzer_dock"
        )

        self._analyzer = RunAnalyzer(
            on_event    = self._on_run_event,
            on_failure  = self._on_failure,
            on_complete = self._on_complete,
        )

        self._panel.jump_requested.connect(self._on_jump_requested)
        self._panel.fix_requested.connect(self._on_fix_requested)
        self._panel.compare_requested.connect(self._on_compare_requested)

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
        file_path, code = self._find_task_file(event)
        past_fix        = self._query_past_fix(event)

        self._panel.show_suggestion(event, past_fix=past_fix)
        self._index_failure(event, file_path, code)

        self.app.plugin_manager.emit(
            EVT_RUN_FAILURE,
            run_event = event,
            code      = code,
            file_path = file_path,
        )

    def _on_complete(self, tool: str, success: bool, summary: str):
        """Called when PLAY RECAP is detected."""
        QTimer.singleShot(0, lambda: self._handle_complete(tool, success, summary))

    def _handle_complete(self, tool: str, success: bool, summary: str):
        self.emit(
            EVT_RUN_COMPLETE,
            tool    = tool,
            success = success,
            summary = summary,
        )

    # ── Memory ────────────────────────────────────────────────────────────

    def _index_failure(self, event: RunEvent, file_path: str, code: str):
        """Index this failure into the vector store for future recall."""
        pass  # vector index removed — FAQ/memory handles this now

    def _query_past_fix(self, event: RunEvent) -> str | None:
        """Search FAQ/memory for a past similar failure and fix."""
        faq = getattr(self.app, 'faq_manager', None)
        if not faq:
            return None
        try:
            query = (
                f"ansible failure {event.task_name or event.title} "
                f"{event.detail[:100]}"
            )
            matches = faq.search(query, limit=1)
            if matches:
                return matches[0].get("answer", "")
        except Exception:
            pass
        return None

    # ── AI fix ────────────────────────────────────────────────────────────

    def _on_fix_requested(self, event: RunEvent):
        """User clicked 'Ask AI' — build rich prompt with all available context."""
        file_path, code = self._find_task_file(event)
        past_fix        = self._query_past_fix(event)

        task  = event.task_name or event.title
        play  = event.play_name  or ""

        prompt_parts = [
            f"I have an Ansible failure I need help fixing.\n",
        ]
        if play:
            prompt_parts.append(f"**Play:** `{play}`")
        prompt_parts.append(f"**Task:** `{task}`")

        # Per-host results
        if event.host_results:
            failed = [(h, r) for h, r in event.host_results.items()
                      if r.status in ("failed", "unreachable")]
            ok     = [(h, r) for h, r in event.host_results.items()
                      if r.status in ("ok", "changed")]

            if failed:
                prompt_parts.append(f"\n**Failed on {len(failed)} host(s):**")
                for host, hr in failed[:3]:  # cap at 3 hosts
                    lines = [f"- `{host}`:"]
                    if hr.msg:
                        lines.append(f"  msg: {hr.msg}")
                    if hr.rc:
                        lines.append(f"  rc: {hr.rc}")
                    if hr.stderr and hr.stderr.strip():
                        lines.append(f"  stderr:\n```\n{hr.stderr.strip()[:500]}\n```")
                    if hr.stdout and hr.stdout.strip():
                        lines.append(f"  stdout:\n```\n{hr.stdout.strip()[:500]}\n```")
                    prompt_parts.append("\n".join(lines))

            if ok and failed:
                ok_hosts = ", ".join(f"`{h}`" for h, _ in ok[:5])
                prompt_parts.append(
                    f"\n**Succeeded on:** {ok_hosts}\n"
                    f"(This suggests a host-specific configuration difference)"
                )

        elif event.detail:
            prompt_parts.append(f"**Error:**\n```\n{event.detail}\n```")

        if code:
            fname = os.path.basename(file_path) if file_path else "task file"
            prompt_parts.append(
                f"\n**Relevant task file ({fname}):**\n```yaml\n{code[:2000]}\n```"
            )

        if past_fix:
            prompt_parts.append(
                f"\n**Note:** Similar failure was fixed before:\n{past_fix[:300]}"
            )

        prompt_parts.append(
            "\nPlease explain what went wrong and show me the corrected task YAML."
        )

        prompt = "\n\n".join(prompt_parts)
        self._send_to_chat(prompt)
        self._panel.hide_suggestion()

    def _on_compare_requested(self, event: RunEvent):
        """
        User clicked 'Compare hosts' — build a prompt comparing
        inventory vars between failed and successful hosts.
        """
        failed_hosts = [h for h, r in event.host_results.items()
                        if r.status in ("failed", "unreachable")]
        ok_hosts     = [h for h, r in event.host_results.items()
                        if r.status in ("ok", "changed")]

        if not failed_hosts or not ok_hosts:
            return

        # Get inventory vars from inventory explorer if available
        inv = getattr(self.app, 'inventory_dock', None)
        inv_context = ""
        if inv and hasattr(inv, 'get_host_vars'):
            var_blocks = []
            for host in (failed_hosts[:2] + ok_hosts[:2]):
                vars_ = inv.get_host_vars(host)
                if vars_:
                    var_blocks.append(
                        f"**{host}** ({event.host_results[host].status}):\n"
                        f"```yaml\n{vars_[:500]}\n```"
                    )
            if var_blocks:
                inv_context = "\n\n".join(var_blocks)

        task = event.task_name or event.title
        prompt_parts = [
            f"I have an Ansible task that fails on some hosts but succeeds on others.\n",
            f"**Task:** `{task}`",
            f"\n**Failed on:** {', '.join(f'`{h}`' for h in failed_hosts)}",
            f"**Succeeded on:** {', '.join(f'`{h}`' for h in ok_hosts)}",
        ]

        if inv_context:
            prompt_parts.append(
                f"\n**Host variables:**\n{inv_context}"
            )
        else:
            prompt_parts.append(
                "\nI don't have the host variables available, but please suggest "
                "what inventory differences (OS version, package manager, "
                "installed packages, SELinux, firewall) might cause this."
            )

        # Add error detail from a failed host
        failed_hr = event.host_results.get(failed_hosts[0])
        if failed_hr:
            if failed_hr.msg:
                prompt_parts.append(f"\n**Error on `{failed_hosts[0]}`:** {failed_hr.msg}")
            if failed_hr.stderr and failed_hr.stderr.strip():
                prompt_parts.append(
                    f"**stderr:**\n```\n{failed_hr.stderr.strip()[:400]}\n```"
                )

        prompt_parts.append(
            "\nWhat host-specific difference is likely causing this failure? "
            "Show me how to fix the task or inventory to handle both cases."
        )

        prompt = "\n\n".join(prompt_parts)
        self._send_to_chat(prompt)

    def _send_to_chat(self, prompt: str):
        if hasattr(self.app, 'chat_panel'):
            self.app.chat_panel.expand()
            self.app.chat_panel.switch_to_chat()
            if hasattr(self.app, 'load_snippet_to_chat'):
                self.app.load_snippet_to_chat(prompt)
            elif hasattr(self.app, 'chat_input'):
                self.app.chat_input.setPlainText(prompt)
                self.app.chat_input.setFocus()

    # ── File finding ──────────────────────────────────────────────────────

    def _find_task_file(self, event: RunEvent) -> tuple[str, str]:
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
        return ""

    # ── Jump to file ──────────────────────────────────────────────────────

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

    # ── Project change ────────────────────────────────────────────────────

    def _on_project_opened(self, project_root: str = None, **kwargs):
        self._analyzer.reset()
        self._panel.clear()

    def deactivate(self):
        self._panel.close()
        self.app.run_analyzer_dock = None