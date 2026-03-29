import base64
import re
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLineEdit,
                             QPushButton, QLabel, QTextEdit, QSizePolicy)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QTextCursor

from ui.theme import get_theme, theme_signals


class InlineChatWidget(QWidget):
    insert_requested      = pyqtSignal(str)
    send_to_chat_requested = pyqtSignal(str, str)
    question_ready        = pyqtSignal(str)
    closed                = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("inlineChat")
        self._response_text  = ""
        self._last_code_block = ""
        self.current_question = ""
        self.setFixedWidth(520)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._setup_ui()

        # Live theme updates
        theme_signals.theme_changed.connect(self._on_theme_changed)

    def _get_theme(self) -> dict:
        p = self.parent()
        while p:
            if hasattr(p, 'settings_manager') and p.settings_manager:
                return get_theme(p.settings_manager.get('theme'))
            p = p.parent() if hasattr(p, 'parent') else None
        return get_theme()

    def _on_theme_changed(self, t: dict):
        self._apply_styles(t)

    def _apply_styles(self, t: dict = None):
        if t is None:
            t = self._get_theme()

        self.setStyleSheet(f"""
            QWidget#inlineChat {{
                background-color: {t['bg1']};
                border: 1px solid {t['accent']};
                border-radius: 6px;
            }}
        """)

        self.header.setStyleSheet(
            f"background-color: {t['bg0_hard']}; border-radius: 6px 6px 0 0;"
        )
        self.title_label.setStyleSheet(
            f"color: {t['aqua']}; font-weight: bold; font-size: 9pt; background: transparent;"
        )
        self.context_label.setStyleSheet(
            f"color: {t['fg4']}; font-size: 8pt; background: transparent;"
        )
        self.close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {t['fg4']};
                border: none; font-size: 9pt; padding: 0;
            }}
            QPushButton:hover {{ color: {t['red']}; }}
        """)

        self.input_container.setStyleSheet(
            f"background: {t['bg0_hard']}; border-top: 1px solid {t['border']};"
        )
        self.input.setStyleSheet(f"""
            QLineEdit {{
                background: transparent;
                border: none;
                color: {t['fg0']};
                font-family: 'Inter', 'Segoe UI', sans-serif;
                font-size: 10pt;
            }}
        """)
        self.send_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {t['accent']};
                color: {t['bg0_hard']};
                border: none; border-radius: 4px; font-size: 10pt;
            }}
            QPushButton:hover {{ background-color: {t['yellow']}; }}
        """)

        self.response_area.setStyleSheet(f"""
            QTextEdit {{
                background-color: {t['bg0_hard']};
                color: {t['fg1']};
                border: none;
                border-top: 1px solid {t['border']};
                font-family: 'Inter', 'Segoe UI', sans-serif;
                font-size: 10pt;
                padding: 8px;
            }}
        """)

        self.footer.setStyleSheet(
            f"background: {t['bg1']}; border-top: 1px solid {t['border']};"
            f"border-radius: 0 0 6px 6px;"
        )
        self.insert_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {t['accent']};
                color: {t['bg0_hard']};
                border: none; border-radius: 3px;
                padding: 3px 10px; font-size: 9pt; font-weight: bold;
            }}
            QPushButton:hover {{ background-color: {t['yellow']}; }}
        """)
        self.chat_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {t['bg2']};
                color: {t['fg1']};
                border: none; border-radius: 3px;
                padding: 3px 10px; font-size: 9pt;
            }}
            QPushButton:hover {{ background-color: {t['bg3']}; }}
        """)
        self.clear_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {t['fg4']};
                border: none; border-radius: 3px;
                padding: 3px 8px; font-size: 9pt;
            }}
            QPushButton:hover {{ color: {t['red']}; }}
        """)

    def _setup_ui(self):
        t = self._get_theme()

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

        self._apply_styles(t)

    # ── Public API ────────────────────────────────────────────

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

        # Extract last code block
        blocks = re.findall(r"```.*?\n(.*?)```", self._response_text, re.DOTALL)
        if blocks:
            self._last_code_block = blocks[-1].strip()
            self.insert_btn.setVisible(True)

        self.adjustSize()

    # ── Actions ───────────────────────────────────────────────

    def _insert_code(self):
        if self._last_code_block:
            self.insert_requested.emit(self._last_code_block)
            self.close_panel()

    def _send_to_chat(self):
        self.send_to_chat_requested.emit(
            self.current_question,
            self._response_text
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

    # ── Events ────────────────────────────────────────────────

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