from PyQt6.QtWidgets import QPlainTextEdit, QWidget, QTextEdit, QMenu
from PyQt6.QtGui import QPainter, QColor, QFontMetrics, QTextCursor, QFont, QTextFormat, QAction, QTextCharFormat, QTextBlockFormat, QTextOption, QIcon
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QRect, QSize, QTimer
import re
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
        
        self.setStyleSheet("""
            QPlainTextEdit {
                background-color: #1E1E1E; 
                color: #888888; 
                border-left: 1px solid #333333; 
                border-right: none;
                border-top: none;
                border-bottom: none;
            }
        """)

        # font size to 4 so it's readable but out of the way
        font = QFont("Hack", 4) 
        font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        self.setFont(font)

        # Sync the scrolling
        self.editor.verticalScrollBar().valueChanged.connect(self.sync_scroll)

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
        
        editor_cursor = QTextCursor(self.editor.document().findBlockByNumber(block_number))
        self.editor.setTextCursor(editor_cursor)
        self.editor.centerCursor()

    def wheelEvent(self, event):
        # Forwards all minimap scrolls to the main editor, preventing accidental minimap zooming
        self.editor.wheelEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        
        painter = QPainter(self.viewport())
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 255, 255, 12))

        fm_editor = QFontMetrics(self.editor.font())
        visible_lines_editor = self.editor.viewport().height() / (fm_editor.height() * 1.5) 

        fm_minimap = QFontMetrics(self.font())
        top_block = self.editor.firstVisibleBlock()
        
        minimap_block = self.document().findBlockByNumber(top_block.blockNumber())
        if minimap_block.isValid():
            geom = self.blockBoundingGeometry(minimap_block).translated(self.contentOffset())
            
            rect_y = geom.top()
            rect_height = visible_lines_editor * (fm_minimap.height() * 1.5) 
            
            painter.drawRect(0, int(rect_y), self.width(), int(rect_height))


