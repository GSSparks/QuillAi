import re
import base64
import markdown
from markdown.extensions.fenced_code import FencedCodeExtension
from markdown.extensions.tables import TableExtension
from pygments import highlight
from pygments.lexers import get_lexer_by_name, guess_lexer, TextLexer
from pygments.formatters import HtmlFormatter
from pygments.util import ClassNotFound
from PyQt6.QtCore import pyqtSlot
import ast
from pathlib import Path

from ui.theme import get_theme, build_chat_styles, FONT_CODE, FONT_UI

# Matches <file_change path="..." mode="...">...</file_change>
_RE_FILE_CHANGE = re.compile(
    r'<file_change\s+path="([^"]+)"\s+mode="([^"]+)">(.*?)</file_change>',
    re.DOTALL,
)

def _autodetect_changes(
    text: str, file_path: str
) -> list[tuple[str, str, str]]:
    """Scan fenced code blocks for complete functions/classes.
    Returns [(file_path, mode, code)] targeting file_path.
    """
    import os
    results = []
    ext = os.path.splitext(file_path)[1].lower()

    _FUNCTION_EXTS = {'.py'}
    _PERL_EXTS = {'.pl', '.pm', '.t'}
    _FULL_EXTS = {
        '.yml', '.yaml', '.json', '.toml', '.xml',
        '.ini', '.cfg', '.conf',
        '.sh', '.bash', '.zsh', '.fish',
        '.html', '.htm', '.css', '.js', '.ts',
        '.rs', '.go', '.c', '.cpp', '.h', '.hpp', '.java',
        '.tf', '.hcl', '.nix', '.md', '.rst', '.txt', '.sql',
    }

    # Split on triple-backtick fences
    chunks = text.split("```")
    for i in range(1, len(chunks), 2):
        block = chunks[i]
        lines = block.split("\n", 1)
        code  = lines[1].strip() if len(lines) > 1 else lines[0].strip()
        if not code or len(code) < 10:
            continue

        applicable = False
        mode = 'full'

        if ext in _FUNCTION_EXTS:
            try:
                tree = ast.parse(code)
                has_sym = any(
                    isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                       ast.ClassDef))
                    for node in tree.body
                )
                if has_sym:
                    top_syms = [n for n in tree.body
                                if isinstance(n, (ast.FunctionDef,
                                    ast.AsyncFunctionDef, ast.ClassDef))]
                    mode = 'function' if len(top_syms) == 1 else 'full'
                    applicable = True
                elif tree.body:
                    applicable = True
            except SyntaxError:
                pass
        elif ext in _PERL_EXTS:
            import re as _re
            if _re.search(r'\bsub\s+\w+', code):
                applicable = True
                mode = 'perl_function'
            elif len(code.splitlines()) > 3:
                applicable = True
        elif ext in _FULL_EXTS:
            applicable = len(code.splitlines()) > 3

        if applicable:
            try:
                rel = os.path.relpath(file_path)
            except ValueError:
                rel = file_path
            results.append((rel, mode, code))
            break
    return results


def _extract_file_changes(text: str) -> tuple[str, list[tuple[str, str, str]]]:
    """
    Strip <file_change> tags from *text*, replace with fenced code blocks,
    and return:
      (cleaned_text, [(path, mode, code), ...])
    """
    changes = []

    def _collect(m):
        path = m.group(1)
        mode = m.group(2)
        code = m.group(3).strip()
        # Warn if code contains placeholders — agent read files before proposing
        placeholders = ["# ...", "# existing", "pass  #", "...existing..."]
        if any(p in code for p in placeholders):
            print(f"[file_change warning] {path} may contain placeholders: {[p for p in placeholders if p in code]}")
        changes.append((path, mode, code))
        # Keep code visible as a fenced block with file path as header
        ext = path.rsplit('.', 1)[-1] if '.' in path else ''
        return f"\n**`{path}`**\n```{ext}\n{code}\n```\n"

    cleaned = _RE_FILE_CHANGE.sub(_collect, text)
    return cleaned, changes


# ── Agent status panel ───────────────────────────────────────────────────────

_AGENT_PANEL_ID = "agent-status-panel"


