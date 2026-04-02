from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                              QLabel, QTextEdit, QTextBrowser, QStackedWidget)
from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QRect, pyqtSignal, QTimer
from PyQt6.QtGui import QKeySequence, QTextCursor, QShortcut, QCursor

from ui.theme import (get_theme, theme_signals,
                      build_sliding_panel_stylesheet,
                      build_sliding_panel_parts,
                      FONT_UI, FONT_CODE)


class ResizeGrip(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(5)
        self.setCursor(Qt.CursorShape.SizeHorCursor)
        self.setStyleSheet("background-color: transparent;")
        self._dragging = False
        self._drag_start_x = 0
        self._drag_start_width = 0
        self._hover_style = build_sliding_panel_parts(get_theme())["resize_grip_hover"]

    def update_hover_style(self, hover_style: str):
        self._hover_style = hover_style

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
        self.setStyleSheet(self._hover_style)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.setStyleSheet("background-color: transparent;")
        super().leaveEvent(event)


class SlidingPanel(QWidget):
    message_sent = pyqtSignal(str)

    HANDLE_WIDTH  = 18
    MIN_WIDTH     = 300
    MAX_WIDTH     = 900
    DEFAULT_WIDTH = 440

    def __init__(self, parent=None, settings_manager=None):
        super().__init__(parent)
        self.setObjectName("slidingPanel")
        self._expanded      = False
        self._animating     = False
        self._pinned        = False
        self._hover_enabled = True
        self.settings_manager = settings_manager

        self.PANEL_WIDTH = self.DEFAULT_WIDTH
        if settings_manager:
            saved = settings_manager.get("panel_width")
            if saved:
                self.PANEL_WIDTH = max(self.MIN_WIDTH, min(self.MAX_WIDTH, int(saved)))

        self._hover_timer = QTimer(self)
        self._hover_timer.setSingleShot(True)
        self._hover_timer.timeout.connect(self._check_collapse)
        self._hover_timer.setInterval(600)

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMouseTracking(True)
        self._setup_ui()
        self._position_collapsed()

        theme_signals.theme_changed.connect(self._on_theme_changed)

    # ── Theme ─────────────────────────────────────────────────────────────

    def _on_theme_changed(self, t: dict):
        self.apply_styles(t)

    def apply_styles(self, t: dict):
        p = build_sliding_panel_parts(t)
        self.setStyleSheet(build_sliding_panel_stylesheet(t))
        self.arrow_label.setStyleSheet(p["arrow_label"])
        self.content.setStyleSheet(p["content"])
        self._tab_bar.setStyleSheet(p["tab_bar"])
        self.pin_btn.setStyleSheet(p["pin_btn"])
        self.chat_history.setStyleSheet(self._chat_history_style(t))
        self.chat_input.setStyleSheet(self._chat_input_style(t))
        self._send_btn.setStyleSheet(self._send_btn_style(t))
        self.resize_grip.update_hover_style(p["resize_grip_hover"])
        for btn in self._tab_buttons.values():
            btn.setStyleSheet(p["tab_btn"])

    def _chat_history_style(self, t: dict) -> str:
        return f"""
            QTextBrowser {{
                background-color: {t['bg0']};
                color: {t['fg1']};
                border: none;
                border-bottom: 1px solid {t['border']};
                font-family: '{FONT_UI}', 'Inter', system-ui, sans-serif;
                font-size: 10.5pt;
                line-height: 1.6;
                padding: 8px 4px;
                selection-background-color: {t['accent']};
                selection-color: {t['bg0_hard']};
            }}
            QScrollBar:vertical {{
                background: {t['bg0_hard']};
                width: 8px;
                border: none;
            }}
            QScrollBar::handle:vertical {{
                background: {t['bg2']};
                border-radius: 4px;
                min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {t['bg3']};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0;
            }}
        """

    def _chat_input_style(self, t: dict) -> str:
        return f"""
            QTextEdit {{
                background-color: {t['bg0_hard']};
                color: {t['fg1']};
                border: 1px solid {t['border']};
                border-radius: 8px;
                font-family: '{FONT_UI}', 'Inter', system-ui, sans-serif;
                font-size: 10.5pt;
                padding: 8px 10px;
                selection-background-color: {t['accent']};
                selection-color: {t['bg0_hard']};
            }}
            QTextEdit:focus {{
                border-color: {t['border_focus']};
            }}
        """

    def _send_btn_style(self, t: dict) -> str:
        return f"""
            QPushButton {{
                background-color: {t['accent']};
                color: {t['bg0_hard']};
                border: none;
                border-radius: 8px;
                font-size: 13pt;
                font-weight: bold;
                padding: 0;
            }}
            QPushButton:hover {{
                background-color: {t.get('yellow', t['accent'])};
            }}
            QPushButton:pressed {{
                background-color: {t.get('orange', t['accent'])};
            }}
        """

    # ── Setup ─────────────────────────────────────────────────────────────

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

        content_layout = QVBoxLayout(self.content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # Tab bar
        self._tab_bar = QWidget(self.content)
        self._tab_bar.setFixedHeight(38)
        tab_bar_layout = QHBoxLayout(self._tab_bar)
        tab_bar_layout.setContentsMargins(8, 0, 8, 0)
        tab_bar_layout.setSpacing(4)

        self._tab_buttons = {}
        self._stack = QStackedWidget(self.content)
        self._stack.setMouseTracking(True)

        for i, (name, icon) in enumerate([("Chat", "💬"), ("Memory", "🧠")]):
            btn = QPushButton(f"{icon}  {name}")
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, idx=i: self._switch_tab(idx))
            tab_bar_layout.addWidget(btn)
            self._tab_buttons[i] = btn

        tab_bar_layout.addStretch()

        self.pin_btn = QPushButton("📌")
        self.pin_btn.setFixedSize(24, 24)
        self.pin_btn.setCheckable(True)
        self.pin_btn.setToolTip("Pin open")
        self.pin_btn.toggled.connect(self._on_pin_toggled)
        tab_bar_layout.addWidget(self.pin_btn)

        content_layout.addWidget(self._tab_bar)
        content_layout.addWidget(self._stack)

        self._build_chat_panel()
        self._build_memory_panel()
        self._switch_tab(0)

        main_layout.addWidget(self.handle)
        main_layout.addWidget(self.resize_grip)
        main_layout.addWidget(self.content)

        self.apply_styles(get_theme())

    # ── Chat panel ────────────────────────────────────────────────────────

    def _build_chat_panel(self):
        t      = get_theme()
        panel  = QWidget(self.content)
        panel.setMouseTracking(True)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # History — no margins, fills the panel
        self.chat_history = QTextBrowser(panel)
        self.chat_history.setOpenLinks(False)
        self.chat_history.setMouseTracking(True)
        self.chat_history.document().setDocumentMargin(12)
        layout.addWidget(self.chat_history, stretch=1)

        # Input area — sits below a separator
        input_container = QWidget(panel)
        input_container.setObjectName("chatInputContainer")
        input_layout = QHBoxLayout(input_container)
        input_layout.setContentsMargins(8, 8, 8, 8)
        input_layout.setSpacing(8)

        self.chat_input = QTextEdit(panel)
        self.chat_input.setFixedHeight(72)
        self.chat_input.setPlaceholderText("Ask QuillAI… (Ctrl+Enter to send)")
        self.chat_input.setMouseTracking(True)
        self.chat_input.setAcceptRichText(False)
        self.chat_input.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        self._send_btn = QPushButton("↑", panel)
        self._send_btn.setFixedSize(40, 40)
        self._send_btn.setToolTip("Send (Ctrl+Enter)")
        self._send_btn.clicked.connect(self._send)

        self._send_shortcut = QShortcut(QKeySequence("Ctrl+Return"), self.chat_input)
        self._send_shortcut.activated.connect(self._send)

        input_layout.addWidget(self.chat_input)
        input_layout.addWidget(self._send_btn, alignment=Qt.AlignmentFlag.AlignBottom)
        layout.addWidget(input_container)

        self._stack.addWidget(panel)

    # ── Memory panel ──────────────────────────────────────────────────────

    def _build_memory_panel(self):
        panel  = QWidget(self.content)
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

    # ── Tab switching ─────────────────────────────────────────────────────

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

    # ── Pin ───────────────────────────────────────────────────────────────

    def _on_pin_toggled(self, pinned: bool):
        self._pinned = pinned
        self.pin_btn.setToolTip("Unpin panel" if pinned else "Pin panel open")
        if pinned:
            self._hover_timer.stop()
            self.expand()
        else:
            self._hover_timer.start()

    # ── Positioning ───────────────────────────────────────────────────────

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

    # ── Animation ─────────────────────────────────────────────────────────

    def expand(self):
        if self._animating:
            return
        if self._expanded:
            self.arrow_label.setText("❮")
            return
        self._animating = True
        self._expanded  = True
        self.raise_()
        self.arrow_label.setText("❮")

        parent = self.parent()
        h      = parent.height()
        start  = QRect(parent.width() - self.HANDLE_WIDTH, self.y(), self.PANEL_WIDTH, h)
        end    = QRect(parent.width() - self.PANEL_WIDTH,  self.y(), self.PANEL_WIDTH, h)

        self._anim = QPropertyAnimation(self, b"geometry")
        self._anim.setDuration(180)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.setStartValue(start)
        self._anim.setEndValue(end)
        self._anim.finished.connect(lambda: setattr(self, "_animating", False))
        self._anim.start()

    def collapse(self):
        if not self._expanded or self._animating or self._pinned:
            return
        self._animating = True
        self._expanded  = False
        self.arrow_label.setText("❯")

        parent = self.parent()
        h      = parent.height()
        start  = QRect(parent.width() - self.PANEL_WIDTH,  0, self.PANEL_WIDTH, h)
        end    = QRect(parent.width() - self.HANDLE_WIDTH, 0, self.PANEL_WIDTH, h)

        self._anim = QPropertyAnimation(self, b"geometry")
        self._anim.setDuration(180)
        self._anim.setEasingCurve(QEasingCurve.Type.InCubic)
        self._anim.setStartValue(start)
        self._anim.setEndValue(end)
        self._anim.finished.connect(lambda: setattr(self, "_animating", False))
        self._anim.start()

    def toggle(self):
        if self._expanded:
            self.collapse()
        else:
            self.expand()

    # ── Mouse ─────────────────────────────────────────────────────────────

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

    # ── Send ──────────────────────────────────────────────────────────────

    def _send(self):
        text = self.chat_input.toPlainText().strip()
        if not text:
            return
        self.chat_input.clear()
        self.message_sent.emit(text)

    # ── Cleanup ───────────────────────────────────────────────────────────

    def closeEvent(self, event):
        try:
            theme_signals.theme_changed.disconnect(self._on_theme_changed)
        except RuntimeError:
            pass
        super().closeEvent(event)