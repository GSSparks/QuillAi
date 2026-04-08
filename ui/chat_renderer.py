import re
import base64
import markdown
from markdown.extensions.fenced_code import FencedCodeExtension
from markdown.extensions.tables import TableExtension
from pygments import highlight
from pygments.lexers import get_lexer_by_name, guess_lexer, TextLexer
from pygments.formatters import HtmlFormatter
from pygments.util import ClassNotFound
import ast
from pathlib import Path
from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import QApplication

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
    _FULL_EXTS = {
        '.yml', '.yaml', '.json', '.toml', '.xml', '.ini', '.cfg', '.conf',
        '.sh', '.bash', '.zsh', '.fish',
        '.pl', '.pm', '.t',
        '.html', '.htm', '.css', '.js', '.ts',
        '.rs', '.go', '.c', '.cpp', '.h', '.hpp', '.java',
        '.tf', '.hcl', '.nix', '.md', '.rst', '.txt', '.sql',
    }

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
                    # Multiple top-level symbols → full file replace
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
    Strip <file_change> tags from *text* and return:
      (cleaned_text, [(path, mode, code), ...])
    """
    changes = []
    def _collect(m):
        changes.append((m.group(1), m.group(2), m.group(3).strip()))
        return ""   # remove tag from text
    cleaned = _RE_FILE_CHANGE.sub(_collect, text)
    return cleaned, changes


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
        s = _safe_styles(build_chat_styles(get_theme()))
        escaped = (text.replace("&", "&amp;")
                       .replace("<", "&lt;")
                       .replace(">", "&gt;")
                       .replace("\n", "<br>"))

        # Vertical spacer before bubble
        # User bubble: table-based right alignment — Qt ignores inline-block
        # 25% empty left cell pushes content to the right
        # Separate "You" label row, then clear spacer before QuillAI label
        html = (
            # Top spacer
            f'<table width="100%" cellpadding="0" cellspacing="0">'
            f'<tr><td height="8"></td></tr></table>'

            # Bubble row
            f'<table width="100%" cellpadding="0" cellspacing="4">'
            f'<tr>'
            f'<td width="20%"></td>'
            f'<td width="80%" style="{s["user_bubble_td"]}">{escaped}</td>'
            f'</tr></table>'

            # "You" label
            f'<table width="100%" cellpadding="0" cellspacing="0">'
            f'<tr><td align="right" style="{s["user_label_td"]}">You</td></tr>'
            f'</table>'

            # Spacer between "You" and "QuillAI"
            f'<table width="100%" cellpadding="0" cellspacing="0">'
            f'<tr><td height="10"></td></tr></table>'

            # QuillAI label — on its own row, clearly separated
            f'<table width="100%" cellpadding="0" cellspacing="0">'
            f'<tr><td style="{s["ai_label_td"]}">QuillAI</td></tr>'
            f'</table>'

            # Small spacer before response starts
            f'<table width="100%" cellpadding="0" cellspacing="0">'
            f'<tr><td height="4"></td></tr></table>'
        )

        self.chat_history.moveCursor(QTextCursor.MoveOperation.End)
        self.chat_history.insertHtml(html)
        self.chat_history.moveCursor(QTextCursor.MoveOperation.End)
        self._stream_start_pos = self.chat_history.textCursor().position()
        self.chat_history.ensureCursorVisible()

    # ── Streaming ─────────────────────────────────────────────────────────

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
        # Extract any file_change tags before rendering
        clean_response, file_changes = _extract_file_changes(full_response)

        # Render full response so code blocks stay visible in chat
        rendered = self._render_ai_response(clean_response if clean_response.strip() else full_response.replace('<file_change', '<!--').replace('</file_change>', '-->'))

        # Auto-detect applicable code blocks if no explicit tags
        if not file_changes:
            editor = self.current_editor()
            if editor and getattr(editor, 'file_path', None):
                file_changes = _autodetect_changes(
                    clean_response, editor.file_path
                )

        # Append apply buttons for each file change
        if file_changes:
            rendered += self._render_apply_buttons(file_changes)

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

        # ── Fenced code blocks ────────────────────────────────────
        def replace_fenced(m):
            inner      = m.group(1)
            # Unescape HTML entities that markdown introduced into the code content
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

        # ── Inline code ───────────────────────────────────────────
        raw_html = re.sub(
            r"<code>([^<]+)</code>",
            lambda m: f'<code style="{s["inline_code"]}">{m.group(1)}</code>',
            raw_html,
        )

        # ── Markdown tables ───────────────────────────────────────
        # Qt renders <table> but needs explicit cell styling to look right
        raw_html = re.sub(
            r"<table>",
            f'<table width="100%" cellpadding="6" cellspacing="0" '
            f'style="{s["md_table"]}">',
            raw_html,
        )
        raw_html = re.sub(r"<thead>", "<thead>", raw_html)
        raw_html = re.sub(
            r"<th>",
            f'<th style="{s["md_th"]}">',
            raw_html,
        )
        raw_html = re.sub(
            r"<td>",
            f'<td style="{s["md_td"]}">',
            raw_html,
        )
        raw_html = re.sub(
            r"<tr>",
            f'<tr style="{s["md_tr"]}">',
            raw_html,
        )

        # ── Prose elements ────────────────────────────────────────
        raw_html = re.sub(r"<p>",       f'<p style="{s["prose_p"]}">',    raw_html)
        raw_html = re.sub(r"<ul>",      f'<ul style="{s["ul"]}">',        raw_html)
        raw_html = re.sub(r"<ol>",      f'<ol style="{s["ol"]}">',        raw_html)
        raw_html = re.sub(r"<li>",      f'<li style="{s["prose_li"]}">',  raw_html)
        raw_html = re.sub(r"<h1>",      f'<p style="{s["heading_1"]}">',  raw_html)
        raw_html = re.sub(r"</h1>",     "</p>",                            raw_html)
        raw_html = re.sub(r"<h2>",      f'<p style="{s["heading_2"]}">',  raw_html)
        raw_html = re.sub(r"</h2>",     "</p>",                            raw_html)
        raw_html = re.sub(r"<h3>",      f'<p style="{s["heading_3"]}">',  raw_html)
        raw_html = re.sub(r"</h3>",     "</p>",                            raw_html)
        raw_html = re.sub(r"<hr\s*/?>", f'<hr style="{s["hr"]}"/>',       raw_html)
        raw_html = re.sub(r"<strong>",  f'<strong style="{s["strong"]}">',raw_html)
        raw_html = re.sub(r"<em>",      f'<em style="{s["em"]}">',        raw_html)

        # Wrap response — table so it doesn't inline with surrounding content
        # No <p> wrapper — Qt inlines <p> content, collapsing spacing
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
        # Qt's rich text renderer displays &quot; literally — unescape it
        return result.replace("&quot;", '"')

    # ── Memory & conversation ─────────────────────────────────────────────

    def _restore_conversation(self, user_message: str, ai_response: str):
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
        self.chat_panel.chat_history.clear()
        self.current_ai_raw_text = ""
        self._stream_start_pos   = 0
        saved = self.memory_manager.load_chat_history()
        if saved:
            self.chat_panel.chat_history.setHtml(saved)
            self.chat_panel.chat_history.moveCursor(QTextCursor.MoveOperation.End)

    def _render_apply_buttons(self, changes: list) -> str:
        """Render apply/undo button row for each file_change."""
        s = _safe_styles(build_chat_styles(get_theme()))
        t = get_theme()
        rows = []
        for file_path, mode, code in changes:
            encoded = base64.b64encode(
                f"{file_path}|{mode}|{code}".encode("utf-8")
            ).decode("utf-8")
            fname = file_path.split("/")[-1]
            apply_url = f"apply:{encoded}"
            undo_url  = f"undo:{base64.b64encode(file_path.encode()).decode()}"
            # Build summary line from code
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

    def handle_chat_link(self, url: QUrl):
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
        elif url_str.startswith("apply:"):
            self._handle_apply_link(url_str[6:])
        elif url_str.startswith("undo:"):
            self._handle_undo_link(url_str[5:])

    def _reload_file_in_editors(self, abs_path: str):
        """Reload any editor pane showing abs_path from disk."""
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

        # Resolve path relative to project root
        root = (self.git_dock.repo_path
                if hasattr(self, "git_dock") and self.git_dock.repo_path
                else None)
        abs_path = str((Path(root) / file_path).resolve()) if root else file_path

        from core.patch_applier import apply_function, apply_full, apply_perl_function
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
