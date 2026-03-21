from PyQt6.QtWidgets import QPlainTextEdit, QWidget, QTextEdit, QMenu
from PyQt6.QtGui import QPainter, QColor, QFontMetrics, QTextCursor, QFont, QTextFormat, QAction, QTextCharFormat, QIcon
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QRect, QSize, QTimer
import re
import ast
import difflib

from ai.worker import AIWorker

# ==========================================
# Professional Snippet Manager
# ==========================================
class SnippetManager:
    def __init__(self):
        self.snippets = {
            "for loop": "for i in range():\n    pass",
            "if statement": "if condition:\n    pass",
            "def function": "def function_name():\n    pass",
            "class definition": "class ClassName:\n    def __init__(self):\n        pass",
            "try/except": "try:\n    pass\nexcept Exception as e:\n    print(e)",
            "main block": "if __name__ == '__main__':\n    main()",
            "list comprehension": "[x for x in items if condition]",
            "with open (read)": "with open('filename.txt', 'r', encoding='utf-8') as f:\n    content = f.read()",
            "with open (write)": "with open('filename.txt', 'w', encoding='utf-8') as f:\n    f.write(content)"
        }

    def get_snippets(self, prefix=""):
        if not prefix:
            return self.snippets
        filtered = {k: v for k, v in self.snippets.items() if prefix.lower() in k.lower()}
        return filtered if filtered else self.snippets


class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.codeEditor = editor

    def sizeHint(self):
        return QSize(self.codeEditor.line_number_area_width(), 0)

    def paintEvent(self, event):
        self.codeEditor.line_number_area_paint_event(event)


