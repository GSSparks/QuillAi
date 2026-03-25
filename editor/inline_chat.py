import base64
import re
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLineEdit,
                             QPushButton, QLabel, QTextEdit, QSizePolicy)
from PyQt6.QtCore import Qt, pyqtSignal, QThread, QTimer
from PyQt6.QtGui import QKeySequence, QShortcut, QTextCursor


class InlineChatWidget(QWidget):
    insert_requested = pyqtSignal(str)
    send_to_chat_requested = pyqtSignal(str, str)
    question_ready = pyqtSignal(str)        # ADD THIS LINE
    closed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("inlineChat")
        self._worker = None
        self._thread = None
        self._response_text = ""
        self._last_code_block = ""
        self.setFixedWidth(500)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("""
            QWidget#inlineChat {
                background-color: #252526;
                border: 1px solid #0E639C;
                border-radius: 6px;
            }
        """)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Header ────────────────────────────────────────────
        header = QWidget()
        header.setStyleSheet("background-color: #1A2A3A; border-radius: 6px 6px 0 0;")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(8, 5, 8, 5)

        title = QLabel("⚡ QuillAI")
        title.setStyleSheet("color: #4EC9FF; font-weight: bold; font-size: 9pt; background: transparent;")

        self.context_label = QLabel("")
        self.context_label.setStyleSheet("color: #555555; font-size: 8pt; background: transparent;")

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(16, 16)
        close_btn.setStyleSheet("""
            QPushButton {
                background: transparent; color: #555555;
                border: none; font-size: 9pt; padding: 0;
            }
            QPushButton:hover { color: #F44336; }
        """)
        close_btn.clicked.connect(self.close_panel)

        header_layout.addWidget(title)
        header_layout.addWidget(self.context_label)
        header_layout.addStretch()
        header_layout.addWidget(close_btn)
        layout.addWidget(header)

        # ── Input ─────────────────────────────────────────────
        input_container = QWidget()
        input_container.setStyleSheet(
            "background: #1E1E1E; border-top: 1px solid #0E639C44;"
        )
        input_layout = QHBoxLayout(input_container)
        input_layout.setContentsMargins(8, 5, 8, 5)

        self.input = QLineEdit()
        self.input.setPlaceholderText("Ask about this code... (Enter to send)")
        self.input.setStyleSheet("""
            QLineEdit {
                background: transparent;
                border: none;
                color: #FFFFFF;
                font-family: 'Inter', 'Segoe UI', sans-serif;
                font-size: 10pt;
            }
        """)
        self.input.installEventFilter(self)

        self.send_btn = QPushButton("➤")
        self.send_btn.setFixedSize(22, 22)
        self.send_btn.setStyleSheet("""
            QPushButton {
                background-color: #0E639C; color: white;
                border: none; border-radius: 4px; font-size: 10pt;
            }
            QPushButton:hover { background-color: #1177BB; }
        """)
        self.send_btn.clicked.connect(self.send)

        input_layout.addWidget(self.input)
        input_layout.addWidget(self.send_btn)
        layout.addWidget(input_container)

        # ── Response ──────────────────────────────────────────
        self.response_area = QTextEdit()
        self.response_area.setReadOnly(True)
        self.response_area.setMaximumHeight(160)
        self.response_area.setMinimumHeight(0)
        self.response_area.setVisible(False)
        self.response_area.setStyleSheet("""
            QTextEdit {
                background-color: #1A1A1C;
                color: #D4D4D4;
                border: none;
                border-top: 1px solid #2A2A2A;
                font-family: 'Inter', 'Segoe UI', sans-serif;
                font-size: 10pt;
                padding: 8px;
            }
        """)
        layout.addWidget(self.response_area)

        # ── Footer buttons ────────────────────────────────────
        self.footer = QWidget()
        self.footer.setStyleSheet(
            "background: #252526; border-top: 1px solid #2A2A2A;"
            "border-radius: 0 0 6px 6px;"
        )
        self.footer.setVisible(False)
        footer_layout = QHBoxLayout(self.footer)
        footer_layout.setContentsMargins(8, 5, 8, 5)
        footer_layout.setSpacing(6)

        self.insert_btn = QPushButton("⚡ Insert")
        self.insert_btn.setStyleSheet("""
            QPushButton {
                background-color: #0E639C; color: white;
                border: none; border-radius: 3px;
                padding: 3px 10px; font-size: 9pt; font-weight: bold;
            }
            QPushButton:hover { background-color: #1177BB; }
        """)
        self.insert_btn.setVisible(False)
        self.insert_btn.clicked.connect(self._insert_code)

        self.chat_btn = QPushButton("↗ Send to Chat")
        self.chat_btn.setStyleSheet("""
            QPushButton {
                background-color: #3E3E42; color: #CCCCCC;
                border: none; border-radius: 3px;
                padding: 3px 10px; font-size: 9pt;
            }
            QPushButton:hover { background-color: #4E4E52; }
        """)
        self.chat_btn.clicked.connect(self._send_to_chat)

        footer_layout.addWidget(self.insert_btn)
        footer_layout.addWidget(self.chat_btn)
        footer_layout.addStretch()
        layout.addWidget(self.footer)

    def set_context(self, line_num, line_text):
        truncated = line_text.strip()[:40]
        if len(line_text.strip()) > 40:
            truncated += "..."
        self.context_label.setText(f"line {line_num}  ·  Esc to close")
        self.input.setFocus()

    def send(self):
        question = self.input.text().strip()
        if not question:
            return
    
        # Disable input while request is in flight
        self.input.setEnabled(False)
        self.send_btn.setEnabled(False)
        self.send_btn.setText("...")
    
        self._response_text = ""
        self._last_code_block = ""
        self.response_area.clear()
        self.response_area.setVisible(True)
        self.response_area.setPlainText("...")
        self.footer.setVisible(True)
        self.insert_btn.setVisible(False)
        self.adjustSize()
    
        self.current_question = question
        self.question_ready.emit(question)

    def append_response(self, text):
        self._response_text += text
        cursor = self.response_area.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        if self.response_area.toPlainText() == "...":
            self.response_area.clear()
            cursor = self.response_area.textCursor()
        cursor.insertText(text)
        self.response_area.ensureCursorVisible()

    def response_finished(self):
        # Re-enable input
        self.input.setEnabled(True)
        self.send_btn.setEnabled(True)
        self.send_btn.setText("➤")
        self.input.clear()
        self.input.setFocus()
    
        # Extract last code block if any
        blocks = re.findall(r"```.*?\n(.*?)```", self._response_text, re.DOTALL)
        if blocks:
            self._last_code_block = blocks[-1].strip()
            self.insert_btn.setVisible(True)
        self.adjustSize()

    def _insert_code(self):
        if self._last_code_block:
            self.insert_requested.emit(self._last_code_block)
            self.close_panel()

    def _send_to_chat(self):
        self.send_to_chat_requested.emit(
            getattr(self, 'current_question', ''),
            self._response_text
        )
        self.close_panel()
        
    def eventFilter(self, obj, event):
        from PyQt6.QtCore import QEvent
        if obj == self.input and event.type() == QEvent.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.send()
                return True  # consume — never reaches the editor
            if event.key() == Qt.Key.Key_Escape:
                self.close_panel()
                return True
        return super().eventFilter(obj, event)
        
    def close_panel(self):
        self.hide()
        self.closed.emit()
        # Return focus to editor
        if self.parent():
            self.parent().setFocus()