import re
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLineEdit,
                             QPushButton, QLabel, QTextEdit)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QTextCursor

from ui.theme import get_theme, theme_signals, build_inline_chat_stylesheet


class InlineChatWidget(QWidget):
    insert_requested       = pyqtSignal(str)
    send_to_chat_requested = pyqtSignal(str, str)
    question_ready         = pyqtSignal(str)
    closed                 = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("inlineChat")
        self._response_text   = ""
        self._last_code_block = ""
        self.current_question = ""
        self.setFixedWidth(520)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._setup_ui()

        theme_signals.theme_changed.connect(self._on_theme_changed)

    # ── Theme handling ────────────────────────────────────────────────────

    def _on_theme_changed(self, t: dict):
        self._apply_styles(t)

    def _apply_styles(self, t: dict):
        s = build_inline_chat_stylesheet(t)
        self.setStyleSheet(s["panel"])
        self.header.setStyleSheet(s["header"])
        self.title_label.setStyleSheet(s["title_label"])
        self.context_label.setStyleSheet(s["context_label"])
        self.close_btn.setStyleSheet(s["close_btn"])
        self.input_container.setStyleSheet(s["input_container"])
        self.input.setStyleSheet(s["input"])
        self.send_btn.setStyleSheet(s["send_btn"])
        self.response_area.setStyleSheet(s["response_area"])
        self.footer.setStyleSheet(s["footer"])
        self.insert_btn.setStyleSheet(s["insert_btn"])
        self.chat_btn.setStyleSheet(s["chat_btn"])
        self.clear_btn.setStyleSheet(s["clear_btn"])

    # ── UI Setup ──────────────────────────────────────────────────────────

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Header ────────────────────────────────────────────
        self.header = QWidget()
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(10, 6, 8, 6)

        self.title_label = QLabel("⚡ Inline AI")
        self.context_label = QLabel("")

        self.close_btn = QPushButton("✕")
        self.close_btn.setFixedSize(16, 16)
        self.close_btn.clicked.connect(self.close_panel)

        header_layout.addWidget(self.title_label)
        header_layout.addWidget(self.context_label)
        header_layout.addStretch()
        header_layout.addWidget(self.close_btn)
        layout.addWidget(self.header)

        # ── Input ─────────────────────────────────────────────
        self.input_container = QWidget()
        input_layout = QHBoxLayout(self.input_container)
        input_layout.setContentsMargins(10, 6, 8, 6)

        self.input = QLineEdit()
        self.input.setPlaceholderText("Ask about this code... (Enter to send, Esc to close)")
        self.input.installEventFilter(self)

        self.send_btn = QPushButton("➤")
        self.send_btn.setFixedSize(24, 24)
        self.send_btn.clicked.connect(self.send)

        input_layout.addWidget(self.input)
        input_layout.addWidget(self.send_btn)
        layout.addWidget(self.input_container)

        # ── Response ──────────────────────────────────────────
        self.response_area = QTextEdit()
        self.response_area.setReadOnly(True)
        self.response_area.setMaximumHeight(200)
        self.response_area.setMinimumHeight(0)
        self.response_area.setVisible(False)
        layout.addWidget(self.response_area)

        # ── Footer ────────────────────────────────────────────
        self.footer = QWidget()
        self.footer.setVisible(False)
        footer_layout = QHBoxLayout(self.footer)
        footer_layout.setContentsMargins(8, 5, 8, 5)
        footer_layout.setSpacing(6)

        self.insert_btn = QPushButton("⚡ Insert Code")
        self.insert_btn.setVisible(False)
        self.insert_btn.clicked.connect(self._insert_code)

        self.chat_btn = QPushButton("↗ Open in Chat")
        self.chat_btn.clicked.connect(self._send_to_chat)

        self.clear_btn = QPushButton("✕ Clear")
        self.clear_btn.clicked.connect(self._clear_response)

        footer_layout.addWidget(self.insert_btn)
        footer_layout.addWidget(self.chat_btn)
        footer_layout.addStretch()
        footer_layout.addWidget(self.clear_btn)
        layout.addWidget(self.footer)

        # Apply initial styles
        self._apply_styles(get_theme())

    # ── Public API ────────────────────────────────────────────────────────

    def set_context(self, line_num, line_text):
        truncated = line_text.strip()[:50]
        if len(line_text.strip()) > 50:
            truncated += "..."
        self.context_label.setText(f"line {line_num}  ·  {truncated}")
        self.input.setFocus()

    def send(self):
        question = self.input.text().strip()
        if not question:
            return

        self.input.setEnabled(False)
        self.send_btn.setEnabled(False)
        self.send_btn.setText("…")

        self._response_text   = ""
        self._last_code_block = ""
        self.current_question = question

        self.response_area.clear()
        self.response_area.setVisible(True)
        self.response_area.setPlainText("Thinking…")
        self.footer.setVisible(True)
        self.insert_btn.setVisible(False)
        self.adjustSize()

        self.question_ready.emit(question)

    def append_response(self, text):
        self._response_text += text
        cursor = self.response_area.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        if self.response_area.toPlainText() == "Thinking…":
            self.response_area.clear()
            cursor = self.response_area.textCursor()
        cursor.insertText(text)
        self.response_area.ensureCursorVisible()

    def response_finished(self):
        self.input.setEnabled(True)
        self.send_btn.setEnabled(True)
        self.send_btn.setText("➤")
        self.input.clear()
        self.input.setFocus()

        blocks = re.findall(r"```.*?\n(.*?)```", self._response_text, re.DOTALL)
        if blocks:
            self._last_code_block = blocks[-1].strip()
            self.insert_btn.setVisible(True)

        self.adjustSize()

    # ── Actions ───────────────────────────────────────────────────────────

    def _insert_code(self):
        if self._last_code_block:
            self.insert_requested.emit(self._last_code_block)
            self.close_panel()

    def _send_to_chat(self):
        self.send_to_chat_requested.emit(
            self.current_question,
            self._response_text,
        )
        self.close_panel()

    def _clear_response(self):
        self.response_area.clear()
        self.response_area.setVisible(False)
        self.footer.setVisible(False)
        self._response_text   = ""
        self._last_code_block = ""
        self.input.clear()
        self.input.setFocus()
        self.adjustSize()

    def close_panel(self):
        self.hide()
        self.closed.emit()
        if self.parent():
            self.parent().setFocus()

    # ── Events ────────────────────────────────────────────────────────────

    def eventFilter(self, obj, event):
        from PyQt6.QtCore import QEvent
        if obj == self.input and event.type() == QEvent.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.send()
                return True
            if event.key() == Qt.Key.Key_Escape:
                self.close_panel()
                return True
        return super().eventFilter(obj, event)