# ==========================================
# Main Ghost Editor
# ==========================================
class GhostEditor(QPlainTextEdit):
    ai_started = pyqtSignal()
    ai_finished = pyqtSignal()
    error_help_requested = pyqtSignal(str, str, int) 
    send_to_chat_requested = pyqtSignal(str)
    
    def __init__(self, settings_manager=None):
        super().__init__()
        self.settings_manager = settings_manager
        # Comprehensive Modern UI Stylesheet
        self.setStyleSheet("""
            QPlainTextEdit {
                background-color: #1E1E1E;
                color: #D4D4D4; /* Softer, highly readable white/grey */
                border: none;
                selection-background-color: #264F78; /* VS Code Blue */
                selection-color: #FFFFFF;
            }
            
            /* Modern Thin Vertical Scrollbar */
            QScrollBar:vertical {
                border: none;
                background: #1E1E1E;
                width: 14px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: #424242;
                min-height: 30px;
                border-radius: 7px;
                margin: 2px 3px 2px 3px; /* Pushes the handle in so it floats */
            }
            QScrollBar::handle:vertical:hover {
                background: #4F4F4F;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px; /* Hides the ugly up/down arrows */
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: none;
            }
            
            /* Modern Thin Horizontal Scrollbar */
            QScrollBar:horizontal {
                border: none;
                background: #1E1E1E;
                height: 14px;
                margin: 0px;
            }
            QScrollBar::handle:horizontal {
                background: #424242;
                min-width: 30px;
                border-radius: 7px;
                margin: 3px 2px 3px 2px;
            }
            QScrollBar::handle:horizontal:hover {
                background: #4F4F4F;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                width: 0px;
            }
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
                background: none;
            }
        """)

        self.file_path = None
        self.ghost_text = ""
        self.snippet_manager = SnippetManager() 
        self.setWordWrapMode(QTextOption.WrapMode.NoWrap)

        self.function_cursor = None
        self.function_active = False
        self.function_output = ""

        # Main editor starting font
        font = QFont("Hack")
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
        
        # ==========================================
        # AI Inline Completion Timer
        # ==========================================
        self.ai_suggest_timer = QTimer(self)
        self.ai_suggest_timer.setSingleShot(True)
        self.ai_suggest_timer.timeout.connect(self.trigger_inline_completion)
        self.textChanged.connect(self.handle_text_changed_for_ai)        
        
        self.current_line_selection = []
        self.lint_selections = []
        self.current_syntax_error = None

        self.line_number_area = LineNumberArea(self)
        
        self.minimap_width = 100
        self.minimap = MinimapArea(self)
        
        self.blockCountChanged.connect(self.update_line_number_area_width)
        self.updateRequest.connect(self.update_line_number_area)
        self.update_line_number_area_width(0)
        self.setTabStopDistance(4 * self.fontMetrics().horizontalAdvance(' '))
        
        self.cursorPositionChanged.connect(self.highlight_current_line)
        self.highlight_current_line() 

    def setPlainText(self, text):
        super().setPlainText(text)
        
        # [NEW] Explicitly set the minimap text since they are now decoupled
        self.minimap.setPlainText(text)
        
        # Apply 150% line height to main editor
        cursor = self.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)
        fmt = QTextBlockFormat()
        fmt.setLineHeight(150, 1) 
        cursor.mergeBlockFormat(fmt)
        cursor.clearSelection()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        self.setTextCursor(cursor)

        # Apply 150% line height to the minimap so the lines match up perfectly
        m_cursor = self.minimap.textCursor()
        m_cursor.select(QTextCursor.SelectionType.Document)
        m_cursor.mergeBlockFormat(fmt)
        m_cursor.clearSelection()
        m_cursor.movePosition(QTextCursor.MoveOperation.Start)
        self.minimap.setTextCursor(m_cursor)

    def highlight_current_line(self):
        self.current_line_selection = []
        if not self.isReadOnly():
            selection = QTextEdit.ExtraSelection()
            line_color = QColor("#2A2D2E")
            selection.format.setBackground(line_color)
            selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)

            selection.cursor = self.textCursor()
            selection.cursor.clearSelection()
            self.current_line_selection.append(selection)

        self.update_extra_selections()

    def insertFromMimeData(self, source):
        """Intercept all paste operations and re-indent to match cursor position."""
        if not source.hasText():
            super().insertFromMimeData(source)
            return

        text = source.text().replace('\r\n', '\n').replace('\r', '\n')
        lines = text.split('\n')

        if len(lines) <= 1:
            # Single line paste — just insert normally
            super().insertFromMimeData(source)
            return

        # Determine the indentation of the line the cursor is currently on
        cursor = self.textCursor()
        current_block_text = cursor.block().text()
        indent_match = re.match(r'^(\s*)', current_block_text)
        target_indent = indent_match.group(1) if indent_match else ""

        # Determine the indentation of the first pasted line
        first_line_match = re.match(r'^(\s*)', lines[0])
        source_indent = first_line_match.group(1) if first_line_match else ""
        source_indent_len = len(source_indent)

        # Re-indent every line relative to the first pasted line
        adjusted_lines = []
        for i, line in enumerate(lines):
            if i == 0:
                # First line inherits whatever is already on the cursor line
                adjusted_lines.append(line.lstrip())
            else:
                if line.strip() == "":
                    # Preserve blank lines as-is
                    adjusted_lines.append("")
                else:
                    # Strip the source indentation, then apply target indentation
                    stripped = line[source_indent_len:] if line.startswith(source_indent) else line.lstrip()
                    adjusted_lines.append(target_indent + stripped)

        cursor.insertText('\n'.join(adjusted_lines))

    def reindent_selection(self):
        """Re-indents the selected block of code to be consistent within itself."""
        cursor = self.textCursor()
        if not cursor.hasSelection():
            # If no selection, select the whole document
            cursor.select(QTextCursor.SelectionType.Document)

        selected_text = cursor.selectedText().replace('\u2029', '\n')
        lines = selected_text.split('\n')

        if not lines:
            return

        # Find the minimum indentation level across all non-empty lines
        min_indent = float('inf')
        for line in lines:
            if line.strip():
                indent = len(line) - len(line.lstrip(' '))
                min_indent = min(min_indent, indent)

        if min_indent == float('inf'):
            min_indent = 0

        # Determine target indent from the first line's block in the document
        block = self.document().findBlock(cursor.selectionStart())
        block_text = block.text()
        target_match = re.match(r'^(\s*)', block_text)
        target_indent = target_match.group(1) if target_match else ""

        # Strip the common indent and re-apply the target indent
        reindented = []
        for i, line in enumerate(lines):
            if line.strip() == "":
                reindented.append("")
            elif i == 0:
                reindented.append(line.lstrip())
            else:
                stripped = line[min_indent:]
                reindented.append(target_indent + stripped)

        cursor.insertText('\n'.join(reindented))

    def update_extra_selections(self):
        self.setExtraSelections(self.current_line_selection + self.lint_selections)

    def _draw_error_squiggle(self, line_idx, col_offset, error_msg, end_offset=None):
        self.current_syntax_error = {
            'msg': error_msg,
            'lineno': line_idx + 1,
            'offset': col_offset
        }
        
        selection = QTextEdit.ExtraSelection()
        selection.format.setUnderlineStyle(QTextCharFormat.UnderlineStyle.WaveUnderline)
        selection.format.setUnderlineColor(QColor("#F44336")) 
        
        cursor = QTextCursor(self.document())
        cursor.setPosition(self.document().findBlockByNumber(line_idx).position())
        cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.MoveAnchor, col_offset)
        
        if end_offset is not None and end_offset > col_offset:
            length = end_offset - col_offset
            cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, length)
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
        
        # ==========================================
        # PYTHON LINTING
        # ==========================================
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

        # ==========================================
        # YAML / ANSIBLE LINTING
        # ==========================================
        elif ext.endswith(('.yml', '.yaml')) and HAS_YAML:
            try:
                yaml.safe_load(text)
            except yaml.YAMLError as e:
                if hasattr(e, 'problem_mark') and e.problem_mark is not None:
                    line_idx = e.problem_mark.line
                    col_offset = e.problem_mark.column
                    self._draw_error_squiggle(line_idx, col_offset, str(e))
            except Exception:
                pass

        # ==========================================
        # BASH LINTING via SHELLCHECK
        # ==========================================
        elif ext.endswith(('.sh', '.bash')):
            try:
                # Pass text to shellcheck via stdin, ask for JSON output
                process = subprocess.Popen(
                    ['shellcheck', '-f', 'json', '-'],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                stdout, _ = process.communicate(input=text)
                
                if stdout:
                    errors = json.loads(stdout)
                    for err in errors:
                        # Shellcheck uses 1-based indexing
                        line_idx = err.get('line', 1) - 1
                        col_offset = err.get('column', 1) - 1
                        end_offset = err.get('endColumn', col_offset + 1) - 1
                        
                        msg = f"SC{err.get('code')}: {err.get('message')}"
                        self._draw_error_squiggle(line_idx, col_offset, msg, end_offset)
            except FileNotFoundError:
                # [NEW] Print to the terminal so we can see it!
                print("LINTER ERROR: shellcheck binary not found in PATH!")
            except Exception as e:
                # [NEW] Print any JSON parsing or Subprocess errors
                print(f"LINTER ERROR: {e}")

    def contextMenuEvent(self, event):
        menu = self.createStandardContextMenu(event.pos())
        active_cursor = self.textCursor()
        click_cursor = self.cursorForPosition(event.pos())
        clicked_line = click_cursor.blockNumber() + 1

        # --- REINDENT ACTION (always available) ---
        menu.addSeparator()
        reindent_action = QAction(
            "⇥ Fix Indentation" if active_cursor.hasSelection() else "⇥ Fix Indentation (whole file)",
            self
        )
        reindent_action.triggered.connect(self.reindent_selection)
        menu.addAction(reindent_action)

        # --- SELECTION CHECK ---
        if active_cursor.hasSelection():
            menu.addSeparator()
            chat_action = QAction("💬 Send to Chat", self)
            selected_text = active_cursor.selectedText().replace('\u2029', '\n')
            chat_action.triggered.connect(
                lambda: self.send_to_chat_requested.emit(selected_text)
            )
            menu.addAction(chat_action)

        # --- SYNTAX ERROR CHECK ---
        if self.current_syntax_error and self.current_syntax_error['lineno'] == clicked_line:
            menu.addSeparator()
            fix_action = QAction(QIcon(), "💡 Explain & Fix Error with AI", self)
            fix_action.triggered.connect(self.trigger_ai_error_fix)
            font = fix_action.font()
            font.setBold(True)
            fix_action.setFont(font)
            menu.addAction(fix_action)

        menu.exec(event.globalPos())
        
    def handle_text_changed_for_ai(self):
        self.clear_ghost_text()

        cursor = self.textCursor()
        if cursor.hasSelection():
            self.ai_suggest_timer.stop()
            return

        text = self.toPlainText()
        pos = cursor.position()

        if pos == 0:
            self.ai_suggest_timer.stop()
            return

        # --- Strong signal checks only ---

        # 1. Cursor is on a brand-new blank line after a colon (entering a block body)
        current_line = cursor.block().text()
        prev_block = cursor.block().previous()
        prev_line = prev_block.text().rstrip() if prev_block.isValid() else ""

        just_entered_block = (
            current_line.strip() == ""
            and prev_line.endswith(":")
        )

        # 2. Inside an existing function/class body but the line is completely empty
        #    (user pressed Enter to start a new statement inside a block)
        inside_indented_empty = (
            current_line == ""
            and prev_line.startswith((" ", "\t"))
        )

        # 3. Cursor is directly after a comment line that was just committed
        #    (user hit Enter after writing a # comment, expecting a function below it)
        prev_is_comment = prev_line.strip().startswith("#")
        after_comment = current_line.strip() == "" and prev_is_comment

        if not (just_entered_block or inside_indented_empty or after_comment):
            self.ai_suggest_timer.stop()
            return

        self.ai_suggest_timer.start(300)

    def request_completion_hotkey(self):
        """Called directly by Ctrl+Space. Always fires a completion at the cursor."""
        self.clear_ghost_text()
        # Cancel any in-flight worker safely
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
        """Fires when the user pauses typing at a logical boundary."""
        try:
            # Check if the Python variable exists
            if hasattr(self, 'ai_thread') and self.ai_thread is not None:
                # If C++ hasn't deleted it yet, check if it's running
                if self.ai_thread.isRunning():
                    return
        except RuntimeError:
            # Catch the crash! The C++ thread was already deleted by deleteLater().
            # We safely clear the dead Python pointer so we can start fresh.
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
        # Center it on the editor
        palette.move(
            self.mapToGlobal(self.rect().center()) - palette.rect().center()
        )
        palette.snippet_selected.connect(self._insert_snippet_code)
        palette.exec()

    def _insert_snippet_code(self, code):
        cursor = self.textCursor()
        # Match indentation of the current line
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
        
        # [NEW] Safely sync the minimap text in the background without causing typing lag
        if self.minimap.toPlainText() != current_text:
            scroll = self.minimap.verticalScrollBar().value()
            self.minimap.setPlainText(current_text)
            
            # Re-apply line height format to the minimap
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
        space = 14 + self.fontMetrics().horizontalAdvance('9') * digits 
        return space

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

    def line_number_area_paint_event(self, event):
        painter = QPainter(self.line_number_area)
        painter.fillRect(event.rect(), QColor(35, 35, 35))
        
        # Match the editor background perfectly for a seamless look
        painter.fillRect(event.rect(), QColor("#1E1E1E"))
        
        # Draw a crisp 1px separator line down the right side of the gutter
        painter.setPen(QColor("#333333"))
        painter.drawLine(self.line_number_area.width() - 1, event.rect().top(),
                         self.line_number_area.width() - 1, event.rect().bottom())

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(block_number + 1)
                painter.setPen(QColor(120, 120, 120))
                painter.drawText(0, top, self.line_number_area.width() - 8, self.fontMetrics().height(),
                                 Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, number)

                status = self.line_changes.get(block_number)
                if status:
                    color = QColor("#4CAF50") if status == 'added' else QColor("#F0A30A")
                    painter.fillRect(self.line_number_area.width() - 4, top, 4, self.fontMetrics().height(), color)

            block = block.next()
            top = bottom
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
        cursor = self.textCursor()
        cursor.insertText(self.ghost_text)
        self.clear_ghost_text()

    def accept_next_word(self):
        if not self.ghost_text:
            return
        parts = self.ghost_text.lstrip().split(" ", 1)
        word = parts[0]
        remainder = parts[1] if len(parts) > 1 else ""

        cursor = self.textCursor()
        cursor.insertText(word + " ")
        self.ghost_text = remainder
        self.viewport().update()

    def get_ast_context(self):
        text = self.toPlainText()
        try:
            tree = ast.parse(text)
        except Exception:
            return text[-1000:]

        functions = []
        classes = []

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                functions.append(node.name)
            elif isinstance(node, ast.ClassDef):
                classes.append(node.name)

        context = f"Functions: {functions}\nClasses: {classes}\n"
        return context + "\n" + text[-1000:]

    def handle_comment_generate(self, comment):
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
        cursor.insertBlock()
        cursor.insertBlock()

        self.function_cursor = self.textCursor()
        self.function_active = True
        context = self.get_ast_context()

        prompt = f"Generate a Python function for this comment:\n\n{comment}\n\nContext:\n{context}\n\nReturn ONLY code."
        self.start_worker(prompt, generate_function=True)

    def replace_selection_with_ai(self):
        cursor = self.textCursor()
        if not cursor.hasSelection():
            return

        selected_text = cursor.selectedText().replace('\u2029', '\n')
        prompt = f"Rewrite or improve this Python code:\n\n{selected_text}\n\nReturn ONLY code."
        
        self.replacement_cursor = cursor
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

        # Pull settings if available, otherwise fall back to empty strings
        model = ""
        api_url = ""
        api_key = ""
        backend = "llama"

        if self.settings_manager:
            model   = self.settings_manager.get_model()
            api_url = self.settings_manager.get_api_url()
            api_key = self.settings_manager.get_api_key()
            backend = self.settings_manager.get_backend()

        worker = AIWorker(
            prompt=prompt,
            editor_text=self.toPlainText(),
            cursor_pos=self.textCursor().position(),
            generate_function=generate_function,
            is_edit=replace_selection,
            model=model,        # <-- was missing
            api_url=api_url,    # <-- was missing
            api_key=api_key,    # <-- was missing
            backend=backend,    # <-- was missing
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
        """
        Public entrypoint used everywhere else.
        """

        self.ai_started.emit()

        worker, thread = self._create_ai_worker(
            prompt,
            generate_function,
            replace_selection
        )

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
            self.apply_replacement()

        self.function_active = False
        self.function_cursor = None
        self.function_output = ""

    def apply_replacement(self):
        cursor = self.replacement_cursor
        cursor.removeSelectedText()
        cursor.insertText(self.function_output)

    def keyPressEvent(self, event):
        # Navigation keys should kill the AI countdown immediately
        if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down):
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

        if event.key() == Qt.Key.Key_Space and event.modifiers() == (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier):
            self.show_snippet_menu()
            return

        if event.key() == Qt.Key.Key_Tab:
            if self.ghost_text:
                self.accept_full_completion()
                return

        if event.key() == Qt.Key.Key_Right and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            self.accept_next_word()
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

            if previous_line_stripped.startswith("#"):
                self.handle_comment_generate(previous_line_stripped)

            self.clear_ghost_text()
            return

        super().keyPressEvent(event)
        self.clear_ghost_text()

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

        space_width = fm.horizontalAdvance(' ')
        indent_width = space_width * 4 
        offset_x = self.contentOffset().x() + self.document().documentMargin()

        painter.setPen(QColor(80, 80, 80, 80)) 

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

                levels = indent_spaces // 4
                
                for i in range(1, levels + 1):
                    x = int(offset_x + (i * indent_width))
                    painter.drawLine(x, top, x, bottom)

            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())

        if self.ghost_text:
            painter.setPen(QColor(120, 120, 120, 160))
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

            cursor = self.textCursor()
            rect = self.cursorRect(cursor)
            
            x = rect.left()
            y = rect.top() + fm.ascent()

            line_spacing = round(self.blockBoundingRect(self.textCursor().block()).height())
            if line_spacing == 0: 
                line_spacing = fm.height() * 1.5 

            lines = self.ghost_text.split("\n")
            for i, line in enumerate(lines):
                painter.drawText(x, int(y + i * line_spacing), line)
