from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                              QLabel, QTextEdit, QTextBrowser, QStackedWidget,
                              QSizePolicy)
from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QRect, pyqtSignal, QTimer
from PyQt6.QtGui import QKeySequence, QTextCursor, QShortcut, QCursor

from ui.theme import get_theme


class ResizeGrip(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(5)
        self.setCursor(Qt.CursorShape.SizeHorCursor)
        self.setStyleSheet("background-color: transparent;")
        self._dragging = False
        self._drag_start_x = 0
        self._drag_start_width = 0

    def _get_theme(self) -> dict:
        p = self.parent()
        if p and hasattr(p, 'settings_manager') and p.settings_manager:
            return get_theme(p.settings_manager.get('theme'))
        return get_theme()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_start_x = event.globalPosition().toPoint().x()
            self._drag_start_width = self.parent().PANEL_WIDTH
            event.accept()

    def mouseMoveEvent(self, event):
        if self._dragging:
            delta = self._drag_start_x - event.globalPosition().toPoint().x()
            new_width = max(300, min(900, self._drag_start_width + delta))
            self.parent().set_panel_width(new_width)
            event.accept()

    def mouseReleaseEvent(self, event):
        if self._dragging:
            self._dragging = False
            self.parent()._save_width()
            event.accept()

    def enterEvent(self, event):
        t = self._get_theme()
        self.setStyleSheet(f"background-color: {t['accent']};")
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.setStyleSheet("background-color: transparent;")
        super().leaveEvent(event)


class SlidingPanel(QWidget):
    message_sent = pyqtSignal(str)

    HANDLE_WIDTH = 18
    MIN_WIDTH = 300
    MAX_WIDTH = 900
    DEFAULT_WIDTH = 440

    def __init__(self, parent=None, settings_manager=None):
        super().__init__(parent)
        self.setObjectName("slidingPanel")
        self._expanded = False
        self._animating = False
        self._pinned = False
        self._hover_enabled = True
        self.settings_manager = settings_manager

        self.PANEL_WIDTH = self.DEFAULT_WIDTH
        if settings_manager:
            saved_width = settings_manager.get("panel_width")
            if saved_width:
                self.PANEL_WIDTH = max(self.MIN_WIDTH,
                                       min(self.MAX_WIDTH, int(saved_width)))

        self._hover_timer = QTimer(self)
        self._hover_timer.setSingleShot(True)
        self._hover_timer.timeout.connect(self._check_collapse)
        self._hover_timer.setInterval(600)

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMouseTracking(True)
        self._setup_ui()
        self._position_collapsed()

    def _get_theme(self) -> dict:
        theme_name = None
        if self.settings_manager:
            theme_name = self.settings_manager.get('theme')
        return get_theme(theme_name)

    def set_panel_width(self, width: int):
        self.PANEL_WIDTH = width
        self.setFixedWidth(width)
        self.content.setFixedWidth(width - self.HANDLE_WIDTH - 5)
        if self._expanded and self.parent():
            self.move(self.parent().width() - width, self.y())

    def _save_width(self):
        if self.settings_manager:
            self.settings_manager.set("panel_width", self.PANEL_WIDTH)

    def _setup_ui(self):
        t = self._get_theme()

        self.setStyleSheet(f"""
            QWidget#slidingPanel {{
                background-color: {t['bg1']};
                border-left: 1px solid {t['border']};
            }}
        """)

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Handle ────────────────────────────────────────────────
        self.handle = QWidget(self)
        self.handle.setFixedWidth(self.HANDLE_WIDTH)
        self.handle.setCursor(Qt.CursorShape.ArrowCursor)
        self.handle.setMouseTracking(True)
        self.handle.setStyleSheet("background-color: transparent;")

        handle_layout = QVBoxLayout(self.handle)
        handle_layout.setContentsMargins(0, 0, 0, 0)
        self.arrow_label = QLabel("❯")
        self.arrow_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.arrow_label.setStyleSheet(
            f"color: {t['fg4']}; font-size: 11pt; background: transparent;"
        )
        self.arrow_label.setMouseTracking(True)
        handle_layout.addStretch()
        handle_layout.addWidget(self.arrow_label)
        handle_layout.addStretch()

        # ── Resize grip ───────────────────────────────────────────
        self.resize_grip = ResizeGrip(self)

        # ── Content ───────────────────────────────────────────────
        self.content = QWidget(self)
        self.content.setFixedWidth(self.PANEL_WIDTH - self.HANDLE_WIDTH - 5)
        self.content.setMouseTracking(True)
        self.content.setStyleSheet(f"background-color: {t['bg1']};")

        content_layout = QVBoxLayout(self.content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # Tab bar
        tab_bar = QWidget(self.content)
        tab_bar.setFixedHeight(38)
        tab_bar.setStyleSheet(
            f"background-color: {t['bg0_hard']}; "
            f"border-bottom: 1px solid {t['border']};"
        )
        tab_bar_layout = QHBoxLayout(tab_bar)
        tab_bar_layout.setContentsMargins(8, 0, 8, 0)
        tab_bar_layout.setSpacing(4)

        self._tab_buttons = {}
        self._stack = QStackedWidget(self.content)
        self._stack.setMouseTracking(True)

        for i, (name, icon) in enumerate([
            ("Chat",   "💬"),
            ("Memory", "🧠"),
        ]):
            btn = QPushButton(f"{icon}  {name}")
            btn.setCheckable(True)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    color: {t['fg4']};
                    border: none;
                    border-bottom: 2px solid transparent;
                    padding: 6px 12px;
                    font-family: Inter, sans-serif;
                    font-size: 9pt;
                    font-weight: bold;
                }}
                QPushButton:checked {{
                    color: {t['fg0']};
                    border-bottom: 2px solid {t['tab_active_bar']};
                }}
                QPushButton:hover:!checked {{ color: {t['fg2']}; }}
            """)
            btn.clicked.connect(lambda checked, idx=i: self._switch_tab(idx))
            tab_bar_layout.addWidget(btn)
            self._tab_buttons[i] = btn

        tab_bar_layout.addStretch()

        self.pin_btn = QPushButton("📌")
        self.pin_btn.setFixedSize(24, 24)
        self.pin_btn.setCheckable(True)
        self.pin_btn.setToolTip("Pin open")
        self.pin_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {t['fg4']};
                border: none;
                font-size: 12pt;
                padding: 0;
            }}
            QPushButton:checked {{ color: {t['accent']}; }}
            QPushButton:hover {{ color: {t['fg2']}; }}
        """)
        self.pin_btn.toggled.connect(self._on_pin_toggled)
        tab_bar_layout.addWidget(self.pin_btn)

        content_layout.addWidget(tab_bar)
        content_layout.addWidget(self._stack)

        self._build_chat_panel()
        self._build_memory_panel()
        self._switch_tab(0)

        main_layout.addWidget(self.handle)
        main_layout.addWidget(self.resize_grip)
        main_layout.addWidget(self.content)

    # ── Chat panel ────────────────────────────────────────────────

    def _build_chat_panel(self):
        t = self._get_theme()

        panel = QWidget(self.content)
        panel.setMouseTracking(True)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        self.chat_history = QTextBrowser(panel)
        self.chat_history.setOpenLinks(False)
        self.chat_history.setMouseTracking(True)
        self.chat_history.setStyleSheet(f"""
            QTextBrowser {{
                background-color: {t['bg0_hard']};
                color: {t['fg1']};
                border: 1px solid {t['border']};
                border-radius: 6px;
                padding: 8px;
            }}
        """)
        layout.addWidget(self.chat_history)

        input_row = QHBoxLayout()
        self.chat_input = QTextEdit(panel)
        self.chat_input.setFixedHeight(70)
        self.chat_input.setPlaceholderText("Ask QuillAI... (Ctrl+Enter)")
        self.chat_input.setMouseTracking(True)
        self.chat_input.setStyleSheet(f"""
            QTextEdit {{
                background-color: {t['bg1']};
                color: {t['fg0']};
                border: 1px solid {t['border']};
                border-radius: 6px;
                padding: 8px;
                font-family: Inter, sans-serif;
                font-size: 10pt;
            }}
            QTextEdit:focus {{ border: 1px solid {t['border_focus']}; }}
        """)

        send_btn = QPushButton("➤", panel)
        send_btn.setFixedSize(36, 70)
        send_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {t['accent']};
                color: {t['bg0_hard']};
                border: none;
                border-radius: 6px;
                font-size: 14pt;
            }}
            QPushButton:hover {{ background-color: {t['yellow']}; }}
        """)
        send_btn.clicked.connect(self._send)

        self._send_shortcut = QShortcut(
            QKeySequence("Ctrl+Return"), self.chat_input
        )
        self._send_shortcut.activated.connect(self._send)

        input_row.addWidget(self.chat_input)
        input_row.addWidget(send_btn)
        layout.addLayout(input_row)

        self._stack.addWidget(panel)

    # ── Memory panel ──────────────────────────────────────────────

    def _build_memory_panel(self):
        panel = QWidget(self.content)
        panel.setMouseTracking(True)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)
        self._memory_panel_widget = panel
        self._stack.addWidget(panel)

    def set_memory_widget(self, widget: QWidget):
        layout = self._memory_panel_widget.layout()
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
        widget.setParent(self._memory_panel_widget)
        layout.addWidget(widget)
        widget.show()

    # ── Tab switching ─────────────────────────────────────────────

    def _switch_tab(self, index: int):
        self._stack.setCurrentIndex(index)
        for i, btn in self._tab_buttons.items():
            btn.setChecked(i == index)

    def switch_to_chat(self):
        self._switch_tab(0)
        self.expand()
        self.chat_input.setFocus()

    def switch_to_memory(self):
        self._switch_tab(1)
        self.expand()

    # ── Pin ───────────────────────────────────────────────────────

    def _on_pin_toggled(self, pinned: bool):
        self._pinned = pinned
        self.pin_btn.setToolTip("Unpin panel" if pinned else "Pin panel open")
        if pinned:
            self._hover_timer.stop()
            self.expand()
        else:
            self._hover_timer.start()

    # ── Positioning ───────────────────────────────────────────────

    def _position_collapsed(self):
        if not self.parent():
            return
        parent = self.parent()
        self.setFixedHeight(parent.height())
        self.setFixedWidth(self.PANEL_WIDTH)
        self.move(parent.width() - self.HANDLE_WIDTH, 0)

    def reposition(self):
        if not self.parent():
            return
        parent = self.parent()
        if self._expanded:
            self.move(parent.width() - self.PANEL_WIDTH, self.y())
        else:
            self.move(parent.width() - self.HANDLE_WIDTH, self.y())

    # ── Animation ─────────────────────────────────────────────────

    def expand(self):
        if self._animating:
            return
        if self._expanded:
            self.arrow_label.setText("❮")
            return
        self._animating = True
        self._expanded = True
        self.raise_()
        self.arrow_label.setText("❮")

        parent = self.parent()
        h = parent.height()
        start = QRect(parent.width() - self.HANDLE_WIDTH, self.y(),
                      self.PANEL_WIDTH, h)
        end = QRect(parent.width() - self.PANEL_WIDTH, self.y(),
                    self.PANEL_WIDTH, h)

        self._anim = QPropertyAnimation(self, b"geometry")
        self._anim.setDuration(180)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.setStartValue(start)
        self._anim.setEndValue(end)
        self._anim.finished.connect(lambda: setattr(self, '_animating', False))
        self._anim.start()

    def collapse(self):
        if not self._expanded or self._animating or self._pinned:
            return
        self._animating = True
        self._expanded = False
        self.arrow_label.setText("❯")

        parent = self.parent()
        h = parent.height()
        start = QRect(parent.width() - self.PANEL_WIDTH, 0,
                      self.PANEL_WIDTH, h)
        end = QRect(parent.width() - self.HANDLE_WIDTH, 0,
                    self.PANEL_WIDTH, h)

        self._anim = QPropertyAnimation(self, b"geometry")
        self._anim.setDuration(180)
        self._anim.setEasingCurve(QEasingCurve.Type.InCubic)
        self._anim.setStartValue(start)
        self._anim.setEndValue(end)
        self._anim.finished.connect(lambda: setattr(self, '_animating', False))
        self._anim.start()

    def toggle(self):
        if self._expanded:
            self.collapse()
        else:
            self.expand()

    # ── Mouse ─────────────────────────────────────────────────────

    def enterEvent(self, event):
        if not self._hover_enabled:
            super().enterEvent(event)
            return
        self._hover_timer.stop()
        self.expand()
        super().enterEvent(event)

    def leaveEvent(self, event):
        if not self._hover_enabled:
            super().leaveEvent(event)
            return
        if not self._pinned:
            self._hover_timer.start()
        super().leaveEvent(event)

    def _check_collapse(self):
        pos = self.mapFromGlobal(QCursor.pos())
        if not self.rect().contains(pos):
            self.collapse()

    # ── Send ──────────────────────────────────────────────────────

    def _send(self):
        text = self.chat_input.toPlainText().strip()
        if not text:
            return
        self.chat_input.clear()
        self.message_sent.emit(text)