class GhostEditor(QPlainTextEdit):
    ai_started = pyqtSignal()
    ai_finished = pyqtSignal()
    
    error_help_requested = pyqtSignal(str, str, int) # message, full_code, line_number

    def __init__(self):
        super().__init__()
        self.setStyleSheet("""
            QPlainTextEdit {
                background-color: #1E1E1E;
                color: #CCCCCC;
                border: none;
            }
        """)
        
        self.file_path = None
        self.ghost_text = ""
        self.snippet_manager = SnippetManager() 

        self.function_cursor = None
        self.function_active = False
        self.function_output = ""

        font = QFont("JetBrains Mono")
        font.setPointSize(11)
        font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        self.setFont(font)

        # --- Change Tracking State ---
        self.original_text = ""
        self.line_changes = {} 
        
        self.diff_timer = QTimer(self)
        self.diff_timer.setSingleShot(True)
        self.diff_timer.timeout.connect(self.calculate_diff)
        self.textChanged.connect(lambda: self.diff_timer.start(400)) 

        # --- Real-time Linter Setup ---
        self.lint_timer = QTimer(self)
        self.lint_timer.setSingleShot(True)
        self.lint_timer.timeout.connect(self.run_linter)
        self.textChanged.connect(lambda: self.lint_timer.start(750)) 
        
        self.current_line_selection = []
        self.lint_selections = []
        
        # [NEW] Store the active syntax error so we can send it to the AI
        self.current_syntax_error = None

        # --- Line Number Setup ---
        self.line_number_area = LineNumberArea(self)
        self.blockCountChanged.connect(self.update_line_number_area_width)
        self.updateRequest.connect(self.update_line_number_area)
        self.update_line_number_area_width(0)
        self.setTabStopDistance(4 * self.fontMetrics().horizontalAdvance(' '))
        
        self.cursorPositionChanged.connect(self.highlight_current_line)
        self.highlight_current_line() 

    # -----------------------------
    # Visual Highlights & Linting
    # -----------------------------
    def highlight_current_line(self):
        self.current_line_selection = []
        if not self.isReadOnly():
            selection = QTextEdit.ExtraSelection()
            line_color = QColor(60, 60, 60, 100)
            selection.format.setBackground(line_color)
            selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)

            selection.cursor = self.textCursor()
            selection.cursor.clearSelection()
            self.current_line_selection.append(selection)

        self.update_extra_selections()

    def update_extra_selections(self):
        self.setExtraSelections(self.current_line_selection + self.lint_selections)

    def run_linter(self):
        self.lint_selections = []
        self.current_syntax_error = None # Reset error state
        text = self.toPlainText()
        
        if not text.strip():
            self.update_extra_selections()
            return

        # ==========================================
        # [NEW] Smart Linter Guard
        # Only parse Python files! Ignore YAML, HTML, etc.
        # ==========================================
        if self.file_path and not self.file_path.lower().endswith('.py'):
            self.update_extra_selections()
            return

        try:
            ast.parse(text)
        except SyntaxError as e:
            # [NEW] Save the error details so the right-click menu can use them
            self.current_syntax_error = {
                'msg': e.msg,
                'lineno': e.lineno,
                'offset': e.offset
            }
            
            selection = QTextEdit.ExtraSelection()
            selection.format.setUnderlineStyle(QTextCharFormat.UnderlineStyle.WaveUnderline)
            selection.format.setUnderlineColor(QColor("#F44336")) 
            
            cursor = QTextCursor(self.document())
            
            line_idx = (e.lineno - 1) if e.lineno is not None else 0
            col_offset = (e.offset - 1) if e.offset is not None else 0
            
            cursor.setPosition(self.document().findBlockByNumber(line_idx).position())
            cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.MoveAnchor, col_offset)
            
            if hasattr(e, 'end_offset') and e.end_offset is not None and e.end_offset > e.offset:
                length = e.end_offset - e.offset
                cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, length)
            else:
                cursor.select(QTextCursor.SelectionType.WordUnderCursor)
            
            if not cursor.hasSelection():
                cursor.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.KeepAnchor, 1)

            selection.cursor = cursor
            self.lint_selections.append(selection)
        except Exception:
            pass
            
        self.update_extra_selections()

    # -----------------------------
    # [NEW] Right-Click Context Menu
    # -----------------------------
    def contextMenuEvent(self, event):
        # Generate the standard PyQt copy/paste menu
        menu = self.createStandardContextMenu(event.pos())
        
        # Figure out which line the user just right-clicked on
        cursor = self.cursorForPosition(event.pos())
        clicked_line = cursor.blockNumber() + 1 # 1-based index to match ast.lineno
        
        # If there is an error, and the user right-clicked exactly on the error line...
        if self.current_syntax_error and self.current_syntax_error['lineno'] == clicked_line:
            menu.addSeparator()
            
            fix_action = QAction(QIcon(), "💡 Explain & Fix Error with AI", self)
            fix_action.triggered.connect(self.trigger_ai_error_fix)
            
            # Make it stand out visually in the menu
            font = fix_action.font()
            font.setBold(True)
            fix_action.setFont(font)
            
            menu.addAction(fix_action)
            
        menu.exec(event.globalPos())

    def trigger_ai_error_fix(self):
        if self.current_syntax_error:
            # Tell main.py to open the chat dock and ask the AI!
            self.error_help_requested.emit(
                self.current_syntax_error['msg'],
                self.toPlainText(),
                self.current_syntax_error['lineno']
            )

    # -----------------------------
    # Snippet Menu Methods
    # -----------------------------
    def show_snippet_menu(self):
        cursor = self.textCursor()
        cursor.select(QTextCursor.SelectionType.WordUnderCursor)
        prefix = cursor.selectedText().strip()

        snippets = self.snippet_manager.get_snippets(prefix)
        if not snippets:
            return

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background-color: #252526; color: #CCCCCC; border: 1px solid #3E3E42; font-family: 'Inter', sans-serif; }
            QMenu::item { padding: 6px 20px; }
            QMenu::item:selected { background-color: #0E639C; color: white; }
        """)

        for name, code in snippets.items():
            action = QAction(name, self)
            action.triggered.connect(lambda checked, c=code, p=prefix: self.insert_snippet(c, p))
            menu.addAction(action)

        rect = self.cursorRect(self.textCursor())
        global_pos = self.viewport().mapToGlobal(rect.bottomRight())
        menu.exec(global_pos)

    def insert_snippet(self, snippet_code, prefix):
        cursor = self.textCursor()
        
        if prefix:
            cursor.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.KeepAnchor, len(prefix))
            cursor.removeSelectedText()

        cursor.select(QTextCursor.SelectionType.LineUnderCursor)
        line_text = cursor.selectedText()
        cursor.clearSelection()
        
        indent_match = re.match(r"^\s*", line_text)
        base_indent = indent_match.group(0) if indent_match else ""

        lines = snippet_code.split('\n')
        formatted_snippet = lines[0] 
        if len(lines) > 1:
            for line in lines[1:]:
                formatted_snippet += "\n" + base_indent + line

        cursor.insertText(formatted_snippet)
        self.clear_ghost_text()

    # -----------------------------
    # Change Tracking Methods
    # -----------------------------
    def set_original_state(self, text):
        self.original_text = text
        self.line_changes.clear()
        self.line_number_area.update()

    def is_dirty(self):
        return self.toPlainText() != self.original_text

    def calculate_diff(self):
        current_lines = self.toPlainText().split('\n')
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

    # -----------------------------
    # Line Number Panel
    # -----------------------------
    def line_number_area_width(self):
        digits = 1
        max_value = max(1, self.blockCount())
        while max_value >= 10:
            max_value /= 10
            digits += 1
        space = 14 + self.fontMetrics().horizontalAdvance('9') * digits 
        return space

    def update_line_number_area_width(self, _):
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

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

    def line_number_area_paint_event(self, event):
        painter = QPainter(self.line_number_area)
        painter.fillRect(event.rect(), QColor(35, 35, 35))

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

    # -----------------------------
    # Ghost handling
    # -----------------------------
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

    # -----------------------------
    # AST-aware context
    # -----------------------------
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

    # -----------------------------
    # AI actions
    # -----------------------------
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

    def start_worker(self, prompt, generate_function=False, replace_selection=False):
        self.thread = QThread()
        self.function_output = ""
        self.ai_started.emit()

        self.worker = AIWorker(
            prompt=prompt,
            editor_text=self.toPlainText(),
            cursor_pos=self.textCursor().position(),
            generate_function=generate_function,
            is_edit=replace_selection 
        )

        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)

        if not generate_function and not replace_selection:
            self.worker.update_ghost.connect(self.set_ghost_text)

        self.worker.function_ready.connect(self.handle_function_output)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.worker.finished.connect(self.finish_function_stream)
        self.worker.finished.connect(self.ai_finished.emit)

        self.thread.start()

    # -----------------------------
    # Apply AI output
    # -----------------------------
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

    # -----------------------------
    # Key handling
    # -----------------------------
    def keyPressEvent(self, event):
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

        if event.key() == Qt.Key.Key_Space and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
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

    # -----------------------------
    # Paint ghost (inline style)
    # -----------------------------
    def paintEvent(self, event):
        super().paintEvent(event)

        if not self.ghost_text:
            return

        painter = QPainter(self.viewport())
        if not painter.isActive():
            return

        painter.setPen(QColor(120, 120, 120, 160))
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        cursor = self.textCursor()
        rect = self.cursorRect(cursor)
        fm = QFontMetrics(self.font())

        x = rect.left()
        y = rect.top() + fm.ascent()

        lines = self.ghost_text.split("\n")
        for i, line in enumerate(lines):
            painter.drawText(x, y + i * fm.height(), line)