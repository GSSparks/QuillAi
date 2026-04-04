"""
ui/completion_popup.py

LSP-powered completion dropdown for QuillAI.

Implemented as a child widget of the editor viewport — no separate window,
no focus stealing, no window manager involvement. Positioned absolutely
over the editor content.

Keyboard routing is handled entirely in ghost_editor.py keyPressEvent —
the popup never receives focus directly.

Two-panel layout:
  Left  — scrollable list of completion items with kind icons
  Right — docstring / detail preview panel
"""

import re
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QVBoxLayout, QListWidget, QListWidgetItem,
    QLabel, QApplication, QAbstractItemView,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent, QColor

from ui.theme import get_theme, theme_signals, FONT_UI, FONT_CODE, build_completion_popup_stylesheet


# ── LSP CompletionItemKind → (icon, label, sort_priority) ────────────────────

_KIND_ASCII = {
    1:  ("T",  "Text",          9),
    2:  ("f",  "Method",        1),
    3:  ("f",  "Function",      1),
    4:  ("f",  "Constructor",   1),
    5:  ("■",  "Field",         4),
    6:  ("$",  "Variable",      5),
    7:  ("C",  "Class",         0),
    8:  ("I",  "Interface",     0),
    9:  ("M",  "Module",        2),
    10: ("·",  "Property",      4),
    11: ("u",  "Unit",          8),
    12: ("=",  "Value",         8),
    13: ("E",  "Enum",          3),
    14: ("k",  "Keyword",       6),
    15: ("~",  "Snippet",       7),
    16: ("o",  "Color",         9),
    17: ("F",  "File",          9),
    18: ("->", "Reference",     8),
    19: ("D",  "Folder",        9),
    20: ("e",  "EnumMember",    3),
    21: ("π",  "Constant",      5),
    22: ("S",  "Struct",        0),
    23: ("!",  "Event",         7),
    24: ("±",  "Operator",      6),
    25: ("T",  "TypeParameter", 3),
}
_DEFAULT_KIND = ("·", "Text", 9)


def _kind_info(kind_int: int):
    return _KIND_ASCII.get(kind_int, _DEFAULT_KIND)


def _strip_markdown(text: str) -> str:
    text = re.sub(r'```[a-z]*\n?', '', text)
    text = re.sub(r'`([^`]+)`', r'\1', text)
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    text = re.sub(r'\*([^*]+)\*', r'\1', text)
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    return text.strip()


# ── Popup ─────────────────────────────────────────────────────────────────────

