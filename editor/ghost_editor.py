from PyQt6.QtWidgets import QPlainTextEdit, QWidget, QTextEdit, QMenu, QLabel
from PyQt6.QtGui import QPainter, QColor, QFontMetrics, QTextCursor, QFont, QTextFormat, QAction, QTextCharFormat, QTextBlockFormat, QTextOption, QIcon
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QRect, QSize, QTimer
import re
import os
import ast
import difflib
import subprocess
import json

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

from ai.worker import AIWorker
from editor.multi_cursor import MultiCursorManager
from ui.theme import (
    get_theme, theme_signals,
    build_editor_stylesheet,
    build_minimap_stylesheet,
    build_jump_bar_stylesheet,
    build_color_swatch_stylesheet,
    QFONT_CODE,
)
from ui.lsp_editor import LspEditorMixin

# ==========================================
# Professional Snippet Manager
# ==========================================
class SnippetManager:
    """Kept for backwards compatibility with insert_snippet.
    The actual palette UI lives in ui/snippet_palette.py."""
    def get_code(self, name):
        from ui.snippet_palette import DEFAULT_SNIPPETS
        for s in DEFAULT_SNIPPETS:
            if s["name"] == name:
                return s["code"]
        return ""


class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.codeEditor = editor

    def sizeHint(self):
        return QSize(self.codeEditor.line_number_area_width(), 0)

    def paintEvent(self, event):
        self.codeEditor.line_number_area_paint_event(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # Map click Y to editor viewport Y, accounting for scroll
            y = event.pos().y()
            block = self.codeEditor.firstVisibleBlock()
            offset = self.codeEditor.contentOffset()
            while block.isValid():
                geom = self.codeEditor.blockBoundingGeometry(block).translated(offset)
                if geom.top() <= y <= geom.bottom():
                    self.codeEditor.select_full_line(block.blockNumber())
                    break
                if geom.top() > y:
                    break
                block = block.next()
            event.accept()


# ==========================================
# The "Microcode" Minimap
# ==========================================
class MinimapArea(QPlainTextEdit):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor

        self.setReadOnly(True)
        self.setWordWrapMode(QTextOption.WrapMode.NoWrap)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.editor.verticalScrollBar().valueChanged.connect(self.sync_scroll)

        font = QFont(QFONT_CODE, 4)
        font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        self.setFont(font)

        # Apply initial style and subscribe to theme changes
        self.apply_styles(get_theme())
        theme_signals.theme_changed.connect(self.apply_styles)

    def apply_styles(self, t: dict):
        self.setStyleSheet(build_minimap_stylesheet(t))

    def sync_scroll(self, value):
        e_max = self.editor.verticalScrollBar().maximum()
        m_max = self.verticalScrollBar().maximum()
        if e_max > 0:
            ratio = value / e_max
            self.verticalScrollBar().setValue(int(m_max * ratio))
        self.viewport().update()

    def mousePressEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            self.jump_to_click(event.pos())

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            self.jump_to_click(event.pos())

    def jump_to_click(self, pos):
        cursor = self.cursorForPosition(pos)
        block_number = cursor.blockNumber()
        editor_cursor = QTextCursor(
            self.editor.document().findBlockByNumber(block_number)
        )
        self.editor.setTextCursor(editor_cursor)
        self.editor.centerCursor()

    def wheelEvent(self, event):
        self.editor.wheelEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)

        t = get_theme()

        painter = QPainter(self.viewport())
        painter.setPen(Qt.PenStyle.NoPen)

        from PyQt6.QtGui import QColor
        highlight = QColor(t['accent'])
        highlight.setAlpha(20)
        painter.setBrush(highlight)

        fm_editor = QFontMetrics(self.editor.font())
        visible_lines_editor = (
            self.editor.viewport().height() / (fm_editor.height() * 1.5)
        )

        fm_minimap = QFontMetrics(self.font())
        top_block = self.editor.firstVisibleBlock()

        minimap_block = self.document().findBlockByNumber(top_block.blockNumber())
        if minimap_block.isValid():
            geom = self.blockBoundingGeometry(minimap_block).translated(
                self.contentOffset()
            )
            rect_y = geom.top()
            rect_height = visible_lines_editor * (fm_minimap.height() * 1.5)
            painter.drawRect(0, int(rect_y), self.width(), int(rect_height))


