"""
ui/file_system_model.py

Custom QFileSystemModel with theme-aware file/folder icons.
"""

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QDir
from PyQt6.QtGui import QFileSystemModel, QIcon, QPixmap, QPainter, QColor

from ui.theme import get_theme, theme_signals


class CustomFileSystemModel(QFileSystemModel):
    def __init__(self, theme_name: str = None):
        super().__init__()
        self._icons: dict = {}
        t = get_theme()
        self._rebuild_icons(t)
        theme_signals.theme_changed.connect(self._rebuild_icons)

    def _rebuild_icons(self, t: dict):
        self._icons = {
            "file":   self._create_icon(t.get("fg4", "#a89984"),
                                        t.get("bg0_hard", "#1d2021"), False),
            "folder": self._create_icon(t.get("yellow", "#d79921"),
                                        t.get("bg0_hard", "#1d2021"), True),
        }

    @staticmethod
    def _create_icon(color: str, bg_hard: str, is_folder: bool) -> QIcon:
        size = 16
        px   = QPixmap(size, size)
        px.fill(Qt.GlobalColor.transparent)
        painter = QPainter(px)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = QColor(color)
        painter.setBrush(c)
        painter.setPen(Qt.PenStyle.NoPen)
        if is_folder:
            painter.drawRoundedRect(1, 4, 14, 10, 2, 2)
            painter.drawRoundedRect(1, 2,  7,  4, 1, 1)
        else:
            painter.drawRoundedRect(2, 1, 10, 13, 1, 1)
            painter.setBrush(QColor(bg_hard))
            painter.drawPolygon([
                __import__("PyQt6.QtCore", fromlist=["QPoint"]).QPoint(9, 1),
                __import__("PyQt6.QtCore", fromlist=["QPoint"]).QPoint(12, 4),
                __import__("PyQt6.QtCore", fromlist=["QPoint"]).QPoint(9, 4),
            ])
        painter.end()
        return QIcon(px)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DecorationRole and index.isValid():
            if self.isDir(index):
                return self._icons.get("folder")
            return self._icons.get("file")
        return super().data(index, role)