class CompletionPopup(QFrame):
    """
    Completion dropdown rendered as a child of the editor viewport.
    Never steals focus. All keyboard input is routed here from
    GhostEditor.keyPressEvent().
    """

    item_accepted = pyqtSignal(dict)

    _instance = None

    @classmethod
    def close_current(cls):
        if cls._instance is not None:
            try:
                cls._instance._dismiss()
            except RuntimeError:
                cls._instance = None

    # ── Construction ──────────────────────────────────────────────────────

    def __init__(self, editor, items: list):
        # Parent to the editor's VIEWPORT — positions in viewport coords
        super().__init__(editor.viewport())
        self.setObjectName("CompletionPopup")

        # Never take focus
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        CompletionPopup._instance = self
        self._editor       = editor
        self._sorted_items = []

        t = get_theme()
        self._build_ui(t)
        self._populate(items)
        theme_signals.theme_changed.connect(self._on_theme)

    def _build_ui(self, t: dict):
        self.setStyleSheet(build_completion_popup_stylesheet(t))
    
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
    
        # ── Item list ─────────────────────────────────────────────
        self._list = QListWidget()
        self._list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._list.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list.setVerticalScrollMode(
            QAbstractItemView.ScrollMode.ScrollPerItem)
        self._list.currentRowChanged.connect(self._on_row_changed)
        self._list.itemClicked.connect(lambda _: self._accept())
        outer.addWidget(self._list)
    
        # ── Detail bar ────────────────────────────────────────────
        detail_bar = QFrame()
        detail_bar.setObjectName("detailBar")
        detail_bar.setFixedHeight(22)
        detail_layout = QHBoxLayout(detail_bar)
        detail_layout.setContentsMargins(8, 3, 8, 3)
    
        self._detail_label = QLabel()
        self._detail_label.setObjectName("detailLabel")
        self._detail_label.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        detail_layout.addWidget(self._detail_label)
        detail_layout.addStretch()
    
        self._doc_label = QLabel()
        self._doc_label.setObjectName("docLabel")
        self._doc_label.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        detail_layout.addWidget(self._doc_label)
    
        outer.addWidget(detail_bar)
        
    def _on_theme(self, t: dict):
        self.setStyleSheet(build_completion_popup_stylesheet(t))
        self._populate(list(self._sorted_items))
            
    # ── Population ────────────────────────────────────────────────────────

    def _populate(self, items: list):
        self._list.clear()
        t = get_theme()
    
        def sort_key(item):
            _, _, priority = _kind_info(item.get("kind", 99))
            return (priority, item.get("label", "").lower())
    
        self._sorted_items = sorted(items, key=sort_key)
    
        kind_colors = {
            "Class":       t.get("yellow",  "#fabd2f"),
            "Function":    t.get("blue",    "#83a598"),
            "Method":      t.get("blue",    "#83a598"),
            "Constructor": t.get("blue",    "#83a598"),
            "Keyword":     t.get("red",     "#fb4934"),
            "Module":      t.get("green",   "#b8bb26"),
            "Constant":    t.get("purple",  "#d3869b"),
            "Enum":        t.get("orange",  "#fe8019"),
            "EnumMember":  t.get("orange",  "#fe8019"),
            "Snippet":     t.get("aqua",    "#8ec07c"),
        }
    
        for item in self._sorted_items:
            kind_int           = item.get("kind", 1)
            icon, kind_name, _ = _kind_info(kind_int)
            label              = item.get("label", "")
            li = QListWidgetItem(f" {icon}  {label}")
            li.setData(Qt.ItemDataRole.UserRole, item)
            color = kind_colors.get(kind_name, t.get("fg4", "#a89984"))
            li.setForeground(QColor(color))
            self._list.addItem(li)
    
        if self._list.count() > 0:
            self._list.setCurrentRow(0)
            
            item_h = self._list.sizeHintForRow(0) if self._list.count() > 0 else 24
            max_items = 10
            n       = min(max(1, len(self._sorted_items)), max_items)
            list_h  = max(item_h * 3, n * item_h)   # minimum 3 rows
            total_h = list_h + 22
            popup_w = 280
            
            self._list.setFixedHeight(list_h)
            self.setFixedSize(popup_w, total_h)
            
    def update_items(self, items: list):
        self._populate(items)

    # ── Detail preview ────────────────────────────────────────────────────

    def _on_row_changed(self, row: int):
        if row < 0 or row >= len(self._sorted_items):
            self._detail_label.setText("")
            self._doc_label.setText("")
            return
        item   = self._sorted_items[row]
        detail = item.get("detail", "")
        self._detail_label.setText(detail)
    
        doc = item.get("documentation", "")
        if isinstance(doc, dict):
            doc = doc.get("value", "")
        doc = _strip_markdown(str(doc)) if doc else ""
        # Single line truncated for the strip
        doc = doc.split("\n")[0][:60] + ("…" if len(doc) > 60 else "")
        self._doc_label.setText(doc)

    # ── Acceptance ────────────────────────────────────────────────────────

    def _accept(self):
        row = self._list.currentRow()
        if 0 <= row < len(self._sorted_items):
            self.item_accepted.emit(self._sorted_items[row])
        self._dismiss()

    def _dismiss(self):
        if CompletionPopup._instance is self:
            CompletionPopup._instance = None
        try:
            self.hide()
            self.deleteLater()
        except RuntimeError:
            pass

    # ── Keyboard handling ─────────────────────────────────────────────────

    def handle_key(self, event: QKeyEvent) -> bool:
        """
        Called from GhostEditor.keyPressEvent BEFORE normal processing.
        Returns True if the key was consumed (editor should not process it).
        """
        key = event.key()

        if key == Qt.Key.Key_Escape:
            self._dismiss()
            return True

        if key in (Qt.Key.Key_Tab, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._accept()
            return True

        if key == Qt.Key.Key_Up:
            row = self._list.currentRow()
            if row > 0:
                self._list.setCurrentRow(row - 1)
                self._list.scrollToItem(self._list.currentItem())
            return True

        if key == Qt.Key.Key_Down:
            row = self._list.currentRow()
            if row < self._list.count() - 1:
                self._list.setCurrentRow(row + 1)
                self._list.scrollToItem(self._list.currentItem())
            return True

        if key == Qt.Key.Key_PageUp:
            row = max(0, self._list.currentRow() - 5)
            self._list.setCurrentRow(row)
            self._list.scrollToItem(self._list.currentItem())
            return True

        if key == Qt.Key.Key_PageDown:
            row = min(self._list.count() - 1, self._list.currentRow() + 5)
            self._list.setCurrentRow(row)
            self._list.scrollToItem(self._list.currentItem())
            return True

        # Left/Right/Home/End — dismiss, let editor handle cursor movement
        if key in (Qt.Key.Key_Left, Qt.Key.Key_Right,
                   Qt.Key.Key_Home, Qt.Key.Key_End):
            self._dismiss()
            return False

        # Everything else — let through to editor (typing, backspace, etc.)
        return False

    # ── Positioning ───────────────────────────────────────────────────────

    def position_at_cursor(self):
        """
        Position below the cursor in viewport coordinates.
        Since we are a child of the viewport, move() uses viewport coords.
        """
        editor      = self._editor
        cursor_rect = editor.cursorRect()
        vp          = editor.viewport()

        x = cursor_rect.left()
        y = cursor_rect.bottom() + 2

        # Keep within viewport
        if x + self.width() > vp.width():
            x = max(0, vp.width() - self.width())
        if y + self.height() > vp.height():
            # Flip above cursor
            y = cursor_rect.top() - self.height() - 2
        y = max(0, y)

        self.move(x, y)
        self.raise_()   # ensure on top of other viewport children

    # ── Theme ─────────────────────────────────────────────────────────────

    def _on_theme(self, t: dict):
        items = list(self._sorted_items)
        self._build_ui(t)
        self._populate(items)