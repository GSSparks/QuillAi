import re
import base64
import markdown
from markdown.extensions.fenced_code import FencedCodeExtension
from markdown.extensions.tables import TableExtension
from pygments import highlight
from pygments.lexers import get_lexer_by_name, guess_lexer, TextLexer
from pygments.formatters import HtmlFormatter
from pygments.util import ClassNotFound
from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import QApplication

from ui.theme import get_theme, build_chat_styles, FONT_CODE


class ChatRenderer:
    """
    Mixin class providing all chat rendering, streaming, and memory
    summarization for CodeEditor. Import and inherit alongside QMainWindow.
    """

    # ── User message ──────────────────────────────────────────────────────

    def _append_user_message(self, text: str):
        escaped = (text.replace("&", "&amp;")
                       .replace("<", "&lt;")
                       .replace(">", "&gt;")
                       .replace("\n", "<br>"))

        s = build_chat_styles(get_theme())

        html = (
            f'<table width="100%" cellpadding="0" cellspacing="0" '
            f'style="margin:8px 0;">'
            f'<tr>'
            f'<td width="30%"></td>'
            f'<td width="70%" align="right">'
            f'<table cellpadding="0" cellspacing="0" align="right" width="100%">'
            f'<tr><td style="{s["user_bubble_td"]}">{escaped}</td></tr>'
            f'<tr><td align="right" style="{s["user_label"]}">You</td></tr>'
            f'</table></td></tr></table>'
            f'<p style="{s["ai_label_p"]}">QuillAI</p>'
            f'<p style="margin:0; font-size:1px;">&nbsp;</p>'
        )

        self.chat_history.moveCursor(QTextCursor.MoveOperation.End)
        self.chat_history.insertHtml(html)
        self.chat_history.moveCursor(QTextCursor.MoveOperation.End)
        self._stream_start_pos = self.chat_history.textCursor().position()
        self.chat_history.ensureCursorVisible()

    # ── Streaming ─────────────────────────────────────────────────────────

    def append_chat_stream(self, text: str):
        self.current_ai_raw_text += text
        self._stream_buffer = getattr(self, '_stream_buffer', '') + text

        should_render = (
            '\n' in self._stream_buffer or
            self._stream_buffer.endswith('```') or
            len(self._stream_buffer) > 80
        )
        if should_render:
            self._flush_stream_buffer()

    def _flush_stream_buffer(self):
        if not self.current_ai_raw_text.strip():
            return
        start_pos = getattr(self, '_stream_start_pos', 0)
        if start_pos == 0:
            return

        cursor = self.chat_history.textCursor()
        cursor.setPosition(start_pos)
        cursor.movePosition(QTextCursor.MoveOperation.End,
                            QTextCursor.MoveMode.KeepAnchor)
        cursor.removeSelectedText()
        self.chat_history.setTextCursor(cursor)

        rendered = self._render_partial_response(self.current_ai_raw_text)
        self.chat_history.moveCursor(QTextCursor.MoveOperation.End)
        self.chat_history.insertHtml(rendered)
        self.chat_history.moveCursor(QTextCursor.MoveOperation.End)
        self.chat_history.ensureCursorVisible()
        self._stream_buffer = ''

    def _render_partial_response(self, text: str) -> str:
        open_fences = len(re.findall(r'^```', text, re.MULTILINE))
        if open_fences % 2 == 1:
            text = text + '\n```'
        return self._render_ai_response(text)

    def chat_stream_finished(self):
        full_response = self.current_ai_raw_text
        start_pos = getattr(self, '_stream_start_pos', 0)

        if start_pos > 0:
            cursor = self.chat_history.textCursor()
            cursor.setPosition(start_pos)
            cursor.movePosition(QTextCursor.MoveOperation.End,
                                QTextCursor.MoveMode.KeepAnchor)
            cursor.removeSelectedText()
            self.chat_history.setTextCursor(cursor)

        rendered = self._render_ai_response(full_response)
        self.chat_history.moveCursor(QTextCursor.MoveOperation.End)
        self.chat_history.insertHtml(rendered)
        self.chat_history.moveCursor(QTextCursor.MoveOperation.End)
        self.chat_history.ensureCursorVisible()

        if full_response.strip():
            self.memory_manager.add_turn("assistant", full_response) 
            self._summarize_conversation_to_memory(full_response)

        self.memory_manager.save_chat_history(self.chat_history.toHtml())
        self.current_ai_raw_text = ""
        self._ai_response_buffer = ""
        self._stream_buffer = ""
        self._stream_start_pos = 0

    # ── Markdown rendering ────────────────────────────────────────────────

    def _render_ai_response(self, text: str) -> str:
        s = build_chat_styles(get_theme())
    
        # Post-process the HTML to inject QuillAI's theme styles
        # and add copy buttons to code blocks
        md = markdown.Markdown(extensions=[
            FencedCodeExtension(),
            TableExtension(),
            "markdown.extensions.nl2br",
            "markdown.extensions.sane_lists",
        ])
    
        raw_html = md.convert(text)
    
        # Inject copy buttons + theme styles into code blocks
        def replace_code_block(m):
            inner      = m.group(1)
            lang_match = re.search(r'class="language-(\w+)"', m.group(0))
            lang       = lang_match.group(1).lower() if lang_match else ""
            lang_label = lang.upper() if lang else "CODE"
    
            highlighted = self._highlight_code_block(inner, lang)
            encoded     = base64.b64encode(inner.encode("utf-8")).decode("utf-8")
    
            return (
                f'<table width="100%" cellpadding="0" cellspacing="0" style="margin:8px 0;">'
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
            r'<code[^>]*>(.*?)</code>',
            replace_code_block,
            raw_html,
            flags=re.DOTALL
        )
    
        # Wrap prose elements with theme styles
        raw_html = re.sub(r'<p>',          f'<p style="{s["prose_p"]}">',    raw_html)
        raw_html = re.sub(r'<ul>',         f'<ul style="{s["ul"]}">',        raw_html)
        raw_html = re.sub(r'<ol>',         f'<ol style="{s["ol"]}">',        raw_html)
        raw_html = re.sub(r'<li>',         f'<li style="{s["prose_li"]}">',  raw_html)
        raw_html = re.sub(r'<h1>',         f'<p style="{s["heading_1"]}">',  raw_html)
        raw_html = re.sub(r'</h1>',        '</p>',                           raw_html)
        raw_html = re.sub(r'<h2>',         f'<p style="{s["heading_2"]}">',  raw_html)
        raw_html = re.sub(r'</h2>',        '</p>',                           raw_html)
        raw_html = re.sub(r'<h3>',         f'<p style="{s["heading_3"]}">',  raw_html)
        raw_html = re.sub(r'</h3>',        '</p>',                           raw_html)
        raw_html = re.sub(r'<hr\s*/>',     f'<hr style="{s["hr"]}"/>',       raw_html)
        raw_html = re.sub(
            r'<code>([^<]+)</code>',
            lambda m: f'<code style="{s["inline_code"]}">{m.group(1)}</code>',
            raw_html
        )
    
        return (
            f'<table width="100%" cellpadding="0" cellspacing="0" '
            f'style="margin:0 0 12px 0;">'
            f'<tr><td style="padding:0;">{raw_html}</td></tr></table>'
        )

    # ── Syntax highlighting ───────────────────────────────────────────────

    def _highlight_code_block(self, code: str, lang: str = "") -> str:
        try:
            lexer = get_lexer_by_name(lang) if lang else guess_lexer(code)
        except ClassNotFound:
            lexer = TextLexer()
    
        formatter = HtmlFormatter(
            nowrap=True,        # no wrapping <div>, just the spans
            noclasses=True,     # inline styles, no external CSS needed
            style="monokai",    # closest to your current Gruvbox-ish palette
        )
    
        return highlight(code, lexer, formatter)

    # ── Memory & conversation ─────────────────────────────────────────────

    def _summarize_conversation_to_memory(self, ai_response: str):
        try:
            last_user = getattr(self, '_last_user_message', "")
            if not last_user:
                return

            extracted = self.memory_manager.extract_facts_from_exchange(
                last_user, ai_response
            )
            for fact in extracted:
                self.memory_manager.add_fact(fact, project_scoped=False)
            if extracted and hasattr(self, 'memory_panel'):
                self.memory_panel.refresh()

            self.intent_tracker.record_chat_exchange(last_user, ai_response[:500])

            summary = last_user[:80] + ("..." if len(last_user) > 80 else "")
            self.memory_manager.add_conversation(
                summary=summary,
                user_message=last_user,
                ai_response=ai_response[:2000],
            )
            if hasattr(self, 'memory_panel'):
                self.memory_panel.refresh()

        except Exception as e:
            import traceback
            print(f"_summarize_conversation_to_memory error: {e}")
            traceback.print_exc()

    def _restore_conversation(self, user_message: str, ai_response: str):
        self.chat_panel.expand()
        self.chat_panel.switch_to_chat()
        self.chat_history.clear()
        self.current_ai_raw_text = ""
        self._ai_response_buffer = ""
        self._stream_start_pos = 0

        self._append_user_message(user_message)
        self.chat_history.insertHtml(self._render_ai_response(ai_response))
        self.chat_history.moveCursor(QTextCursor.MoveOperation.End)
        self.statusBar().showMessage(
            "Past conversation restored — send a message to continue it.", 5000
        )

    def load_snippet_to_chat(self, text: str):
        self.chat_panel.expand()
        self.chat_panel.switch_to_chat()

        chat_input   = self.chat_panel.chat_input
        current_input = chat_input.toPlainText()
        new_text     = f"```python\n{text}\n```\n"
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
        self._stream_start_pos = 0
        saved = self.memory_manager.load_chat_history()
        if saved:
            self.chat_panel.chat_history.setHtml(saved)
            self.chat_panel.chat_history.moveCursor(QTextCursor.MoveOperation.End)

    def handle_chat_link(self, url: QUrl):
        url_str = url.toString()
        if url_str.startswith("insert:"):
            decoded = base64.b64decode(url_str.replace("insert:", "")).decode('utf-8')
            editor = self.current_editor()
            if editor:
                editor.textCursor().insertText(decoded)
                editor.setFocus()
        elif url_str.startswith("copy:"):
            decoded = base64.b64decode(url_str.replace("copy:", "")).decode('utf-8')
            QApplication.clipboard().setText(decoded)
            self.statusBar().showMessage("Code copied to clipboard.", 2000)