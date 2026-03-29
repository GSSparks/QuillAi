import re
import base64
from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import QApplication
from ui.theme import get_theme


class ChatRenderer:
    """
    Mixin class providing all chat rendering, streaming, and memory
    summarization for CodeEditor. Import and inherit alongside QMainWindow.
    """

    # ── User message ──────────────────────────────────────────────

    def _append_user_message(self, text: str):
        escaped = (text.replace("&", "&amp;")
                       .replace("<", "&lt;")
                       .replace(">", "&gt;")
                       .replace("\n", "<br>"))
    
        t = get_theme(
            self.settings_manager.get('theme')
            if hasattr(self, 'settings_manager') else None
        )
    
        # Pull colors out first — can't use dict keys inside f-strings safely
        bubble_bg  = t['chat_user_bubble']
        fg1        = t['fg1']
        fg4        = t['fg4']
        ai_label   = t['chat_ai_label']
        bg1        = t['bg1']
    
        html = (
            f'<table width="100%" cellpadding="0" cellspacing="0" '
            f'style="margin:8px 0;">'
            f'<tr>'
            f'<td width="30%"></td>'
            f'<td width="70%" align="right">'
            f'<table cellpadding="0" cellspacing="0" align="right" width="100%">'
            f'<tr><td style="background-color:{bubble_bg}; '
            f'border-radius:18px 18px 4px 18px; '
            f'padding:10px 14px; color:{fg1}; '
            f'font-family:Inter,sans-serif; font-size:10pt; '
            f'line-height:1.5;">{escaped}</td></tr>'
            f'<tr><td align="right" style="padding:2px 4px 8px 0; '
            f'color:{fg4}; font-size:8pt; '
            f'font-family:Inter,sans-serif;">You</td></tr>'
            f'</table></td></tr></table>'
            f'<p style="margin:8px 0 2px 4px; color:{ai_label}; '
            f'font-size:8pt; font-family:Inter,sans-serif; '
            f'font-weight:bold;">QuillAI</p>'
            f'<p style="margin:0; font-size:1px;">&nbsp;</p>'
        )
    
        self.chat_history.moveCursor(QTextCursor.MoveOperation.End)
        self.chat_history.insertHtml(html)
        self.chat_history.moveCursor(QTextCursor.MoveOperation.End)
        self._stream_start_pos = self.chat_history.textCursor().position()
        self.chat_history.ensureCursorVisible()

    # ── Streaming ─────────────────────────────────────────────────

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
            self._summarize_conversation_to_memory(full_response)

        self.memory_manager.save_chat_history(self.chat_history.toHtml())
        self.current_ai_raw_text = ""
        self._ai_response_buffer = ""
        self._stream_buffer = ""
        self._stream_start_pos = 0

    # ── Markdown rendering ────────────────────────────────────────

    def _apply_inline_markdown(self, text: str) -> str:
        text = re.sub(
            r'`([^`]+)`',
            r'<code style="background:#2A2A2D;color:#CE9178;'
            r'padding:1px 5px;border-radius:3px;'
            r'font-family:JetBrains Mono,monospace;font-size:9pt;">'
            r'\1</code>',
            text
        )
        text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
        text = re.sub(r'__(.+?)__', r'<strong>\1</strong>', text)
        text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
        text = re.sub(r'_(.+?)_', r'<em>\1</em>', text)
        return text

    def _render_markdown_text(self, text: str) -> str:
        t = get_theme(
            self.settings_manager.get('theme')
            if hasattr(self, 'settings_manager') else None
        )
        fg1     = t['fg1']
        blue    = t['blue']
        border  = t['border']
        bg1     = t['bg1']
        
        lines = text.split('\n')
        html_lines = []
        in_ul = False
        in_ol = False

        for line in lines:
            stripped = line.strip()

            if re.match(r'^[-*+]\s+', stripped):
                if not in_ul:
                    if in_ol:
                        html_lines.append('</ol>')
                        in_ol = False
                    html_lines.append(
                        '<ul style="margin:4px 0 4px 16px; padding:0; '
                        'list-style-type:disc;">'
                    )
                    in_ul = True
                content = re.sub(r'^[-*+]\s+', '', stripped)
                html_lines.append(
                    f'<li style="color:{fg1}; font-family:JetBrains Mono,'
                    f'monospace; font-size:10pt; line-height:1.8; '
                    f'margin:2px 0;">{self._apply_inline_markdown(content)}</li>'
                )
                continue

            if re.match(r'^\d+\.\s+', stripped):
                if not in_ol:
                    if in_ul:
                        html_lines.append('</ul>')
                        in_ul = False
                    html_lines.append('<ol style="margin:4px 0 4px 16px; padding:0;">')
                    in_ol = True
                content = re.sub(r'^\d+\.\s+', '', stripped)
                html_lines.append(
                    f'<li style="color:{fg1}; font-family:JetBrains Mono,'
                    f'monospace; font-size:10pt; line-height:1.8; '
                    f'margin:2px 0;">{self._apply_inline_markdown(content)}</li>'
                )
                continue

            if in_ul:
                html_lines.append('</ul>')
                in_ul = False
            if in_ol:
                html_lines.append('</ol>')
                in_ol = False

            if re.match(r'^#{1,3}\s', stripped):
                level = len(re.match(r'^(#+)', stripped).group(1))
                content = re.sub(r'^#+\s+', '', stripped)
                sizes = {1: '14pt', 2: '12pt', 3: '11pt'}
                html_lines.append(
                    f'<p style="margin:10px 0 4px 0; color:{blue}; '
                    f'font-weight:bold; font-family:JetBrains Mono,monospace; '
                    f'font-size:{sizes.get(level, "11pt")};">'
                    f'{self._apply_inline_markdown(content)}</p>'
                )
                continue

            if re.match(r'^[-*_]{3,}\s*$', stripped):
                html_lines.append(
                    '<hr style="border:none; border-top:1px solid {border}; '
                    'margin:8px 0;"/>'
                )
                continue

            if not stripped:
                html_lines.append('<p style="margin:4px 0;">&nbsp;</p>')
                continue

            html_lines.append(
                f'<p style="margin:2px 0; color:{fg1}; '
                f'font-family:JetBrains Mono,monospace; '
                f'font-size:10pt; line-height:1.8;">'
                f'{self._apply_inline_markdown(stripped)}</p>'
            )

        if in_ul:
            html_lines.append('</ul>')
        if in_ol:
            html_lines.append('</ol>')

        return ''.join(html_lines)

    def _render_ai_response(self, text: str) -> str:
        t = get_theme(
            self.settings_manager.get('theme')
            if hasattr(self, 'settings_manager') else None
        )
    
        # Pull colors out before f-strings
        code_header_bg = t['bg1']
        code_body_bg   = t['bg0_hard']
        border         = t['border']
        fg1            = t['fg1']
        fg4            = t['fg4']
        blue           = t['blue']
    
        parts = re.split(r'(```(?:[\w]*)\n.*?```)', text, flags=re.DOTALL)
        html_parts = []
    
        for part in parts:
            if part.startswith('```'):
                lang_match = re.match(r'```([\w]*)\n?', part)
                lang = lang_match.group(1).lower() if lang_match else ""
                code = re.sub(r'^```[\w]*\n?', '', part)
                code = re.sub(r'\n?```$', '', code)
    
                highlighted = self._highlight_code_block(code, lang)
                encoded = base64.b64encode(code.encode('utf-8')).decode('utf-8')
                lang_label = lang.upper() if lang else "CODE"
    
                html_parts.append(
                    f'<table width="100%" cellpadding="0" cellspacing="0" '
                    f'style="margin:8px 0;">'
                    f'<tr><td width="100%" style="background-color:{code_header_bg}; '
                    f'border-radius:12px 12px 0 0; padding:4px 12px;">'
                    f'<span style="color:{fg4}; font-family:JetBrains Mono,monospace; '
                    f'font-size:8pt;">{lang_label}</span>'
                    f'&nbsp;&nbsp;'
                    f'<a href="copy:{encoded}" style="color:{blue}; '
                    f'font-family:Hack,monospace; font-size:8pt; '
                    f'text-decoration:none;">⎘ Copy</a>'
                    f'</td></tr>'
                    f'<tr><td width="100%" style="background-color:{code_body_bg}; '
                    f'border:1px solid {border}; border-radius:0 0 12px 12px; '
                    f'padding:12px 16px;">'
                    f'<pre style="margin:0; '
                    f'font-family:JetBrains Mono,Courier New,monospace; '
                    f'font-size:10pt; line-height:1.8; white-space:pre; '
                    f'color:{fg1};">{highlighted}</pre>'
                    f'</td></tr></table>'
                )
            else:
                if not part.strip():
                    continue
                escaped = (part.replace("&", "&amp;")
                              .replace("<", "&lt;")
                              .replace(">", "&gt;"))
                html_parts.append(self._render_markdown_text(escaped))
    
        inner = ''.join(html_parts)
        return (
            f'<table width="100%" cellpadding="0" cellspacing="0" '
            f'style="margin:0 0 12px 0;">'
            f'<tr><td width="100%" style="padding:0;">'
            f'{inner}'
            f'</td></tr></table>'
        )

    # ── Syntax highlighting ───────────────────────────────────────

    def _highlight_code_block(self, code: str, lang: str = "") -> str:
        escaped = (code.replace("&", "&amp;")
                       .replace("<", "&lt;")
                       .replace(">", "&gt;"))

        if not lang:
            if re.search(r'\bdef \w+|import \w+|class \w+:', escaped):
                lang = "python"
            elif re.search(r'\bfunction\b|\bconst\b|\blet\b|\bvar\b', escaped):
                lang = "javascript"
            elif re.search(r'^\s*-\s+\w+:|hosts:|tasks:', escaped, re.MULTILINE):
                lang = "yaml"
            elif re.search(r'#!/.*bash|echo\b|\bfi\b|\bdone\b', escaped):
                lang = "bash"
            elif re.search(r'nixpkgs|mkShell|buildInputs', escaped):
                lang = "nix"

        if lang in ("python", "py"):
            keywords = (r'\b(def|class|import|from|return|if|elif|else|for|while|'
                        r'in|and|or|not|True|False|None|pass|try|except|with|as|'
                        r'async|await|lambda|yield|raise|break|continue|global|'
                        r'nonlocal|del|assert|is)\b')
            builtins = (r'\b(print|len|range|str|int|float|list|dict|set|tuple|'
                        r'bool|type|isinstance|hasattr|getattr|setattr|open|'
                        r'enumerate|zip|map|filter|any|all|sum|min|max|abs|'
                        r'round|sorted|reversed|super|self)\b')

            string_map = {}
            counter = [0]

            def protect_string(m):
                key = f"\x00STR{counter[0]}\x00"
                counter[0] += 1
                string_map[key] = f'<span style="color:#E6DB74;">{m.group(0)}</span>'
                return key

            escaped = re.sub(r'""".*?"""|\'\'\'.*?\'\'\'',
                             protect_string, escaped, flags=re.DOTALL)
            escaped = re.sub(r'"[^"\n]*"|\'[^\'\n]*\'', protect_string, escaped)

            def protect_comment(m):
                key = f"\x00CMT{counter[0]}\x00"
                counter[0] += 1
                string_map[key] = (
                    f'<span style="color:#75715E;font-style:italic;">'
                    f'{m.group(0)}</span>'
                )
                return key

            escaped = re.sub(r'#[^\n]*', protect_comment, escaped)
            escaped = re.sub(r'(@\w+)',
                             r'<span style="color:#A6E22E;">\1</span>', escaped)
            escaped = re.sub(keywords,
                             r'<span style="color:#F92672;font-weight:bold;">\1</span>',
                             escaped)
            escaped = re.sub(builtins,
                             r'<span style="color:#66D9EF;font-style:italic;">\1</span>',
                             escaped)
            escaped = re.sub(r'\b(\d+\.?\d*)\b',
                             r'<span style="color:#AE81FF;">\1</span>', escaped)
            escaped = re.sub(
                r'(def|class)\s+(<span[^>]*>)?(\w+)',
                lambda m: (f'{m.group(1)} '
                           f'<span style="color:#A6E22E;font-weight:bold;">'
                           f'{m.group(3)}</span>'),
                escaped
            )
            for key, value in string_map.items():
                escaped = escaped.replace(key, value)

        elif lang in ("javascript", "js", "typescript", "ts"):
            keywords = (r'\b(function|const|let|var|return|if|else|for|while|'
                        r'class|import|export|from|new|this|typeof|instanceof|'
                        r'async|await|try|catch|throw|true|false|null|undefined|'
                        r'switch|case|break|continue|default|of|in)\b')
            escaped = re.sub(r'"[^"\n]*"|\'[^\'\n]*\'|`[^`]*`',
                             lambda m: f'<span style="color:#E6DB74;">{m.group(0)}</span>',
                             escaped)
            escaped = re.sub(r'//[^\n]*',
                             lambda m: f'<span style="color:#75715E;font-style:italic;">{m.group(0)}</span>',
                             escaped)
            escaped = re.sub(keywords,
                             r'<span style="color:#F92672;font-weight:bold;">\1</span>',
                             escaped)
            escaped = re.sub(r'\b(\d+\.?\d*)\b',
                             r'<span style="color:#AE81FF;">\1</span>', escaped)

        elif lang in ("bash", "sh"):
            escaped = re.sub(r'#[^\n]*',
                             lambda m: f'<span style="color:#75715E;font-style:italic;">{m.group(0)}</span>',
                             escaped)
            escaped = re.sub(r'"[^"\n]*"|\'[^\'\n]*\'',
                             lambda m: f'<span style="color:#E6DB74;">{m.group(0)}</span>',
                             escaped)
            escaped = re.sub(r'\$\{?\w+\}?',
                             lambda m: f'<span style="color:#AE81FF;">{m.group(0)}</span>',
                             escaped)
            escaped = re.sub(
                r'\b(if|then|else|elif|fi|for|while|do|done|case|esac|'
                r'function|return|export|local|echo|source)\b',
                r'<span style="color:#F92672;font-weight:bold;">\1</span>',
                escaped
            )

        elif lang in ("yaml", "yml", "ansible"):
            lines = escaped.split('\n')
            result = []
            for line in lines:
                line = re.sub(
                    r'^(\s*)(\w[\w\s]*?)(:)',
                    r'\1<span style="color:#66D9EF;">\2</span>\3',
                    line
                )
                line = re.sub(
                    r'(#[^\n]*)',
                    r'<span style="color:#75715E;font-style:italic;">\1</span>',
                    line
                )
                line = re.sub(
                    r':\s*(["\'].*?["\'])',
                    lambda m: f': <span style="color:#E6DB74;">{m.group(1)}</span>',
                    line
                )
                result.append(line)
            escaped = '\n'.join(result)

        elif lang in ("nix",):
            escaped = re.sub(r'#[^\n]*',
                             lambda m: f'<span style="color:#75715E;font-style:italic;">{m.group(0)}</span>',
                             escaped)
            escaped = re.sub(r'"[^"\n]*"',
                             lambda m: f'<span style="color:#E6DB74;">{m.group(0)}</span>',
                             escaped)
            escaped = re.sub(
                r'\b(let|in|with|rec|if|then|else|import|inherit|true|false|null)\b',
                r'<span style="color:#F92672;font-weight:bold;">\1</span>',
                escaped
            )

        return escaped

    # ── Memory & conversation ─────────────────────────────────────

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

        chat_input = self.chat_panel.chat_input
        current_input = chat_input.toPlainText()
        new_text = f"```python\n{text}\n```\n"
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