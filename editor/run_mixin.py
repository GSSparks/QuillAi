"""
editor/run_mixin.py

RunMixin — script execution, output panel, stderr/stdout handling,
terminal error capture.
Mixed into CodeEditor.
"""

import re
from PyQt6.QtCore import QProcess
from ui.theme import (build_output_panel_stylesheet,
                      build_explain_error_btn_stylesheet, get_theme)


class RunMixin:

    @staticmethod
    def _strip_ansi(text: str) -> str:
        return re.sub(
            r'\x1b\[[0-9;]*[mABCDEFGHJKSTfsu]|\x1b\([A-Z]|\x1b\[\?[0-9;]*[lh]',
            "", text
        )

    def _on_terminal_output(self, text: str = "", **kwargs):
        if not text:
            return
        clean = self._strip_ansi(text)
        self._terminal_output_buffer.extend(clean.splitlines())
        if len(self._terminal_output_buffer) > 200:
            self._terminal_output_buffer = self._terminal_output_buffer[-200:]
        error_triggers = [
            "Traceback (most recent call last)",
            "Error:", "error:", "ERROR:",
            "Exception:", "FAILED", "fatal:",
            "command not found", "No such file or directory",
            "Permission denied",
        ]
        if any(trigger in clean for trigger in error_triggers):
            self._terminal_error_text = "\n".join(
                self._terminal_output_buffer[-50:]
            )
            self.terminal_error_btn.setVisible(True)

    def _explain_terminal_error(self):
        if not self._terminal_error_text.strip():
            return
        self.terminal_error_btn.setVisible(False)
        self.chat_panel.expand()
        self.chat_panel.switch_to_chat()
        error_text = self._terminal_error_text[:4000]
        self._terminal_error_text = ""
        prompt = (
            f"I got an error in my terminal. Can you explain what went wrong and how to fix it?\n\n"
            f"[Terminal Output]\n{error_text}\n\n"
            "Please:\n"
            "- Explain the error clearly\n"
            "- Identify the root cause\n"
            "- Show how to fix it\n"
            "- Include corrected code if applicable\n"
        )
        self._on_chat_message(prompt)

    def run_script(self):
        editor = self.current_editor()
        if not editor:
            return
        if self.process.state() == QProcess.ProcessState.Running:
            self.process.kill()
            return
        fp = getattr(editor, "file_path", None)
        if not fp or not fp.endswith(".py"):
            self.statusBar().showMessage("Run: only Python files supported", 3000)
            return
        if self.settings_manager.get_trim_trailing_whitespace():
            code = "\n".join(l.rstrip() for l in editor.toPlainText().splitlines())
            if code and not code.endswith("\n"):
                code += "\n"
            open(fp, "w", encoding="utf-8").write(code)
        self.current_error_text = ""
        self.output_editor.clear()
        self.explain_error_btn.hide()
        self.output_dock.show()
        self.output_dock.raise_()
        import sys, os
        self.process.setWorkingDirectory(os.path.dirname(fp))
        self.process.start(sys.executable, [fp])
        self.statusBar().showMessage(f"Running {os.path.basename(fp)}…", 0)

    def handle_stderr(self):
        data   = self.process.readAllStandardError()
        stderr = bytes(data).decode("utf8", errors="replace")
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
        prompt = (
            f"{user_text}\n\n"
            f"[Error Trace]\n{self.current_error_text[:8000]}\n\n"
            "Please:\n"
            "- Explain the error clearly\n"
            "- Identify the root cause\n"
            "- Show how to fix it\n"
            "- Include corrected code if possible\n"
        )
        self._last_user_message = user_text
        self._append_user_message(user_text)
        self._ai_response_buffer = ""
        self.current_ai_raw_text = ""
        self._on_chat_message(prompt)

    def handle_stdout(self):
        data   = self.process.readAllStandardOutput()
        stdout = bytes(data).decode("utf8", errors="replace")
        self.output_editor.insertPlainText(stdout)
        self.output_editor.ensureCursorVisible()

    def process_finished(self):
        self.statusBar().showMessage("Process finished", 3000)
        self.output_editor.insertPlainText("\n[Process finished]\n")
