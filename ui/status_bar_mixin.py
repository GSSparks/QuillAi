"""
ui/status_bar_mixin.py

StatusBarMixin — AI mode toggle, loading indicator, terminal error button.
Mixed into CodeEditor.
"""

from PyQt6.QtWidgets import QPushButton
from PyQt6.QtCore import QTimer


class StatusBarMixin:

    def toggle_ai_mode(self):
        current = self.settings_manager.get_backend()
        cycle   = ["llama", "openai", "claude", "gemini"]
        idx     = (cycle.index(current) + 1) % len(cycle) if current in cycle else 0
        backend = cycle[idx]
        self.settings_manager.set_backend(backend)
        self.update_mode_label(backend)
        self.statusBar().showMessage(f"AI Mode: {backend}", 3000)

    def update_mode_label(self, backend: str):
        labels = {
            "llama":  "\U0001f3e0 LOCAL",
            "openai": "\u2601\ufe0f  OPENAI",
            "claude": "\U0001f7e0 CLAUDE",
            "gemini": "\U0001f48e GEMINI",
        }
        self.ai_mode_btn.setText(labels.get(backend, "\U0001f3e0 LOCAL"))

    def show_loading_indicator(self):
        pane  = self.split_container.active_pane()
        index = pane.currentIndex()
        if index >= 0:
            current_text = pane.tabText(index)
            if not current_text.startswith("⟳"):
                pane.setTabText(index, "⟳ " + current_text)

    def hide_loading_indicator(self):
        for pane in self.split_container.all_panes():
            for i in range(pane.count()):
                t = pane.tabText(i)
                if t.startswith("⟳ "):
                    pane.setTabText(i, t[2:])

    def update_status_bar(self):
        import os
        editor = self.current_editor()
        if not editor:
            self.cursor_label.setText("")
            if hasattr(self, "filetype_btn"):
                self.filetype_btn.setText("")
            return
        cursor = editor.textCursor()
        self.cursor_label.setText(
            f"Ln {cursor.blockNumber() + 1}, Col {cursor.columnNumber() + 1}"
        )
        if hasattr(editor, "multi_cursor") and editor.multi_cursor.active:
            count = editor.multi_cursor.cursor_count()
            self.cursor_label.setText(
                f"Ln {cursor.blockNumber()+1}, Col {cursor.columnNumber()+1}"
                f"  \u00b7  {count} cursors"
            )
        path = getattr(editor, "file_path", None)
        type_map = {
            ".py": "Python", ".html": "HTML", ".css": "CSS",
            ".js": "JavaScript", ".ts": "TypeScript", ".tsx": "TypeScript",
            ".json": "JSON", ".yml": "YAML", ".yaml": "YAML",
            ".tf": "Terraform", ".nix": "Nix", ".sh": "Bash",
            ".pl": "Perl", ".lua": "Lua", ".rs": "Rust", ".go": "Go",
            ".md": "Markdown", ".txt": "Text", ".sql": "SQL",
        }
        if path:
            ext = os.path.splitext(path)[1].lower()
            self.filetype_btn.setText(
                type_map.get(ext, ext.lstrip(".").upper() or "Plain Text")
            )
        else:
            self.filetype_btn.setText("Plain Text")
        text = editor.toPlainText()
        tabs   = sum(1 for l in text.split("\n") if l.startswith("\t"))
        spaces = sum(1 for l in text.split("\n") if l.startswith("    "))
        self.indent_btn.setText("Tabs" if tabs > spaces else "Spaces: 4")
        if "\r\n" in text:
            self.lineending_btn.setText("CRLF")
        elif "\r" in text:
            self.lineending_btn.setText("CR")
        else:
            self.lineending_btn.setText("LF")
        if path and os.path.exists(path):
            try:
                import chardet
                raw = open(path, "rb").read(4096)
                enc = (chardet.detect(raw).get("encoding") or "UTF-8").upper()
                enc = enc.replace("UTF-8-SIG", "UTF-8 BOM").replace("ASCII", "UTF-8")
                self.encoding_btn.setText(enc)
            except ImportError:
                self.encoding_btn.setText("UTF-8")
        else:
            self.encoding_btn.setText("UTF-8")
        if hasattr(self, "ins_ovr_btn") and hasattr(self.ins_ovr_btn, "_refresh"):
            self.ins_ovr_btn._refresh(editor)

    def update_git_branch(self):
        import os, subprocess
        repo_path = None
        if hasattr(self, "git_dock") and self.git_dock.repo_path:
            repo_path = self.git_dock.repo_path
        else:
            editor = self.current_editor()
            if editor and getattr(editor, "file_path", None):
                repo_path = os.path.dirname(editor.file_path)
        if not repo_path:
            self.branch_label.setText("")
            return
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=repo_path, capture_output=True, text=True, timeout=2,
            )
            self.branch_label.setText(
                f"\u23b7  {result.stdout.strip()}" if result.returncode == 0 else ""
            )
        except Exception:
            self.branch_label.setText("")