def render_agent_status_panel(chat_history, json_str: str):
    """
    Insert or update the collapsible agent status panel in the chat.
    Uses a JavaScript-free approach: replaces the panel HTML in place
    by finding it via QTextCursor search.
    """
    import json as _json
    from PyQt6.QtGui import QTextCursor
    try:
        data = _json.loads(json_str)
    except Exception:
        return

    t       = get_theme()
    summary = data.get("summary", "Agent thinking...")
    content = data.get("content", "")
    done    = data.get("done", False)

    border_color = t.get("aqua",   "#8ec07c") if not done else t.get("green", "#98971a")
    dim_color = t.get("fg4", "#a89984")

    content_html = content.replace("\n", "<br>")

    # Build rows for each tool call
    rows = []
    for line in content.splitlines():
        if line.strip():
            rows.append(
                f'<tr><td style="padding:1px 0 1px 8px;'
                f'color:{dim_color};font-size:8pt;">'
                f'{line}</td></tr>'
            )
    rows_html = "".join(rows)

    panel_html = (
        f'<!-- agent-status-begin -->'
        f'<table width="100%" cellpadding="0" cellspacing="0" '
        f'style="margin:4px 0 4px 0;">'
        f'<tr><td style="'
        f'border-left:3px solid {border_color};'
        f'padding:4px 0 4px 8px;">'
        f'<table width="100%" cellpadding="0" cellspacing="0">'
        f'<tr><td style="color:{border_color};font-size:8.5pt;'
        f'font-weight:bold;padding-bottom:2px;">'
        f'{summary}</td></tr>'
        f'{rows_html}'
        f'</table>'
        f'</td></tr></table>'
        f'<!-- agent-status-end -->'
    )

    doc    = chat_history.document()
    cursor = QTextCursor(doc)

    # Try to find and replace existing panel
    found = doc.find("<!-- agent-status-begin -->")
    if not found.isNull():
        end = doc.find("<!-- agent-status-end -->", found)
        if not end.isNull():
            end.movePosition(
                QTextCursor.MoveOperation.EndOfBlock,
                QTextCursor.MoveMode.KeepAnchor
            )
            found.setPosition(
                found.position(),
                QTextCursor.MoveMode.MoveAnchor
            )
            found.setPosition(
                end.position(),
                QTextCursor.MoveMode.KeepAnchor
            )
            found.insertHtml(panel_html)
            return

    # No existing panel — insert before stream start pos
    cursor = chat_history.textCursor()
    stream_start = getattr(chat_history, '_agent_panel_pos', None)
    if stream_start is None:
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertHtml(panel_html)
        chat_history._agent_panel_pos = cursor.position()
    else:
        cursor.setPosition(stream_start)
        cursor.insertHtml(panel_html)
    chat_history.moveCursor(QTextCursor.MoveOperation.End)
    chat_history.ensureCursorVisible()


_PYGMENTS_STYLE_MAP = {
    "gruvbox_dark":  "gruvbox-dark",
    "vscode_dark":   "dracula",
    "monokai":       "monokai",
    "solarized_dark":"solarized-dark",
}

def _pygments_style_for_theme(theme_name: str) -> str:
    return _PYGMENTS_STYLE_MAP.get(theme_name, "monokai")

def _safe_styles(t: dict) -> dict:
    return {k: v.replace('"', "'") for k, v in t.items()}


def _summarise_change(code: str, mode: str) -> str:
    """One-line summary of what the change does."""
    import ast as _ast
    try:
        tree = _ast.parse(code)
        names = [
            node.name for node in tree.body
            if isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef,
                                   _ast.ClassDef))
        ]
        if mode == 'full':
            return f'Full file rewrite'
        if names:
            kind = 'class' if any(
                isinstance(n, _ast.ClassDef) for n in tree.body
                if hasattr(n, 'name') and n.name == names[0]
            ) else 'function'
            return f'Replace {kind} {names[0]}()' if kind == 'function' \
                   else f'Replace class {names[0]}'
    except Exception:
        pass
    return 'Apply suggested change'