# ==========================================
# Main Ghost Editor
# ==========================================
class GhostEditor(LspEditorMixin, QPlainTextEdit):
    ai_started = pyqtSignal()
    ai_finished = pyqtSignal()
    error_help_requested = pyqtSignal(str, str, int)
    send_to_chat_requested = pyqtSignal(str)
    goto_file_requested = pyqtSignal(str, int, int)
    completion_accepted = pyqtSignal(str, str)  # accepted_text, context_before

    def __init__(self, settings_manager=None, intent_tracker=None):
        super().__init__()
        self.settings_manager = settings_manager
        self._t = get_theme()
        self.intent_tracker = intent_tracker
        self._setup_jump_bar()
        self._setup_inline_chat()

        self.setStyleSheet(build_editor_stylesheet(self._t))

        self.file_path = None
        self.ghost_text = ""
        self.snippet_manager = SnippetManager()
        self.setWordWrapMode(QTextOption.WrapMode.NoWrap)

        self.function_cursor = None
        self.function_active = False
        self.function_output = ""

        font = QFont(QFONT_CODE)
        font.setPointSize(10)
        font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        self.setFont(font)

        self.document().setDocumentMargin(12)

        self.original_text = ""
        self.line_changes = {}

        self.diff_timer = QTimer(self)
        self.diff_timer.setSingleShot(True)
        self.diff_timer.timeout.connect(self.calculate_diff)
        self.textChanged.connect(lambda: self.diff_timer.start(400))

        self.lint_timer = QTimer(self)
        self.lint_timer.setSingleShot(True)
        self.lint_timer.timeout.connect(self.run_linter)
        self.textChanged.connect(lambda: self.lint_timer.start(750))

        self.ai_suggest_timer = QTimer(self)
        self.ai_suggest_timer.setSingleShot(True)
        self.ai_suggest_timer.timeout.connect(self.trigger_inline_completion)
        self.textChanged.connect(self.handle_text_changed_for_ai)

        self.current_line_selection = []
        self.lint_selections = []
        self.bracket_selections = []
        self.mc_selections      = []
        self.multi_cursor       = MultiCursorManager()
        self.multi_cursor.setup(self)
        self.lsp_selections = []
        self.current_syntax_error = None

        # Git blame
        self._blame_data: dict[int, str] = {}   # line_number → "hash Author"
        self._blame_visible = False
        self._blame_width   = 0

        self.line_number_area = LineNumberArea(self)

        self.minimap_width = 100
        self.minimap = MinimapArea(self)

        self.blockCountChanged.connect(self.update_line_number_area_width)
        self.updateRequest.connect(self.update_line_number_area)
        self.update_line_number_area_width(0)
        self.setTabStopDistance(4 * self.fontMetrics().horizontalAdvance(' '))

        self.cursorPositionChanged.connect(self.highlight_current_line)
        self.cursorPositionChanged.connect(self._track_cursor_symbol)
        self.cursorPositionChanged.connect(self._highlight_matching_bracket)
        self.highlight_current_line()

        self._setup_color_swatch()
        self._swatch.mousePressEvent = lambda e: (
            self._on_color_swatch_clicked(
                self._get_hex_color_at_cursor()[0]
            ) if self._get_hex_color_at_cursor() else None
        )
        self.cursorPositionChanged.connect(self._update_color_swatch)

        # Subscribe to theme changes
        theme_signals.theme_changed.connect(self._on_theme_changed)

    # ── Theme handling ────────────────────────────────────────────────────

    def _on_theme_changed(self, t: dict):
        self._t = t
        self.setStyleSheet(build_editor_stylesheet(t))
        self._jump_bar.setStyleSheet(build_jump_bar_stylesheet(t))
        self.highlight_current_line()
        self.viewport().update()
        self.line_number_area.update()

    # ── Intent tracking ───────────────────────────────────────────────────

    def _get_language(self) -> str:
        if not self.file_path:
            return "code"
        ext_map = {
            '.py': 'Python', '.sh': 'Bash', '.bash': 'Bash',
            '.yml': 'YAML', '.yaml': 'YAML', '.nix': 'Nix',
            '.html': 'HTML', '.htm': 'HTML', '.js': 'JavaScript',
            '.ts': 'TypeScript', '.json': 'JSON', '.md': 'Markdown',
            '.lua': 'Lua', '.go': 'Go', '.rs': 'Rust',
            '.c': 'C', '.cpp': 'C++',
        }
        for ext, name in ext_map.items():
            if self.file_path.lower().endswith(ext):
                return name
        return "code"

    def _is_markdown_file(self) -> bool:
        """Returns True if the current file is a markdown file."""
        if not self.file_path:
            return False
        return self.file_path.lower().endswith(('.md', '.markdown'))

    def _track_cursor_symbol(self):
        if not self.intent_tracker:
            return
        text = self.toPlainText()
        pos = self.textCursor().position()
        symbol = self.intent_tracker.get_current_symbol(text, pos)
        if symbol:
            self.intent_tracker.record_cursor_symbol(symbol)

    def _get_intent_context(self) -> str:
        if not self.intent_tracker:
            return ""
        return self.intent_tracker.build_intent_context(
            current_file_path=self.file_path or "",
            language=self._get_language(),
        )

    # ── Function generation guard ─────────────────────────────────────────

    def _should_generate_function(self, line: str) -> bool:
        """
        Smarter check — only generate when the comment clearly
        describes a function/class to create. Never fires for
        markdown files, shebangs, or casual comments.
        """
        if self._is_markdown_file():
            return False

        if self.file_path and not self.file_path.lower().endswith('.py'):
            return False

        stripped = line.strip()

        if not stripped.startswith('#'):
            return False

        if stripped.startswith('#!'):
            return False

        comment_text = stripped.lstrip('#').strip().lower()

        if len(comment_text) < 8:
            return False

        if len(comment_text.split()) < 3:
            return False

        action_keywords = [
            'create', 'make', 'build', 'write', 'generate',
            'implement', 'add a', 'define', 'build a', 'make a',
            'create a', 'write a', 'implement a',
        ]
        if any(kw in comment_text for kw in action_keywords):
            code_concepts = [
                'function', 'class', 'method', 'def', 'decorator',
                'parser', 'handler', 'manager', 'helper', 'util',
                'api', 'endpoint', 'route', 'model', 'schema',
                'validator', 'serializer', 'middleware', 'hook',
                'worker', 'task', 'job', 'service', 'client',
                'server', 'database', 'query', 'cache',
            ]
            if any(concept in comment_text for concept in code_concepts):
                return True

        if re.search(r'\b(function|class|method)\s+(that|to|for|which)\b', comment_text):
            return True

        if re.match(r'^(todo|fixme|hack)\s*:?\s*', comment_text):
            todo_body = re.sub(r'^(todo|fixme|hack)\s*:?\s*', '', comment_text)
            if any(kw in todo_body for kw in ['implement', 'create', 'add', 'build', 'write']):
                return True

        return False

    # ── Jump bar ──────────────────────────────────────────────────────────

    def _setup_jump_bar(self):
        from PyQt6.QtWidgets import QLineEdit
        self._jump_bar = QLineEdit(self)
        self._jump_bar.setPlaceholderText("Go to line...")
        self._jump_bar.setStyleSheet(build_jump_bar_stylesheet(get_theme()))
        self._jump_bar.setFixedHeight(28)
        self._jump_bar.hide()
        self._jump_bar.installEventFilter(self)

    def _show_jump_bar(self):
        self._jump_bar.clear()
        self._jump_bar.show()
        self._jump_bar.setFocus()
        self._position_jump_bar()

    def _position_jump_bar(self):
        cr = self.contentsRect()
        hbar = self.horizontalScrollBar()
        scrollbar_height = hbar.height() if hbar.isVisible() else 20
        self._jump_bar.setGeometry(
            cr.left() + self.line_number_area_width(),
            cr.bottom() - 28 - scrollbar_height,
            cr.width() - self.line_number_area_width() - self.minimap_width,
            28
        )

    def _do_jump(self):
        text = self._jump_bar.text().strip()
        self._jump_bar.hide()
        try:
            line = int(text) - 1
            block = self.document().findBlockByNumber(max(0, line))
            if block.isValid():
                cursor = QTextCursor(block)
                self.setTextCursor(cursor)
                self.centerCursor()
                self.highlight_current_line()
        except ValueError:
            pass
        self.setFocus()

    def eventFilter(self, obj, event):
        from PyQt6.QtCore import QEvent
        if hasattr(self, '_jump_bar') and obj == self._jump_bar:
            if event.type() == QEvent.Type.KeyPress:
                if event.key() == Qt.Key.Key_Escape:
                    self._jump_bar.hide()
                    self.setFocus()
                    return True
                if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                    self._do_jump()
                    return True
        return super().eventFilter(obj, event)

    # ── Inline chat ───────────────────────────────────────────────────────

    def _setup_inline_chat(self):
        from editor.inline_chat import InlineChatWidget
        self._inline_chat = InlineChatWidget(self)
        self._inline_chat_thread = None
        self._inline_chat_worker = None
        self._inline_chat.hide()
        self._inline_chat.question_ready.connect(self._fire_inline_chat_worker)
        self._inline_chat.insert_requested.connect(self._insert_inline_chat_code)
        self._inline_chat.send_to_chat_requested.connect(self._relay_to_chat)
        self._inline_chat.closed.connect(self.setFocus)

    def show_inline_chat(self):
        if not hasattr(self, '_inline_chat'):
            self._setup_inline_chat()
        cursor = self.textCursor()
        line_num = cursor.blockNumber() + 1
        line_text = cursor.block().text()
        self._inline_chat.set_context(line_num, line_text)
        self._position_inline_chat()
        self._inline_chat.show()
        self._inline_chat.raise_()
        self._inline_chat.input.setFocus()

    def _position_inline_chat(self):
        cursor = self.textCursor()
        rect = self.cursorRect(cursor)
        x = self.line_number_area_width() + 20
        y = rect.bottom() + 4
        max_y = self.viewport().height() - self._inline_chat.sizeHint().height() - 10
        y = min(y, max_y)
        self._inline_chat.move(x, y)
        self._inline_chat.adjustSize()

    def _fire_inline_chat_worker(self, question):
        if hasattr(self, '_inline_chat_thread') and self._inline_chat_thread is not None:
            try:
                if self._inline_chat_thread.isRunning():
                    return
            except RuntimeError:
                self._inline_chat_thread = None

        cursor = self.textCursor()
        line_num = cursor.blockNumber() + 1

        doc = self.document()
        start_block = max(0, cursor.blockNumber() - 10)
        end_block = min(doc.blockCount() - 1, cursor.blockNumber() + 10)

        lines = []
        for i in range(start_block, end_block + 1):
            block = doc.findBlockByNumber(i)
            prefix = ">>>" if i == cursor.blockNumber() else "   "
            lines.append(f"{prefix} {block.text()}")
        context_snippet = "\n".join(lines)

        lang = self._get_language()
        intent_ctx = self._get_intent_context()

        prompt = f"""{intent_ctx}
The user is asking about {lang} code at line {line_num}.

Code context (>>> marks the current line):
{context_snippet}

User question: {question}

Answer concisely. If you include code, use a single fenced code block."""

        if not self.settings_manager:
            return

        if hasattr(self, '_inline_chat_thread') and self._inline_chat_thread is not None:
            try:
                if self._inline_chat_thread.isRunning():
                    if hasattr(self, '_inline_chat_worker') and self._inline_chat_worker:
                        self._inline_chat_worker.cancel()
                    self._inline_chat_thread.quit()
                    self._inline_chat_thread.wait(500)
            except RuntimeError:
                pass
            self._inline_chat_thread = None
            self._inline_chat_worker = None

        thread = QThread()
        worker = AIWorker(
            prompt=prompt,
            editor_text="",
            cursor_pos=0,
            is_chat=True,
            model=self.settings_manager.get_chat_model(),
            api_url=self.settings_manager.get_api_url(),
            api_key=self.settings_manager.get_api_key(),
            backend=self.settings_manager.get_backend(),
        )

        self._inline_chat_thread = thread
        self._inline_chat_worker = worker

        worker.moveToThread(thread)
        worker.chat_update.connect(self._inline_chat.append_response)
        worker.finished.connect(self._inline_chat.response_finished)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._on_inline_chat_finished)
        thread.started.connect(worker.run)
        thread.start()

    def _on_inline_chat_finished(self):
        self._inline_chat_thread = None
        self._inline_chat_worker = None

    def _insert_inline_chat_code(self, code):
        cursor = self.textCursor()
        cursor.insertText(code)
        self.setFocus()

    def _relay_to_chat(self, question, response):
        self.send_to_chat_requested.emit(
            f"**Inline question:** {question}\n\n**AI response:**\n{response}"
        )

    # ── Editing helpers ───────────────────────────────────────────────────

    def duplicate_line(self):
        cursor = self.textCursor()
        if cursor.hasSelection():
            start = cursor.selectionStart()
            end = cursor.selectionEnd()
            selected = cursor.selectedText().replace('\u2029', '\n')
            cursor.setPosition(end)
            cursor.insertText('\n' + selected)
            cursor.setPosition(end + 1)
            cursor.setPosition(end + 1 + len(selected), QTextCursor.MoveMode.KeepAnchor)
        else:
            cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
            cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
            line_text = cursor.selectedText()
            cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
            cursor.insertText('\n' + line_text)
            cursor.movePosition(QTextCursor.MoveOperation.Down)
        self.setTextCursor(cursor)

    def toggle_comment(self):
        cursor = self.textCursor()
        comment_char = self._get_comment_char()

        if cursor.hasSelection():
            start = cursor.selectionStart()
            end = cursor.selectionEnd()
            cursor.setPosition(start)
            cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
            block_start = cursor.position()
            cursor.setPosition(end)
            if cursor.atBlockStart() and end > start:
                cursor.movePosition(QTextCursor.MoveOperation.PreviousBlock)
            cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
            block_end = cursor.position()
            cursor.setPosition(block_start)
            cursor.setPosition(block_end, QTextCursor.MoveMode.KeepAnchor)
            selected = cursor.selectedText().replace('\u2029', '\n')
            lines = selected.split('\n')
        else:
            cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
            block_start = cursor.position()
            cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
            block_end = cursor.position()
            lines = [cursor.selectedText()]

        all_commented = all(l.lstrip().startswith(comment_char) for l in lines if l.strip())

        result = []
        for line in lines:
            if not line.strip():
                result.append(line)
                continue
            if all_commented:
                stripped = line.lstrip()
                indent = line[:len(line) - len(stripped)]
                if stripped.startswith(comment_char + ' '):
                    result.append(indent + stripped[len(comment_char) + 1:])
                else:
                    result.append(indent + stripped[len(comment_char):])
            else:
                stripped = line.lstrip()
                indent = line[:len(line) - len(stripped)]
                result.append(indent + comment_char + ' ' + stripped)

        new_text = '\n'.join(result)
        cursor.setPosition(block_start)
        cursor.setPosition(block_end, QTextCursor.MoveMode.KeepAnchor)
        cursor.beginEditBlock()
        cursor.insertText(new_text)
        cursor.endEditBlock()
        cursor.setPosition(block_start)
        cursor.setPosition(block_start + len(new_text), QTextCursor.MoveMode.KeepAnchor)
        self.setTextCursor(cursor)

    def _get_comment_char(self):
        if not self.file_path:
            return '#'
        ext = self.file_path.lower()
        if ext.endswith(('.py', '.sh', '.bash', '.yml', '.yaml', '.nix')):
            return '#'
        if ext.endswith(('.js', '.ts', '.cpp', '.c', '.java', '.go')):
            return '//'
        if ext.endswith('.lua'):
            return '--'
        return '#'

    def indent_selection(self):
        cursor = self.textCursor()
        if not cursor.hasSelection():
            cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
            cursor.insertText("    ")
            return
        start = cursor.selectionStart()
        end = cursor.selectionEnd()
        cursor.setPosition(start)
        cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        block_start = cursor.position()
        cursor.setPosition(end)
        if cursor.atBlockStart() and end > start:
            cursor.movePosition(QTextCursor.MoveOperation.PreviousBlock)
        cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
        block_end = cursor.position()
        cursor.setPosition(block_start)
        cursor.setPosition(block_end, QTextCursor.MoveMode.KeepAnchor)
        selected = cursor.selectedText().replace('\u2029', '\n')
        indented = '\n'.join("    " + line for line in selected.split('\n'))
        cursor.beginEditBlock()
        cursor.insertText(indented)
        cursor.endEditBlock()
        cursor.setPosition(block_start)
        cursor.setPosition(block_start + len(indented), QTextCursor.MoveMode.KeepAnchor)
        self.setTextCursor(cursor)

    def unindent_selection(self):
        cursor = self.textCursor()
        if not cursor.hasSelection():
            cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
            line = cursor.block().text()
            if line.startswith("    "):
                cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, 4)
                cursor.removeSelectedText()
            elif line.startswith("\t"):
                cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, 1)
                cursor.removeSelectedText()
            return
        start = cursor.selectionStart()
        end = cursor.selectionEnd()
        cursor.setPosition(start)
        cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        block_start = cursor.position()
        cursor.setPosition(end)
        if cursor.atBlockStart() and end > start:
            cursor.movePosition(QTextCursor.MoveOperation.PreviousBlock)
        cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
        block_end = cursor.position()
        cursor.setPosition(block_start)
        cursor.setPosition(block_end, QTextCursor.MoveMode.KeepAnchor)
        selected = cursor.selectedText().replace('\u2029', '\n')
        unindented = []
        for line in selected.split('\n'):
            if line.startswith("    "):
                unindented.append(line[4:])
            elif line.startswith("\t"):
                unindented.append(line[1:])
            else:
                unindented.append(line)
        result = '\n'.join(unindented)
        cursor.beginEditBlock()
        cursor.insertText(result)
        cursor.endEditBlock()
        cursor.setPosition(block_start)
        cursor.setPosition(block_start + len(result), QTextCursor.MoveMode.KeepAnchor)
        self.setTextCursor(cursor)
        
    def select_full_line(self, block_number: int):
        """Select the entire line at the given 0-indexed block number."""
        doc    = self.document()
        block  = doc.findBlockByNumber(block_number)
        if not block.isValid():
            return
        cursor = QTextCursor(block)
        cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        cursor.movePosition(
            QTextCursor.MoveOperation.EndOfBlock,
            QTextCursor.MoveMode.KeepAnchor,
        )
        self.setTextCursor(cursor)
        self.setFocus()

    # ── Context menu ──────────────────────────────────────────────────────

    def contextMenuEvent(self, event):
        menu = self.createStandardContextMenu(event.pos())
        active_cursor = self.textCursor()
        click_cursor = self.cursorForPosition(event.pos())
        clicked_line = click_cursor.blockNumber() + 1

        menu.addSeparator()
        indent_action = QAction("⇥ Indent  (Ctrl+])", self)
        indent_action.triggered.connect(self.indent_selection)
        menu.addAction(indent_action)

        unindent_action = QAction("⇤ Unindent  (Ctrl+[)", self)
        unindent_action.triggered.connect(self.unindent_selection)
        menu.addAction(unindent_action)

        menu.addSeparator()
        dup_action = QAction("⧉ Duplicate Line  (Ctrl+D)", self)
        dup_action.triggered.connect(self.duplicate_line)
        menu.addAction(dup_action)

        comment_action = QAction("# Toggle Comment  (Ctrl+/)", self)
        comment_action.triggered.connect(self.toggle_comment)
        menu.addAction(comment_action)

        jump_action = QAction("⤵ Go to Line  (Ctrl+G)", self)
        jump_action.triggered.connect(self._show_jump_bar)
        menu.addAction(jump_action)

        if active_cursor.hasSelection():
            menu.addSeparator()
            chat_action = QAction("💬 Send to Chat", self)
            selected_text = active_cursor.selectedText().replace('\u2029', '\n')
            chat_action.triggered.connect(lambda: self.send_to_chat_requested.emit(selected_text))
            menu.addAction(chat_action)

        if self.current_syntax_error and self.current_syntax_error['lineno'] == clicked_line:
            menu.addSeparator()
            fix_action = QAction(QIcon(), "💡 Explain & Fix Error with AI", self)
            fix_action.triggered.connect(self.trigger_ai_error_fix)
            font = fix_action.font()
            font.setBold(True)
            fix_action.setFont(font)
            menu.addAction(fix_action)

        menu.exec(event.globalPos())

    # ── setPlainText ──────────────────────────────────────────────────────

    def setPlainText(self, text):
        super().setPlainText(text)
        self.minimap.setPlainText(text)

        cursor = self.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)
        fmt = QTextBlockFormat()
        fmt.setLineHeight(150, 1)
        cursor.mergeBlockFormat(fmt)
        cursor.clearSelection()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        self.setTextCursor(cursor)

        m_cursor = self.minimap.textCursor()
        m_cursor.select(QTextCursor.SelectionType.Document)
        m_cursor.mergeBlockFormat(fmt)
        m_cursor.clearSelection()
        m_cursor.movePosition(QTextCursor.MoveOperation.Start)
        self.minimap.setTextCursor(m_cursor)

    # ── Highlighting & linting ────────────────────────────────────────────

    def highlight_current_line(self):
        self.current_line_selection = []
        if not self.isReadOnly():
            selection = QTextEdit.ExtraSelection()
            selection.format.setBackground(QColor(self._t['bg1']))
            selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
            selection.cursor = self.textCursor()
            selection.cursor.clearSelection()
            self.current_line_selection.append(selection)
        self.update_extra_selections()

    def update_extra_selections(self):
        self.setExtraSelections(
            self.current_line_selection +
            self.lint_selections +
            self.bracket_selections +
            self.lsp_selections +
            self.mc_selections
        )

    def toggle_blame(self):
        """Toggle git blame column."""
        if self._blame_visible:
            self._blame_visible = False
            self._blame_width   = 0
            self._blame_data    = {}
            self.update_line_number_area_width(0)
            self.line_number_area.update()
        else:
            self._fetch_blame()

    def _fetch_blame(self):
        """Run git blame on the current file and apply results on the GUI thread."""
        if not self.file_path or not os.path.exists(self.file_path):
            print(f"[blame] No file path or file does not exist: {self.file_path!r}")
            return

        import subprocess, threading

        # Capture self.file_path now — don't reference self from the thread
        file_path = self.file_path
        cwd       = os.path.dirname(file_path)

        def run():
            try:
                result = subprocess.run(
                    ['git', 'blame', '--porcelain', file_path],
                    cwd=cwd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=10,
                )
                print(f"[blame] git returned code {result.returncode}")
                if result.returncode != 0:
                    print(f"[blame] stderr: {result.stderr[:200]}")
                    return

                blame:   dict[int, str] = {}
                authors: dict[str, str] = {}
                current_hash = ''
                current_line = 0

                for raw_line in result.stdout.splitlines():
                    # Porcelain header: exactly 40 hex chars followed by space
                    # then original-line final-line [num-lines]
                    if (len(raw_line) > 40 and raw_line[40] == ' '
                            and all(c in '0123456789abcdef' for c in raw_line[:40])):
                        parts = raw_line.split()
                        if len(parts) >= 3:
                            try:
                                current_hash = parts[0][:8]
                                current_line = int(parts[2])
                            except (ValueError, IndexError):
                                pass
                    elif raw_line.startswith('author '):
                        author = raw_line[7:].strip()
                        short  = author.split()[0][:10] if author else '?'
                        authors[current_hash] = short
                    elif raw_line.startswith('\t'):
                        author_short = authors.get(current_hash, '?')
                        blame[current_line] = f"{current_hash} {author_short}"

                # Use invokeMethod for guaranteed GUI thread delivery
                from PyQt6.QtCore import QMetaObject, Qt as QtCore_Qt
                QMetaObject.invokeMethod(
                    self, "_apply_blame_slot",
                    QtCore_Qt.ConnectionType.QueuedConnection,
                )
                # Store data where the slot can pick it up
                self._blame_pending = blame

            except Exception as e:
                print(f"[blame] Exception: {e}")

        threading.Thread(target=run, daemon=True).start()

    from PyQt6.QtCore import pyqtSlot

    @pyqtSlot()
    def _apply_blame_slot(self):
        blame = getattr(self, '_blame_pending', {})
        self._apply_blame(blame)

    def _apply_blame(self, blame: dict):
        self._blame_data    = blame
        self._blame_visible = True
        sample = "a1b2c3d4 authorname"
        self._blame_width = self.fontMetrics().horizontalAdvance(sample) + 12
        self.update_line_number_area_width(0)
        self.line_number_area.update()

    # ── Bracket matching ──────────────────────────────────────────────────

    _OPEN  = {'{': '}', '(': ')', '[': ']'}
    _CLOSE = {'}': '{', ')': '(', ']': '['}

    def _highlight_matching_bracket(self):
        self.bracket_selections = []
        cursor = self.textCursor()
        doc    = self.document()
        pos    = cursor.position()

        # Use doc.characterAt() which works in document position space,
        # not string index space (they diverge due to block separators).
        bracket_pos = None
        bracket_ch  = None

        for check_pos in (pos - 1, pos):
            if check_pos < 0:
                continue
            ch = doc.characterAt(check_pos)
            if ch in self._OPEN or ch in self._CLOSE:
                bracket_pos = check_pos
                bracket_ch  = ch
                break

        if bracket_pos is None:
            self.update_extra_selections()
            return

        # Build the full text using document positions for matching.
        # We walk using doc.characterAt() to stay in document space.
        match_pos = self._find_match_doc(doc, bracket_pos, bracket_ch)

        color = QColor(self._t.get('accent', '#fabd2f'))
        bg    = QColor(self._t.get('bg2',    '#504945'))
        for p in (bracket_pos, match_pos):
            if p is None:
                continue
            sel = QTextEdit.ExtraSelection()
            sel.format.setForeground(color)
            sel.format.setFontWeight(700)
            sel.format.setBackground(bg)
            c = QTextCursor(doc)
            c.setPosition(p)
            c.setPosition(p + 1, QTextCursor.MoveMode.KeepAnchor)
            sel.cursor = c
            self.bracket_selections.append(sel)

        self.update_extra_selections()

    def _find_match_doc(self, doc, pos: int, ch: str):
        """Walk document character positions to find the matching bracket."""
        doc_len = doc.characterCount()

        if ch in self._OPEN:
            target = self._OPEN[ch]
            rng    = range(pos + 1, doc_len)
        else:
            target = self._CLOSE[ch]
            rng    = range(pos - 1, -1, -1)

        depth = 1
        for i in rng:
            c = doc.characterAt(i)
            if c == ch:
                depth += 1
            elif c == target:
                depth -= 1
                if depth == 0:
                    return i
        return None

    def _draw_error_squiggle(self, line_idx, col_offset, error_msg, end_offset=None):
        self.current_syntax_error = {'msg': error_msg, 'lineno': line_idx + 1, 'offset': col_offset}
        selection = QTextEdit.ExtraSelection()
        selection.format.setUnderlineStyle(QTextCharFormat.UnderlineStyle.WaveUnderline)
        selection.format.setUnderlineColor(QColor(self._t['error']))
        cursor = QTextCursor(self.document())
        cursor.setPosition(self.document().findBlockByNumber(line_idx).position())
        cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.MoveAnchor, col_offset)
        if end_offset is not None and end_offset > col_offset:
            cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, end_offset - col_offset)
        else:
            cursor.select(QTextCursor.SelectionType.WordUnderCursor)
        if not cursor.hasSelection():
            cursor.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.KeepAnchor, 1)
        selection.cursor = cursor
        self.lint_selections.append(selection)

    def run_linter(self):
        self.lint_selections = []
        self.current_syntax_error = None
        text = self.toPlainText()
        if not text.strip() or not self.file_path:
            self.update_extra_selections()
            return
        ext = self.file_path.lower()
        if ext.endswith('.py'):
            try:
                ast.parse(text)
            except SyntaxError as e:
                line_idx = (e.lineno - 1) if e.lineno is not None else 0
                col_offset = (e.offset - 1) if e.offset is not None else 0
                end_offset = (e.end_offset - 1) if hasattr(e, 'end_offset') and e.end_offset is not None else None
                self._draw_error_squiggle(line_idx, col_offset, e.msg, end_offset)
            except Exception:
                pass
        elif ext.endswith(('.yml', '.yaml')) and HAS_YAML:
            try:
                yaml.safe_load(text)
            except yaml.YAMLError as e:
                if hasattr(e, 'problem_mark') and e.problem_mark is not None:
                    self._draw_error_squiggle(e.problem_mark.line, e.problem_mark.column, str(e))
            except Exception:
                pass
        elif ext.endswith(('.sh', '.bash')):
            try:
                process = subprocess.Popen(
                    ['shellcheck', '-f', 'json', '-'],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, text=True
                )
                stdout, _ = process.communicate(input=text)
                if stdout:
                    for err in json.loads(stdout):
                        line_idx = err.get('line', 1) - 1
                        col_offset = err.get('column', 1) - 1
                        end_offset = err.get('endColumn', col_offset + 1) - 1
                        self._draw_error_squiggle(line_idx, col_offset,
                                                  f"SC{err.get('code')}: {err.get('message')}", end_offset)
            except FileNotFoundError:
                print("LINTER ERROR: shellcheck binary not found in PATH!")
            except Exception as e:
                print(f"LINTER ERROR: {e}")
        self.update_extra_selections()

    # ── AI completion ─────────────────────────────────────────────────────

    def handle_text_changed_for_ai(self):
        self.clear_ghost_text()

        if self._is_markdown_file():
            self.ai_suggest_timer.stop()
            return

        cursor = self.textCursor()
        if cursor.hasSelection():
            self.ai_suggest_timer.stop()
            return

        pos = cursor.position()
        if pos == 0:
            self.ai_suggest_timer.stop()
            return

        current_line = cursor.block().text()
        prev_block = cursor.block().previous()
        prev_line = prev_block.text().rstrip() if prev_block.isValid() else ""

        just_entered_block = (
            current_line.strip() == ""
            and prev_line.endswith(":")
        )

        inside_indented_empty = (
            current_line == ""
            and prev_line.startswith((" ", "\t"))
        )

        after_generatable_comment = (
            current_line.strip() == ""
            and prev_line.strip().startswith("#")
            and self._should_generate_function(prev_line.strip())
        )

        if not (just_entered_block or inside_indented_empty or after_generatable_comment):
            self.ai_suggest_timer.stop()
            return

        self.ai_suggest_timer.start(300)

    def request_completion_hotkey(self):
        if self._is_markdown_file():
            return

        self.clear_ghost_text()
        try:
            if hasattr(self, 'ai_thread') and self.ai_thread is not None:
                if self.ai_thread.isRunning():
                    if hasattr(self, 'worker') and self.worker:
                        self.worker.cancel()
        except RuntimeError:
            self.ai_thread = None
        self.ai_suggest_timer.stop()
        self.trigger_inline_completion()

    def trigger_inline_completion(self):
        if self._is_markdown_file():
            return

        try:
            if hasattr(self, 'ai_thread') and self.ai_thread is not None:
                if self.ai_thread.isRunning():
                    return
        except RuntimeError:
            self.ai_thread = None
        self.start_worker(prompt="", generate_function=False, replace_selection=False)

    def trigger_ai_error_fix(self):
        if self.current_syntax_error:
            self.error_help_requested.emit(
                self.current_syntax_error['msg'],
                self.toPlainText(),
                self.current_syntax_error['lineno']
            )

    def show_snippet_menu(self):
        from ui.snippet_palette import SnippetPalette
        palette = SnippetPalette(self)
        palette.move(self.mapToGlobal(self.rect().center()) - palette.rect().center())
        palette.snippet_selected.connect(self._insert_snippet_code)
        palette.exec()

    def _insert_snippet_code(self, code):
        cursor = self.textCursor()
        current_line = cursor.block().text()
        indent_match = re.match(r'^(\s*)', current_line)
        base_indent = indent_match.group(1) if indent_match else ""
        lines = code.split('\n')
        indented = lines[0]
        for line in lines[1:]:
            indented += '\n' + base_indent + line
        cursor.insertText(indented)
        self.clear_ghost_text()
        self.setFocus()

    def set_original_state(self, text):
        self.original_text = text
        self.line_changes.clear()
        self.line_number_area.update()

    def is_dirty(self):
        return self.toPlainText() != self.original_text

    def calculate_diff(self):
        current_text = self.toPlainText()
        if self.minimap.toPlainText() != current_text:
            scroll = self.minimap.verticalScrollBar().value()
            self.minimap.setPlainText(current_text)
            m_cursor = self.minimap.textCursor()
            m_cursor.select(QTextCursor.SelectionType.Document)
            fmt = QTextBlockFormat()
            fmt.setLineHeight(150, 1)
            m_cursor.mergeBlockFormat(fmt)
            self.minimap.verticalScrollBar().setValue(scroll)
        current_lines = current_text.split('\n')
        original_lines = self.original_text.split('\n')
        matcher = difflib.SequenceMatcher(None, original_lines, current_lines)
        new_changes = {}
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'replace':
                for j in range(j1, j2):
                    new_changes[j] = 'modified'
            elif tag == 'insert':
                for j in range(j1, j2):
                    new_changes[j] = 'added'
        self.line_changes = new_changes
        self.line_number_area.update()

    def line_number_area_width(self):
        digits = 1
        max_value = max(1, self.blockCount())
        while max_value >= 10:
            max_value /= 10
            digits += 1
        base = 14 + self.fontMetrics().horizontalAdvance('9') * digits
        return base + self._blame_width

    def update_line_number_area_width(self, _):
        self.setViewportMargins(self.line_number_area_width(), 0, self.minimap_width, 0)

    def update_line_number_area(self, rect, dy):
        if dy:
            self.line_number_area.scroll(0, dy)
        else:
            self.line_number_area.update(0, rect.y(), self.line_number_area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self.update_line_number_area_width(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.line_number_area.setGeometry(QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height()))
        self.minimap.setGeometry(QRect(cr.right() - self.minimap_width, cr.top(), self.minimap_width, cr.height()))
        if hasattr(self, '_jump_bar'):
            self._position_jump_bar()
        if hasattr(self, '_inline_chat') and self._inline_chat.isVisible():
            self._position_inline_chat()

    def line_number_area_paint_event(self, event):
        painter = QPainter(self.line_number_area)
        painter.fillRect(event.rect(), QColor(self._t['bg0_hard']))
        painter.setPen(QColor(self._t['border']))
        painter.drawLine(self.line_number_area.width() - 1, event.rect().top(),
                         self.line_number_area.width() - 1, event.rect().bottom())

        # Blame column separator
        if self._blame_visible and self._blame_width > 0:
            painter.setPen(QColor(self._t['border']))
            painter.drawLine(self._blame_width, event.rect().top(),
                             self._blame_width, event.rect().bottom())

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top    = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())
        fm_h   = self.fontMetrics().height()

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                # ── Blame annotation ──────────────────────────────────────
                if self._blame_visible and self._blame_width > 0:
                    annotation = self._blame_data.get(block_number + 1, "")
                    if annotation:
                        painter.setPen(QColor(self._t['fg4']))
                        blame_font = painter.font()
                        blame_font.setPointSize(blame_font.pointSize() - 1)
                        painter.setFont(blame_font)
                        painter.drawText(
                            2, top, self._blame_width - 6, fm_h,
                            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                            annotation
                        )
                        # Restore font
                        blame_font.setPointSize(blame_font.pointSize() + 1)
                        painter.setFont(blame_font)

                # ── Line number ───────────────────────────────────────────
                painter.setPen(QColor(self._t['fg4']))
                painter.drawText(
                    self._blame_width, top,
                    self.line_number_area.width() - self._blame_width - 8, fm_h,
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                    str(block_number + 1)
                )

                # ── Diff indicator ────────────────────────────────────────
                status = self.line_changes.get(block_number)
                if status:
                    color = QColor(self._t['added_line']) if status == 'added' \
                            else QColor(self._t['modified_line'])
                    painter.fillRect(
                        self.line_number_area.width() - 4, top, 4, fm_h, color
                    )

            block = block.next()
            top    = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            block_number += 1

    def set_ghost_text(self, text):
        self.ghost_text = text
        self.viewport().update()

    def clear_ghost_text(self):
        self.ghost_text = ""
        self.viewport().update()

    def accept_full_completion(self):
        if not self.ghost_text:
            return
        accepted_text = self.ghost_text
        context_before = self.toPlainText()[:self.textCursor().position()]
        self.textCursor().insertText(accepted_text)
        self.completion_accepted.emit(accepted_text, context_before)
        self.clear_ghost_text()

    def accept_next_word(self):
        if not self.ghost_text:
            return
        parts         = self.ghost_text.lstrip().split(" ", 1)
        word          = parts[0]
        remainder     = parts[1] if len(parts) > 1 else ""
        context_before = self.toPlainText()[:self.textCursor().position()]
        self.textCursor().insertText(word + " ")
        self.completion_accepted.emit(word, context_before)
        self.ghost_text = remainder
        self.viewport().update()

    def get_ast_context(self):
        text = self.toPlainText()
        try:
            tree = ast.parse(text)
        except Exception:
            return text[-1000:]
        functions, classes = [], []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                functions.append(node.name)
            elif isinstance(node, ast.ClassDef):
                classes.append(node.name)
        return f"Functions: {functions}\nClasses: {classes}\n\n" + text[-1000:]

    def handle_comment_generate(self, comment):
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
        cursor.insertBlock()
        cursor.insertBlock()
        self.function_cursor = self.textCursor()
        self.function_active = True
        context = self.get_ast_context()
        lang = self._get_language()
        intent_ctx = self._get_intent_context()
        prompt = (
            f"{intent_ctx}\n"
            f"Generate a {lang} function based on this comment:\n\n"
            f"{comment}\n\n"
            f"Context (existing functions and classes):\n{context}\n\n"
            f"Return ONLY the {lang} code. No explanation, no markdown, no backticks."
        )
        self.start_worker(prompt, generate_function=True)

    def replace_selection_with_ai(self):
        cursor = self.textCursor()
        if not cursor.hasSelection():
            return
        self._replacement_original = cursor.selectedText().replace('\u2029', '\n')
        self.replacement_cursor = cursor
        lang = self._get_language()
        intent_ctx = self._get_intent_context()
        prompt = (
            f"{intent_ctx}"
            f"Rewrite or improve this {lang} code. "
            f"Return ONLY {lang} code with no explanation, no markdown, no backticks:\n\n"
            f"{self._replacement_original}"
        )
        self.start_worker(prompt, replace_selection=True)

    def _create_ai_worker(self, prompt, generate_function=False, replace_selection=False):
        try:
            if hasattr(self, 'ai_thread') and self.ai_thread is not None:
                if self.ai_thread.isRunning():
                    return None, None
        except RuntimeError:
            self.ai_thread = None

        self.ai_thread = QThread()
        self.function_output = ""

        model = ""
        api_url = ""
        api_key = ""
        backend = "llama"

        if self.settings_manager:
            model = self.settings_manager.get_inline_model()
            api_url = self.settings_manager.get_api_url()
            api_key = self.settings_manager.get_api_key()
            backend = self.settings_manager.get_backend()

        if (not generate_function and not replace_selection
                and not prompt and self.intent_tracker):
            prompt = self._get_intent_context()

        worker = AIWorker(
            prompt=prompt,
            editor_text=self.toPlainText(),
            cursor_pos=self.textCursor().position(),
            generate_function=generate_function,
            is_edit=replace_selection,
            model=model,
            api_url=api_url,
            api_key=api_key,
            backend=backend,
        )

        worker.moveToThread(self.ai_thread)
        self.ai_thread.started.connect(worker.run)

        if not generate_function and not replace_selection:
            worker.update_ghost.connect(self.set_ghost_text)

        worker.function_ready.connect(self.handle_function_output)
        worker.finished.connect(self.ai_thread.quit)
        worker.finished.connect(worker.deleteLater)
        self.ai_thread.finished.connect(self.ai_thread.deleteLater)
        worker.finished.connect(self.finish_function_stream)
        worker.finished.connect(self.ai_finished.emit)

        return worker, self.ai_thread

    def start_worker(self, prompt, generate_function=False, replace_selection=False):
        self.ai_started.emit()
        worker, thread = self._create_ai_worker(prompt, generate_function, replace_selection)
        if worker is None:
            return
        self.worker = worker
        thread.start()
        self.ai_thread.start()

    def handle_function_output(self, text):
        if self.function_active and self.function_cursor:
            self.function_cursor.insertText(text)
        else:
            self.function_output += text

    def finish_function_stream(self):
        if hasattr(self, "replacement_cursor") and self.function_output:
            self._show_diff_dialog()
        self.function_active = False
        self.function_cursor = None
        self.function_output = ""

    def _show_diff_dialog(self):
        from ui.diff_apply_dialog import DiffApplyDialog
        original = getattr(self, '_replacement_original', '')
        proposed = self.function_output.strip()
        dialog = DiffApplyDialog(original, proposed, parent=self.window())
        if dialog.exec() and dialog.accepted_code is not None:
            self.replacement_cursor.removeSelectedText()
            self.replacement_cursor.insertText(dialog.accepted_code)

    def apply_replacement(self):
        cursor = self.replacement_cursor
        cursor.removeSelectedText()
        cursor.insertText(self.function_output)

    # ── Color picker ──────────────────────────────────────────────────────

    def _setup_color_swatch(self):
        """Small floating swatch that appears near hex colors."""
        self._swatch = QLabel(self.viewport())
        self._swatch.setFixedSize(56, 24)
        self._swatch.hide()
        self._current_color_range = None

    def _get_hex_color_at_cursor(self):
        """
        Checks if the cursor is on or adjacent to a hex color.
        Returns (hex_string, start, end) or None.
        """
        cursor = self.textCursor()
        block = cursor.block()
        text = block.text()
        pos_in_block = cursor.positionInBlock()

        for match in re.finditer(
            r'#([0-9A-Fa-f]{8}|[0-9A-Fa-f]{6}|[0-9A-Fa-f]{3})\b', text
        ):
            start = match.start()
            end = match.end()
            if start - 1 <= pos_in_block <= end + 1:
                return match.group(0), block.position() + start, block.position() + end
        return None

    def _update_color_swatch(self):
        """Show or hide the swatch based on cursor position."""
        result = self._get_hex_color_at_cursor()
        if not result:
            self._swatch.hide()
            self._current_color_range = None
            return

        hex_color, start, end = result
        self._current_color_range = (start, end)

        try:
            color = QColor(hex_color)
            if not color.isValid():
                self._swatch.hide()
                return
        except Exception:
            self._swatch.hide()
            return

        cursor = self.textCursor()
        rect = self.cursorRect(cursor)

        brightness = (
            color.red() * 299 +
            color.green() * 587 +
            color.blue() * 114
        ) / 1000
        text_color = "#000000" if brightness > 128 else "#FFFFFF"

        self._swatch.setStyleSheet(build_color_swatch_stylesheet(hex_color, text_color))
        self._swatch.setText(hex_color.upper())
        self._swatch.adjustSize()
        self._swatch.setFixedHeight(20)

        swatch_x = max(0, rect.left() - 4)
        swatch_y = max(0, rect.top() - 26)

        if swatch_x + self._swatch.width() > self.viewport().width():
            swatch_x = self.viewport().width() - self._swatch.width() - 4

        self._swatch.move(swatch_x, swatch_y)
        self._swatch.show()
        self._swatch.raise_()

    def _on_color_swatch_clicked(self, hex_color: str):
        """Open a color dialog; replace the hex value in the editor on accept."""
        from PyQt6.QtWidgets import QColorDialog
        current = QColor(hex_color)
        new_color = QColorDialog.getColor(
            current, self,
            "Pick a Color",
            QColorDialog.ColorDialogOption.ShowAlphaChannel
        )
        if not new_color.isValid():
            return

        if new_color.alpha() < 255 or len(hex_color) == 9:
            new_hex = new_color.name(QColor.NameFormat.HexArgb).upper()
        else:
            new_hex = new_color.name().upper()

        if self._current_color_range:
            start, end = self._current_color_range
            cursor = self.textCursor()
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
            cursor.insertText(new_hex)
            self._update_color_swatch()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        if hasattr(self, '_swatch'):
            self._swatch.hide()

    # ── Key handling ──────────────────────────────────────────────────────

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt, Qt.Key.Key_Meta):
            super().keyPressEvent(event)
            return
            
        key  = event.key()
        mods = event.modifiers()            
    
        # ── Multi-cursor triggers ─────────────────────────────
        # Ctrl+D — add next occurrence (or remove last if no new found)
        if (key == Qt.Key.Key_D
                and mods == Qt.KeyboardModifier.ControlModifier):
            prev_count = len(self.multi_cursor._cursors)
            self.multi_cursor.add_next_occurrence()
            if len(self.multi_cursor._cursors) == prev_count and prev_count > 0:
                # No new cursor added — remove last (toggle behaviour)
                self.multi_cursor.remove_last_occurrence()
            return
    
        # Ctrl+Shift+L — all occurrences
        if (key == Qt.Key.Key_L
                and mods == (Qt.KeyboardModifier.ControlModifier
                             | Qt.KeyboardModifier.ShiftModifier)):
            self.multi_cursor.add_all_occurrences()
            return
    
        # Ctrl+Alt+Up — cursor above
        if (key == Qt.Key.Key_Up
                and mods == (Qt.KeyboardModifier.ControlModifier
                             | Qt.KeyboardModifier.AltModifier)):
            self.multi_cursor.add_cursor_above()
            return
    
        # Ctrl+Alt+Down — cursor below
        if (key == Qt.Key.Key_Down
                and mods == (Qt.KeyboardModifier.ControlModifier
                             | Qt.KeyboardModifier.AltModifier)):
            self.multi_cursor.add_cursor_below()
            return
    
        # ── Multi-cursor active: route keypresses ─────────────
        if self.multi_cursor.active:
            if self.multi_cursor.handle_key(event):
                # _apply handled ALL cursors including primary — do NOT call super()
                return
            # Unhandled keys (Ctrl+S, Ctrl+Z etc.) — pass through normally
            super().keyPressEvent(event)
            return
            

        if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Up, Qt.Key.Key_Down):
            self.ai_suggest_timer.stop()
            self.clear_ghost_text()
            super().keyPressEvent(event)
            return

        if event.key() == Qt.Key.Key_Right:
            if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
                if self.ghost_text:
                    self.accept_next_word()
                    return
                super().keyPressEvent(event)
                return
            else:
                self.ai_suggest_timer.stop()
                self.clear_ghost_text()
                super().keyPressEvent(event)
                return

        pairs = {'(': ')', '[': ']', '{': '}', '"': '"', "'": "'"}
        char = event.text()
        if char in pairs:
            super().keyPressEvent(event)
            cursor = self.textCursor()
            cursor.insertText(pairs[char])
            cursor.movePosition(QTextCursor.MoveOperation.Left)
            self.setTextCursor(cursor)
            self.clear_ghost_text()
            return

        if event.key() == Qt.Key.Key_Space and event.modifiers() == (
                Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier):
            self.show_snippet_menu()
            return

        if event.key() == Qt.Key.Key_Tab:
            if self.ghost_text:
                self.accept_full_completion()
                return

        if event.key() == Qt.Key.Key_E and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            self.replace_selection_with_ai()
            return

        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            cursor = self.textCursor()
            cursor.select(QTextCursor.SelectionType.LineUnderCursor)
            previous_line_raw = cursor.selectedText()
            previous_line_stripped = previous_line_raw.strip()
            super().keyPressEvent(event)
            whitespace_match = re.match(r"^\s*", previous_line_raw)
            indent = whitespace_match.group(0) if whitespace_match else ""
            if previous_line_stripped.endswith(":"):
                indent += "    "
            if indent:
                self.textCursor().insertText(indent)
            if self._should_generate_function(previous_line_stripped):
                self.handle_comment_generate(previous_line_stripped)
            self.clear_ghost_text()
            return

        if event.key() == Qt.Key.Key_BracketRight and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            self.indent_selection()
            return

        if event.key() == Qt.Key.Key_BracketLeft and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            self.unindent_selection()
            return

        if event.key() == Qt.Key.Key_G and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            self._show_jump_bar()
            return
            
        if (event.key() == Qt.Key.Key_D and event.modifiers() == (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)):
            self.duplicate_line()
            return

        if event.key() == Qt.Key.Key_Slash and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            self.toggle_comment()
            return

        if event.key() == Qt.Key.Key_I and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            self.show_inline_chat()
            return

        super().keyPressEvent(event)
        self.clear_ghost_text()

    # ── Wheel & paint ─────────────────────────────────────────────────────

    def wheelEvent(self, event):
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta > 0:
                self.zoomIn(1)
            elif delta < 0:
                self.zoomOut(1)
            self.update_line_number_area_width(0)
            self.minimap.viewport().update()
            return
        super().wheelEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self.viewport())
        if not painter.isActive():
            return
        fm = QFontMetrics(self.font())
        indent_width = fm.horizontalAdvance(' ') * 4
        offset_x = self.contentOffset().x() + self.document().documentMargin()
        painter.setPen(QColor(self._t['border']))
        block = self.firstVisibleBlock()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())
        previous_indent = 0
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                text = block.text()
                if text.strip():
                    indent_spaces = len(text) - len(text.lstrip(' '))
                    previous_indent = indent_spaces
                else:
                    indent_spaces = previous_indent
                for i in range(1, indent_spaces // 4 + 1):
                    painter.drawLine(int(offset_x + i * indent_width), top,
                                     int(offset_x + i * indent_width), bottom)
            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())

        if self.ghost_text:
            painter.setPen(QColor(self._t['ghost_text']))
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
            cursor = self.textCursor()
            rect = self.cursorRect(cursor)
            x = rect.left()
            y = rect.top() + fm.ascent()
            line_spacing = round(self.blockBoundingRect(self.textCursor().block()).height())
            if line_spacing == 0:
                line_spacing = fm.height() * 1.5
            for i, line in enumerate(self.ghost_text.split("\n")):
                painter.drawText(x, int(y + i * line_spacing), line)