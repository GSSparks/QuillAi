from PyQt6.QtWidgets import QPlainTextEdit, QWidget, QTextEdit
from PyQt6.QtGui import QPainter, QColor, QFontMetrics, QTextCursor, QFont, QTextFormat
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QRect, QSize, QTimer
import re
import ast
import difflib

from ai.worker import AIWorker

class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.codeEditor = editor

    def sizeHint(self):
        return QSize(self.codeEditor.line_number_area_width(), 0)

    def paintEvent(self, event):
        self.codeEditor.line_number_area_paint_event(event)

class GhostEditor(QPlainTextEdit):
    # [FIXED] Define custom signals to talk to the main window
    ai_started = pyqtSignal()
    ai_finished = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setStyleSheet("""
            QPlainTextEdit {
                background-color: #1E1E1E;
                color: #CCCCCC;
                border: none;
            }
        """)

        self.ghost_text = ""

        # function streaming state
        self.function_cursor = None
        self.function_active = False
        self.function_output = ""

        font = QFont("JetBrains Mono")
        font.setPointSize(11)
        font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        self.setFont(font)

        # --- NEW: Change Tracking State ---
        self.original_text = ""
        self.line_changes = {} # Stores {line_index: 'added' | 'modified'}
        
        self.diff_timer = QTimer(self)
        self.diff_timer.setSingleShot(True)
        self.diff_timer.timeout.connect(self.calculate_diff)
        self.textChanged.connect(lambda: self.diff_timer.start(400)) # 400ms debounce

        # --- Line Number Setup ---
        self.line_number_area = LineNumberArea(self)

        # When the document changes size, update the margin
        self.blockCountChanged.connect(self.update_line_number_area_width)
        # When the editor scrolls, scroll the line numbers
        self.updateRequest.connect(self.update_line_number_area)

        self.update_line_number_area_width(0)
        self.setTabStopDistance(4 * self.fontMetrics().horizontalAdvance(' '))
        self.cursorPositionChanged.connect(self.highlight_current_line)
        self.highlight_current_line() # Call once to highlight line 1 on startup

    def highlight_current_line(self):
        extra_selections = []
        if not self.isReadOnly():
            selection = QTextEdit.ExtraSelection()
            # A subtle dark-theme friendly highlight color
            line_color = QColor(60, 60, 60, 100)
            selection.format.setBackground(line_color)
            selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)

            selection.cursor = self.textCursor()
            selection.cursor.clearSelection()
            extra_selections.append(selection)

        self.setExtraSelections(extra_selections)

    # -----------------------------
    # Change Tracking Methods
    # -----------------------------
    def set_original_state(self, text):
        """Call this when a file is loaded or saved to reset the tracking."""
        self.original_text = text
        self.line_changes.clear()
        self.line_number_area.update()

    # [NEW] Check if the file has unsaved changes
    def is_dirty(self):
        """Returns True if the current text differs from the last saved state."""
        return self.toPlainText() != self.original_text

    def calculate_diff(self):
        """Compares current text to the original state and maps changed lines."""
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
        self.line_number_area.update() # Force repaint

    # -----------------------------
    # Line Number Panel
    # -----------------------------
    def line_number_area_width(self):
        # Calculate how much space we need based on the number of lines
        digits = 1
        max_value = max(1, self.blockCount())
        while max_value >= 10:
            max_value /= 10
            digits += 1

        # 10px padding + width of a character * number of digits + 4px for the color bar
        space = 14 + self.fontMetrics().horizontalAdvance('9') * digits 
        return space

    def update_line_number_area_width(self, _):
        # Push the text editor to the right to make room for the line numbers
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def update_line_number_area(self, rect, dy):
        # Handle scrolling
        if dy:
            self.line_number_area.scroll(0, dy)
        else:
            self.line_number_area.update(0, rect.y(), self.line_number_area.width(), rect.height())

        if rect.contains(self.viewport().rect()):
            self.update_line_number_area_width(0)

    def resizeEvent(self, event):
        # When the window resizes, resize the line number panel
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.line_number_area.setGeometry(QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height()))

    def line_number_area_paint_event(self, event):
        painter = QPainter(self.line_number_area)

        # Lock to dark grey background
        painter.fillRect(event.rect(), QColor(35, 35, 35))

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(block_number + 1)

                # Lock to muted grey text
                painter.setPen(QColor(120, 120, 120))

                # Shift text over slightly so it doesn't overlap the color bar
                painter.drawText(0, top, self.line_number_area.width() - 8, self.fontMetrics().height(),
                                 Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, number)

                # --- NEW: Draw the modification color bar ---
                status = self.line_changes.get(block_number)
                if status:
                    # Added = Green, Modified = Yellow/Orange
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

        # shrink ghost text
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

        context = f"""
Functions: {functions}
Classes: {classes}
"""

        return context + "\n" + text[-1000:]

    # -----------------------------
    # AI actions
    # -----------------------------
    def handle_comment_generate(self, comment):
        cursor = self.textCursor()

        # create space below comment
        cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
        cursor.insertBlock()
        cursor.insertBlock()

        # anchor cursor for streaming
        self.function_cursor = self.textCursor()
        self.function_active = True

        context = self.get_ast_context()

        prompt = f"""
Generate a Python function for this comment:

{comment}

Context:
{context}

Return ONLY code.
"""

        self.start_worker(prompt, generate_function=True)

    def replace_selection_with_ai(self):
        cursor = self.textCursor()

        if not cursor.hasSelection():
            return

        # [NEW] Fix the PyQt Unicode newline bug
        selected_text = cursor.selectedText().replace('\u2029', '\n')

        prompt = f"""
Rewrite or improve this Python code:

{selected_text}

Return ONLY code.
"""
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
            # Streams deltas directly into the editor
            self.function_cursor.insertText(text)
        else:
            # replacement mode: accumulate deltas to insert when finished
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
        # Auto-close brackets and quotes
        pairs = {'(': ')', '[': ']', '{': '}', '"': '"', "'": "'"}
        char = event.text()

        if char in pairs:
            # Insert both the opening and closing characters
            super().keyPressEvent(event)
            cursor = self.textCursor()
            cursor.insertText(pairs[char])
            # Move cursor back one space to sit between them
            cursor.movePosition(QTextCursor.MoveOperation.Left)
            self.setTextCursor(cursor)
            self.clear_ghost_text()
            return

        # TAB → accept full ghost
        if event.key() == Qt.Key.Key_Tab:
            if self.ghost_text:
                self.accept_full_completion()
                return

        # Ctrl + → → accept next word
        if event.key() == Qt.Key.Key_Right and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            self.accept_next_word()
            return

        # Ctrl + E → AI replace
        if event.key() == Qt.Key.Key_E and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            self.replace_selection_with_ai()
            return

        # ENTER handling
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            cursor = self.textCursor()

            # Grab previous line before we hit enter
            cursor.select(QTextCursor.SelectionType.LineUnderCursor)
            previous_line_raw = cursor.selectedText()
            previous_line_stripped = previous_line_raw.strip()

            # Perform normal Enter (moves to next line)
            super().keyPressEvent(event)

            # --- NEW: Smart Auto-Indent ---
            # 1. Copy whitespace from the line we just left
            whitespace_match = re.match(r"^\s*", previous_line_raw)
            indent = whitespace_match.group(0) if whitespace_match else ""

            # 2. Add an extra indent block if the previous line ended with a colon
            if previous_line_stripped.endswith(":"):
                indent += "    " # 4 spaces

            # 3. Insert the calculated whitespace
            if indent:
                self.textCursor().insertText(indent)
            # ------------------------------

            # Check for AI generation triggers
            if previous_line_stripped.startswith("#"):
                self.handle_comment_generate(previous_line_stripped)

            self.clear_ghost_text()
            return

        # default behavior
        super().keyPressEvent(event)

        # clear ghost on typing
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