class ChatRenderer:

    # ── User message ──────────────────────────────────────────────────────

    def _append_user_message(self, text: str):
        from PyQt6.QtGui import QTextCursor
        s = _safe_styles(build_chat_styles(get_theme()))
        escaped = (text.replace("&", "&amp;")
                       .replace("<", "&lt;")
                       .replace(">", "&gt;")
                       .replace("\n", "<br>"))

        html = (
            f'<table width="100%" cellpadding="0" cellspacing="0">'
            f'<tr><td height="8"></td></tr></table>'

            f'<table width="100%" cellpadding="0" cellspacing="4">'
            f'<tr>'
            f'<td width="20%"></td>'
            f'<td width="80%" style="{s["user_bubble_td"]}">{escaped}</td>'
            f'</tr></table>'

            f'<table width="100%" cellpadding="0" cellspacing="0">'
            f'<tr><td align="right" style="{s["user_label_td"]}">You</td></tr>'
            f'</table>'

            f'<table width="100%" cellpadding="0" cellspacing="0">'
            f'<tr><td height="10"></td></tr></table>'

            f'<table width="100%" cellpadding="0" cellspacing="0">'
            f'<tr><td style="{s["ai_label_td"]}">QuillAI</td></tr>'
            f'</table>'

            f'<table width="100%" cellpadding="0" cellspacing="0">'
            f'<tr><td height="4"></td></tr></table>'
        )

        self.chat_history.moveCursor(QTextCursor.MoveOperation.End)
        self.chat_history.insertHtml(html)
        self.chat_history.moveCursor(QTextCursor.MoveOperation.End)
        self._stream_start_pos = self.chat_history.textCursor().position()
        self.chat_history.ensureCursorVisible()

    # ── Streaming ─────────────────────────────────────────────────────────

    def append_agent_status(self, json_str: str):
        """Receive agent status panel update and forward to chat renderer."""
        if hasattr(self, 'chat_history'):
            from ui.chat_renderer import render_agent_status_panel
            from PyQt6.QtGui import QTextCursor
            render_agent_status_panel(self.chat_history, json_str)
            # Update stream start to be after the status panel
            # so chat_stream_finished doesn't wipe it
            cursor = self.chat_history.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self._stream_start_pos = cursor.position()
            self.chat_history._agent_panel_pos = None  # reset so panel updates in place

    def _on_agent_write_ops(self, ops: list):
        """Show multi-file diff dialog for agent write operations."""
        from ui.multi_file_diff_dialog import MultiFileDiffDialog
        root = (
            self.git_dock.repo_path
            if hasattr(self, 'git_dock') and self.git_dock.repo_path
            else os.getcwd()
        )
        # Convert agent write ops to (path, mode, code) tuples
        changes = []
        rejected_patches = []
        applied_direct   = []  # patch_file ops applied immediately
        for op in ops:
            name  = op.get("name", "")
            attrs = op.get("attrs", {})
            if name == "write_file":
                path = attrs.get("path", "")
                code = attrs.get("content", "")
                if path:
                    changes.append((path, "full", code))
            elif name == "patch_file":
                path = attrs.get("path", "")
                sl   = attrs.get("start_line")
                el   = attrs.get("end_line")
                body = attrs.get("_body", "")
                if not path:
                    continue
                if not sl or not el:
                    # Old-format patch_file without line numbers — reject
                    rejected_patches.append(
                        f"{path} (missing start_line/end_line — agent must use wc -l then read_file)"
                    )
                    continue
                from ai.worker import clean_code
                abs_path = str((Path(root) / path).resolve())
                # Apply directly via run_tool
                from ai.tools import run_tool as _run_tool
                ok, msg = _run_tool("patch_file", attrs, root)
                if ok:
                    changes.append((path, "patch_done",
                        f"Patched lines {sl}-{el} in {path}"))
                    applied_direct.append(abs_path)
                else:
                    rejected_patches.append(f"{path}: {msg}")
        if rejected_patches:
            from PyQt6.QtWidgets import QMessageBox
            names = chr(10).join(rejected_patches)
            QMessageBox.warning(
                self, 'Patch Context Too Short',
                'The agent provided insufficient context for:' + chr(10) + names + chr(10) + chr(10) +
                'Ask the agent to re-read the file and patch again '
                'using at least 3 lines of context in the old field.'
            )
        # Reload any directly-applied patch_file ops
        for abs_path in applied_direct:
            self._reload_file_in_editors(abs_path)
            if hasattr(self, "repo_map") and self.repo_map:
                self.repo_map.invalidate(abs_path)
        if not changes:
            if applied_direct:
                n = len(applied_direct)
                self.statusBar().showMessage(
                    f"Agent applied {n} patch{'es' if n != 1 else ''}.", 5000
                )
            return
        dialog = MultiFileDiffDialog(changes, root, parent=self)
        if dialog.exec():
            for abs_path in dialog.applied_paths:
                self._reload_file_in_editors(abs_path)
                if hasattr(self, "repo_map") and self.repo_map:
                    self.repo_map.invalidate(abs_path)
            n = len(dialog.applied_paths) + len(applied_direct)
            self.statusBar().showMessage(
                f"Agent applied {n} file{'s' if n != 1 else ''}.", 5000
            )

    def append_chat_stream(self, text: str):
        self.current_ai_raw_text += text
        self._stream_buffer = getattr(self, "_stream_buffer", "") + text
        should_render = (
            "\n" in self._stream_buffer
            or self._stream_buffer.endswith("```")
            or len(self._stream_buffer) > 80
        )
        if should_render:
            self._flush_stream_buffer()

    def _flush_stream_buffer(self):
        from PyQt6.QtGui import QTextCursor
        if not self.current_ai_raw_text.strip():
            return
        start_pos = getattr(self, "_stream_start_pos", 0)
        if start_pos == 0:
            return
        cursor = self.chat_history.textCursor()
        cursor.setPosition(start_pos)
        cursor.movePosition(
            QTextCursor.MoveOperation.End, QTextCursor.MoveMode.KeepAnchor
        )
        cursor.removeSelectedText()
        self.chat_history.setTextCursor(cursor)
        rendered = self._render_partial_response(self.current_ai_raw_text)
        self.chat_history.moveCursor(QTextCursor.MoveOperation.End)
        self.chat_history.insertHtml(rendered)
        self.chat_history.moveCursor(QTextCursor.MoveOperation.End)
        self.chat_history.ensureCursorVisible()
        self._stream_buffer = ""

    def _render_partial_response(self, text: str) -> str:
        open_fences = len(re.findall(r"^```", text, re.MULTILINE))
        if open_fences % 2 == 1:
            text = text + "\n```"
        return self._render_ai_response(text)

    def chat_stream_finished(self):
        # Agent mode — final answer already rendered, just clean up
        if getattr(self, '_skip_stream_finished', False):
            self._skip_stream_finished = False
            self._agent_session_active = True  # keep agent mode for next turn
            self.current_ai_raw_text = ""
            self._stream_buffer      = ""
            self._stream_start_pos   = 0
            self.memory_manager.save_chat_history(self.chat_history.toHtml())
            return

        # Model requested tool access — re-launch as agent
        if '<needs_tools/>' in self.current_ai_raw_text:
            # Clear the partial response (don't show <needs_tools/> to user)
            from PyQt6.QtGui import QTextCursor
            start_pos = getattr(self, '_stream_start_pos', 0)
            if start_pos > 0:
                cursor = self.chat_history.textCursor()
                cursor.setPosition(start_pos)
                cursor.movePosition(
                    QTextCursor.MoveOperation.End,
                    QTextCursor.MoveMode.KeepAnchor
                )
                cursor.removeSelectedText()
            self.current_ai_raw_text = ""
            self._stream_buffer      = ""
            self._stream_start_pos   = 0
            # Re-launch as agent
            if hasattr(self, '_relaunch_as_agent'):
                self._relaunch_as_agent(self._last_user_message)
            return


        # Model requested tool access — re-launch as agent
        if '<needs_tools/>' in self.current_ai_raw_text:
            # Clear the partial response (don't show <needs_tools/> to user)
            from PyQt6.QtGui import QTextCursor
            start_pos = getattr(self, '_stream_start_pos', 0)
            if start_pos > 0:
                cursor = self.chat_history.textCursor()
                cursor.setPosition(start_pos)
                cursor.movePosition(
                    QTextCursor.MoveOperation.End,
                    QTextCursor.MoveMode.KeepAnchor
                )
                cursor.removeSelectedText()
            self.current_ai_raw_text = ""
            self._stream_buffer      = ""
            self._stream_start_pos   = 0
            # Re-launch as agent
            if hasattr(self, '_relaunch_as_agent'):
                self._relaunch_as_agent(self._last_user_message)
            return

            
        from PyQt6.QtGui import QTextCursor
        full_response = self.current_ai_raw_text
        start_pos     = getattr(self, "_stream_start_pos", 0)
        if start_pos > 0:
            cursor = self.chat_history.textCursor()
            cursor.setPosition(start_pos)
            cursor.movePosition(
                QTextCursor.MoveOperation.End, QTextCursor.MoveMode.KeepAnchor
            )
            cursor.removeSelectedText()
            self.chat_history.setTextCursor(cursor)

        clean_response, file_changes = _extract_file_changes(full_response)

        rendered = self._render_ai_response(
            clean_response if clean_response.strip()
            else full_response
                .replace('<file_change', '<!--')
                .replace('</file_change>', '-->')
        )

        if not file_changes:
            editor = self.current_editor()
            if editor and getattr(editor, 'file_path', None):
                file_changes = _autodetect_changes(
                    clean_response, editor.file_path
                )

        if file_changes:
            rendered += self._render_apply_buttons(file_changes)

        rendered += self._render_save_faq_button(
            self._last_user_message, clean_response
        )

        self.chat_history.moveCursor(QTextCursor.MoveOperation.End)
        self.chat_history.insertHtml(rendered)
        self.chat_history.moveCursor(QTextCursor.MoveOperation.End)
        self.chat_history.ensureCursorVisible()

        if full_response.strip():
            self.memory_manager.add_turn("assistant", clean_response)
            self.memory_manager.process_exchange_async(
                self._last_user_message,
                clean_response,
            )
            if hasattr(self, 'faq_manager') and self.faq_manager:
                self.faq_manager.process_exchange_async(
                    self._last_user_message,
                    clean_response,
                )

        self.memory_manager.save_chat_history(self.chat_history.toHtml())
        self.current_ai_raw_text  = ""
        self._ai_response_buffer  = ""
        self._stream_buffer       = ""
        self._stream_start_pos    = 0

    # ── AI response rendering ─────────────────────────────────────────────

    def _render_ai_response(self, text: str) -> str:
        s = _safe_styles(build_chat_styles(get_theme()))
        t = get_theme()

        md = markdown.Markdown(extensions=[
            FencedCodeExtension(),
            TableExtension(),
            "markdown.extensions.nl2br",
            "markdown.extensions.sane_lists",
        ])
        raw_html = md.convert(text)

        def replace_fenced(m):
            inner      = m.group(1)
            inner = (inner.replace("&amp;", "&")
                          .replace("&lt;", "<")
                          .replace("&gt;", ">")
                          .replace("&quot;", '"')
                          .replace("&#39;", "'"))
            lang_match  = re.search(r'class="language-(\w+)"', m.group(0))
            lang        = lang_match.group(1).lower() if lang_match else ""
            lang_label  = lang.upper() if lang else "CODE"
            highlighted = self._highlight_code_block(inner, lang)
            encoded     = base64.b64encode(inner.encode("utf-8")).decode("utf-8")
            return (
                f'<table width="100%" cellpadding="0" cellspacing="0" '
                f'style="margin:6px 0 10px 0;">'
                f'<tr><td style="{s["code_header_td"]}">'
                f'<span style="{s["lang_label"]}">{lang_label}</span>'
                f'&nbsp;&nbsp;'
                f'<a href="copy:{encoded}" style="{s["copy_link"]}">⎘ Copy</a>'
                f'</td></tr>'
                f'<tr><td style="{s["code_body_td"]}">'
                f'<pre style="{s["code_pre"]}">{highlighted}</pre>'
                f'</td></tr></table>'
            )

        raw_html = re.sub(
            r"<pre><code[^>]*>(.*?)</code></pre>",
            replace_fenced,
            raw_html,
            flags=re.DOTALL,
        )

        raw_html = re.sub(
            r"<code>([^<]+)</code>",
            lambda m: f'<code style="{s["inline_code"]}">{m.group(1)}</code>',
            raw_html,
        )

        raw_html = re.sub(
            r"<table>",
            f'<table width="100%" cellpadding="6" cellspacing="0" '
            f'style="{s["md_table"]}">',
            raw_html,
        )
        raw_html = re.sub(r"<thead>", "<thead>", raw_html)
        raw_html = re.sub(r"<th>",    f'<th style="{s["md_th"]}">',  raw_html)
        raw_html = re.sub(r"<td>",    f'<td style="{s["md_td"]}">',  raw_html)
        raw_html = re.sub(r"<tr>",    f'<tr style="{s["md_tr"]}">',  raw_html)

        raw_html = re.sub(r"<p>",    f'<p style="{s["prose_p"]}">',   raw_html)
        raw_html = re.sub(r"<ul>",   f'<ul style="{s["ul"]}">',       raw_html)
        raw_html = re.sub(r"<ol>",   f'<ol style="{s["ol"]}">',       raw_html)
        raw_html = re.sub(r"<li>",   f'<li style="{s["prose_li"]}">',raw_html)
        raw_html = re.sub(r"<h1>",   f'<p style="{s["heading_1"]}">',raw_html)
        raw_html = re.sub(r"</h1>",  "</p>",                          raw_html)
        raw_html = re.sub(r"<h2>",   f'<p style="{s["heading_2"]}">',raw_html)
        raw_html = re.sub(r"</h2>",  "</p>",                          raw_html)
        raw_html = re.sub(r"<h3>",   f'<p style="{s["heading_3"]}">',raw_html)
        raw_html = re.sub(r"</h3>",  "</p>",                          raw_html)
        raw_html = re.sub(r"<hr\s*/?>", f'<hr style="{s["hr"]}"/>',  raw_html)
        raw_html = re.sub(r"<strong>",  f'<strong style="{s["strong"]}">',raw_html)
        raw_html = re.sub(r"<em>",      f'<em style="{s["em"]}">',        raw_html)

        return (
            f'<table width="100%" cellpadding="0" cellspacing="0" '
            f'style="margin:0 0 16px 0;">'
            f'<tr><td style="{s["response_td"]}">'
            f'{raw_html}'
            f'</td></tr></table>'
        )

    # ── Syntax highlighting ───────────────────────────────────────────────

    def _highlight_code_block(self, code: str, lang: str = "") -> str:
        try:
            lexer = get_lexer_by_name(lang) if lang else guess_lexer(code)
        except ClassNotFound:
            lexer = TextLexer()
        theme_name     = get_theme().get("name", "gruvbox_dark")
        pygments_style = _pygments_style_for_theme(theme_name)
        try:
            formatter = HtmlFormatter(nowrap=True, noclasses=True, style=pygments_style)
        except Exception:
            formatter = HtmlFormatter(nowrap=True, noclasses=True, style="monokai")
        result = highlight(code, lexer, formatter)
        return result.replace("&quot;", '"')

    # ── Memory & conversation ─────────────────────────────────────────────

    def _restore_conversation(self, user_message: str, ai_response: str):
        from PyQt6.QtGui import QTextCursor
        self.chat_panel.expand()
        self.chat_panel.switch_to_chat()
        self.chat_history.clear()
        self.current_ai_raw_text = ""
        self._ai_response_buffer = ""
        self._stream_start_pos   = 0
        self._append_user_message(user_message)
        self.chat_history.insertHtml(self._render_ai_response(ai_response))
        self.chat_history.moveCursor(QTextCursor.MoveOperation.End)
        self.statusBar().showMessage(
            "Past conversation restored — send a message to continue it.", 5000
        )

    def load_snippet_to_chat(self, text: str):
        from PyQt6.QtGui import QTextCursor
        self.chat_panel.expand()
        self.chat_panel.switch_to_chat()
        chat_input    = self.chat_panel.chat_input
        current_input = chat_input.toPlainText()
        new_text      = f"```python\n{text}\n```\n"
        chat_input.setPlainText(
            current_input + "\n\n" + new_text if current_input.strip() else new_text
        )
        chat_input.setFocus()
        cursor = chat_input.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        chat_input.setTextCursor(cursor)

    def load_project_chat(self):
        from PyQt6.QtGui import QTextCursor
        self.chat_panel.chat_history.clear()
        self.current_ai_raw_text   = ""
        self._stream_start_pos     = 0
        self._agent_session_active = False
        saved = self.memory_manager.load_chat_history()
        if saved:
            self.chat_panel.chat_history.setHtml(saved)
            self.chat_panel.chat_history.moveCursor(QTextCursor.MoveOperation.End)

    def _render_save_faq_button(self, question: str, answer: str) -> str:
        if not question or not answer:
            return ''
        t = get_theme()
        encoded = base64.b64encode(
            f"{question}|||{answer}".encode('utf-8', errors='replace')
        ).decode()
        return (
            f'<table width="100%" cellpadding="0" cellspacing="0" '
            f'style="margin:2px 0 8px 0;">'
            f'<tr><td style="text-align:right;padding-right:4px;">'
            f'<a href="savefaq:{encoded}" '
            f'style="color:{t.get("bg4","#7c6f64")};'
            f'font-size:8pt;text-decoration:none;">'
            f'💾 Save as FAQ</a>'
            f'</td></tr></table>'
        )

    def _render_apply_buttons(self, changes: list) -> str:
        s = _safe_styles(build_chat_styles(get_theme()))
        t = get_theme()
        rows = []

        # Apply All button — shown when there are 2+ file changes
        if len(changes) >= 2:
            import base64 as _b64, json as _json
            all_encoded = _b64.b64encode(
                _json.dumps([
                    {"path": p, "mode": m, "code": c}
                    for p, m, c in changes
                ]).encode("utf-8")
            ).decode()
            rows.append(
                f'<table width="100%" cellpadding="0" cellspacing="0" '
                f'style="margin:8px 0 4px 0;">'
                f'<tr><td style="padding:8px 10px;'
                f'background:{t.get("bg2","#504945")};'
                f'border-left:3px solid {t.get("aqua","#8ec07c")};'
                f'border-radius:2px;">'
                f'<a href="apply_all:{all_encoded}" '
                f'style="color:{t.get("aqua","#8ec07c")};'
                f'font-size:9.5pt;font-weight:bold;text-decoration:none;">'
                f'⚡ Review &amp; Apply All {len(changes)} Files</a>'
                f'</td></tr></table>'
            )
        for file_path, mode, code in changes:
            # Strip absolute project root prefix if present
            _root = None
            if hasattr(self, "git_dock") and self.git_dock.repo_path:
                _root = self.git_dock.repo_path.rstrip("/")
            if _root and file_path.startswith(_root + "/"):
                file_path = file_path[len(_root)+1:]
            elif file_path.startswith("/"):
                # Try to make relative to cwd
                import os as _os
                try:
                    file_path = _os.path.relpath(file_path)
                except ValueError:
                    pass
            encoded = base64.b64encode(
                f"{file_path}|{mode}|{code}".encode("utf-8")
            ).decode("utf-8")
            fname = file_path.split("/")[-1]
            apply_url = f"apply:{encoded}"
            undo_url  = f"undo:{base64.b64encode(file_path.encode()).decode()}"
            summary = _summarise_change(code, mode)
            rows.append(
                f'<table width="100%" cellpadding="0" cellspacing="0" '
                f'style="margin:8px 0 4px 0;">'
                f'<tr><td style="padding:8px 10px;'
                f'background:{t.get("bg1","#3c3836")};'
                f'border-left:3px solid {t.get("green","#98971a")};'
                f'border-radius:2px;">'
                f'<div style="color:{t.get("fg1","#ebdbb2")};font-size:9pt;'
                f'margin-bottom:4px;">'
                f'🔧 <strong>{summary}</strong></div>'
                f'<span style="color:{t.get("fg4","#a89984")};font-size:8pt;">'
                f'📄 {file_path}</span>'
                f'&nbsp;&nbsp;'
                f'<a href="{apply_url}" style="color:{t.get("green","#98971a")};'
                f'font-size:9pt;font-weight:bold;text-decoration:none;">'
                f'⚡ Apply to {fname}</a>'
                f'&nbsp;&nbsp;'
                f'<a href="{undo_url}" style="color:{t.get("fg4","#a89984")};'
                f'font-size:9pt;text-decoration:none;">'
                f'↩ Undo</a>'
                f'</td></tr></table>'
            )
        return "".join(rows)

    def handle_chat_link(self, url):
        from PyQt6.QtWidgets import QApplication
        url_str = url.toString()
        if url_str.startswith("insert:"):
            decoded = base64.b64decode(url_str.replace("insert:", "")).decode("utf-8")
            editor  = self.current_editor()
            if editor:
                editor.textCursor().insertText(decoded)
                editor.setFocus()
        elif url_str.startswith("copy:"):
            decoded = base64.b64decode(url_str.replace("copy:", "")).decode("utf-8")
            QApplication.clipboard().setText(decoded)
            self.statusBar().showMessage("Code copied to clipboard.", 2000)
        elif url_str.startswith("apply_all:"):
            self._handle_apply_all_link(url_str[10:])
        elif url_str.startswith("apply:"):
            self._handle_apply_link(url_str[6:])
        elif url_str.startswith("undo:"):
            self._handle_undo_link(url_str[5:])
        elif url_str.startswith("savefaq:"):
            self._handle_save_faq_link(url_str[8:])

    def _reload_file_in_editors(self, abs_path: str):
        for pane in self.split_container.all_panes():
            for i in range(pane.count()):
                editor = pane.widget(i)
                fp = getattr(editor, "file_path", None)
        try:
            with open(abs_path, 'r', encoding='utf-8') as f:
                new_content = f.read()
        except Exception:
            return
        for pane in self.split_container.all_panes():
            for i in range(pane.count()):
                editor = pane.widget(i)
                if getattr(editor, 'file_path', None) == abs_path:
                    self._reload_editor(editor, new_content, abs_path)

    def _handle_save_faq_link(self, encoded: str):
        try:
            payload  = base64.b64decode(encoded).decode('utf-8', errors='replace')
            sep      = payload.index('|||')
            question = payload[:sep].strip()
            answer   = payload[sep+3:].strip()
        except Exception as e:
            self.statusBar().showMessage(f'Could not parse FAQ: {e}', 3000)
            return
        if hasattr(self, 'faq_manager') and self.faq_manager:
            ok = self.faq_manager.add_entry(
                question, answer,
                source='manual',
                deduplicate=False,
            )
            msg = 'Saved to FAQ!' if ok else 'Already in FAQ'
            self.statusBar().showMessage(msg, 3000)
        else:
            self.statusBar().showMessage('FAQ manager not available', 3000)

    def _handle_apply_all_link(self, encoded: str):
        """Open MultiFileDiffDialog for reviewing all changes at once."""
        import base64 as _b64, json as _json
        try:
            payload = _json.loads(_b64.b64decode(encoded).decode("utf-8"))
            changes = [(c["path"], c["mode"], c["code"]) for c in payload]
        except Exception as e:
            self.statusBar().showMessage(f"Could not parse changes: {e}", 4000)
            return

        root = (
            self.git_dock.repo_path
            if hasattr(self, "git_dock") and self.git_dock.repo_path
            else str(Path.cwd())
        )

        from ui.multi_file_diff_dialog import MultiFileDiffDialog
        dialog = MultiFileDiffDialog(changes, root, parent=self)
        if dialog.exec():
            for abs_path in dialog.applied_paths:
                self._reload_file_in_editors(abs_path)
                if hasattr(self, "repo_map") and self.repo_map:
                    self.repo_map.invalidate(abs_path)
            n = len(dialog.applied_paths)
            self.statusBar().showMessage(
                f"Applied {n} file{'s' if n != 1 else ''} successfully.",
                5000
            )

    def _handle_apply_link(self, encoded: str):
        try:
            payload   = base64.b64decode(encoded).decode("utf-8")
            sep1      = payload.index("|")
            sep2      = payload.index("|", sep1 + 1)
            file_path = payload[:sep1]
            mode      = payload[sep1 + 1:sep2]
            code      = payload[sep2 + 1:]
        except Exception as e:
            self.statusBar().showMessage(f"Could not parse apply link: {e}", 4000)
            return

        root = (self.git_dock.repo_path
                if hasattr(self, "git_dock") and self.git_dock.repo_path
                else None)
        abs_path = str((Path(root) / file_path).resolve()) if root else file_path

        from core.patch_applier import apply_function, apply_full, apply_perl_function
        from ai.worker import clean_code
        code = clean_code(code)  # strip markdown fences if AI wrapped the code
        if mode == "function":
            ok, msg = apply_function(abs_path, code, parent_widget=self)
        elif mode == "perl_function":
            ok, msg = apply_perl_function(abs_path, code, parent_widget=self)
        else:
            ok, msg = apply_full(abs_path, code, parent_widget=self)
        self.statusBar().showMessage(msg, 5000)
        if ok:
            self._reload_file_in_editors(abs_path)
            if hasattr(self, "repo_map") and self.repo_map:
                self.repo_map.invalidate(abs_path)

    def _handle_undo_link(self, encoded: str):
        try:
            file_path = base64.b64decode(encoded).decode("utf-8")
        except Exception as e:
            self.statusBar().showMessage(f"Could not parse undo link: {e}", 4000)
            return

        root = (self.git_dock.repo_path
                if hasattr(self, "git_dock") and self.git_dock.repo_path
                else None)
        abs_path = str((Path(root) / file_path).resolve()) if root else file_path

        from core.patch_applier import undo_last
        ok, msg = undo_last(abs_path)
        self.statusBar().showMessage(msg, 5000)
        if ok and hasattr(self, "repo_map") and self.repo_map:
            self.repo_map.invalidate(abs_path)
