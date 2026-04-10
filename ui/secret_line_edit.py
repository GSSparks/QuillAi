"""
ui/secret_line_edit.py

QLineEdit with a clickable eye icon inside the field to toggle
password visibility. Drop-in replacement for:
    self.field = QLineEdit()
    self.field.setEchoMode(QLineEdit.EchoMode.Password)

Replace with:
    self.field = SecretLineEdit()
"""
from __future__ import annotations

from PyQt6.QtWidgets import QLineEdit, QToolButton, QSizePolicy
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QPainter, QColor, QPixmap, QPen


def _eye_icon(visible: bool, color: str) -> QIcon:
    """Draw a simple eye icon as a QIcon."""
    px = QPixmap(16, 16)
    px.fill(Qt.GlobalColor.transparent)
    p  = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color))
    pen.setWidth(1)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)

    # Eye outline (ellipse)
    p.drawEllipse(2, 5, 12, 6)
    # Pupil
    p.setBrush(QColor(color))
    p.drawEllipse(6, 6, 4, 4)

    if not visible:
        # Strike-through line
        pen2 = QPen(QColor(color))
        pen2.setWidth(2)
        p.setPen(pen2)
        p.drawLine(2, 2, 14, 14)

    p.end()
    return QIcon(px)


class SecretLineEdit(QLineEdit):
    """
    QLineEdit with an eye-icon toggle button inside the field.
    Starts in Password mode (hidden). Click eye to reveal/hide.
    """

    def __init__(self, text: str = "", placeholder: str = "",
                 parent=None):
        super().__init__(parent)
        if text:
            self.setText(text)
        if placeholder:
            self.setPlaceholderText(placeholder)
        self.setEchoMode(QLineEdit.EchoMode.Password)

        self._visible = False

        # Eye button inside the field
        self._eye_btn = QToolButton(self)
        self._eye_btn.setFixedSize(20, 20)
        self._eye_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._eye_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._eye_btn.setStyleSheet(
            "QToolButton { border: none; background: transparent; }"
        )
        self._eye_btn.clicked.connect(self._toggle_visibility)
        self._update_icon()

        # Adjust right padding so text doesn't overlap button
        self.setStyleSheet(
            "QLineEdit { padding-right: 24px; }"
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Keep eye button at right edge, vertically centered
        btn_size = self._eye_btn.sizeHint()
        frame_w  = self.style().pixelMetric(
            self.style().PixelMetric.PM_DefaultFrameWidth
        )
        self._eye_btn.move(
            self.rect().right() - frame_w - btn_size.width() - 2,
            (self.rect().bottom() - btn_size.height()) // 2 + 1,
        )

    def _toggle_visibility(self):
        self._visible = not self._visible
        self.setEchoMode(
            QLineEdit.EchoMode.Normal if self._visible
            else QLineEdit.EchoMode.Password
        )
        self._update_icon()

    def _update_icon(self):
        # Use a simple text emoji as fallback — works everywhere
        self._eye_btn.setText("👁" if self._visible else "🔒")
        self._eye_btn.setToolTip(
            "Hide" if self._visible else "Show"
        )

    def update_theme(self, t: dict):
        """Call when theme changes to update icon colors."""
        self._update_icon()