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

AI items (source="ai") are appended after LSP items with a ✦ badge
and a subtle section separator.
"""

import re
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QVBoxLayout, QListWidget, QListWidgetItem,
    QLabel, QApplication, QAbstractItemView,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent, QColor, QFont

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
    99: ("✦",  "AI",            10),  # AI completion items
}
_DEFAULT_KIND = ("·", "Text", 9)

# Sentinel kind value for section separator pseudo-items
_SEPARATOR_KIND = -1


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

    Supports mixed LSP + AI items. AI items are visually distinguished
    with a ✦ badge and appear after a section separator.
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
        self._sorted_items = []   # real items only (no separator sentinels)
        self._row_map      = []   # maps list row → index in _sorted_items, or None for separators

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
        self._list.itemClicked.connect(self._on_item_clicked)
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
        self._sorted_items = []
        self._row_map      = []
        t = get_theme()

        # Split LSP vs AI items
        lsp_items = [i for i in items if i.get("source") != "ai"]
        ai_items  = [i for i in items if i.get("source") == "ai"]

        def lsp_sort_key(item):
            _, _, priority = _kind_info(item.get("kind", 99))
            return (priority, item.get("label", "").lower())

        lsp_items = sorted(lsp_items, key=lsp_sort_key)

        # All real items in display order
        self._sorted_items = lsp_items + ai_items

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
            "AI":          t.get("aqua",    "#8ec07c"),
        }

        ai_color    = t.get("aqua",   "#8ec07c")
        sep_color   = t.get("bg3",    "#665c54")
        sep_fg      = t.get("fg4",    "#a89984")

        item_index = 0  # index into self._sorted_items

        # ── LSP items ─────────────────────────────────────────────
        for item in lsp_items:
            kind_int           = item.get("kind", 1)
            icon, kind_name, _ = _kind_info(kind_int)
            label              = item.get("label", "")
            li = QListWidgetItem(f" {icon}  {label}")
            li.setData(Qt.ItemDataRole.UserRole, item_index)
            color = kind_colors.get(kind_name, t.get("fg4", "#a89984"))
            li.setForeground(QColor(color))
            self._list.addItem(li)
            self._row_map.append(item_index)
            item_index += 1

        # ── Separator (only when both sections have items) ─────────
        if lsp_items and ai_items:
            sep = QListWidgetItem("  ✦ AI Suggestions")
            sep.setFlags(Qt.ItemFlag.NoItemFlags)   # not selectable
            sep.setForeground(QColor(sep_fg))
            sep_font = sep.font()
            sep_font.setPointSizeF(sep_font.pointSizeF() * 0.85)
            sep_font.setItalic(True)
            sep.setFont(sep_font)
            self._list.addItem(sep)
            self._row_map.append(None)  # sentinel — no real item

        # ── AI items ──────────────────────────────────────────────
        for item in ai_items:
            label = item.get("label", "")
            li = QListWidgetItem(f" ✦  {label}")
            li.setData(Qt.ItemDataRole.UserRole, item_index)
            li.setForeground(QColor(ai_color))
            # Slightly italic to visually distinguish
            f = li.font()
            f.setItalic(True)
            li.setFont(f)
            self._list.addItem(li)
            self._row_map.append(item_index)
            item_index += 1

        # ── Size the popup ────────────────────────────────────────
        if self._list.count() > 0:
            item_h   = self._list.sizeHintForRow(0) if self._list.count() > 0 else 24
            max_rows = 12
            n        = min(max(1, self._list.count()), max_rows)
            list_h   = max(item_h * 3, n * item_h)
            total_h  = list_h + 22
            popup_w  = 300

            self._list.setFixedHeight(list_h)
            self.setFixedSize(popup_w, total_h)

            # Select first real (non-separator) item
            self._select_first_real_row()

    def _select_first_real_row(self):
        for row in range(self._list.count()):
            if self._row_map[row] is not None:
                self._list.setCurrentRow(row)
                return

    def _real_item_at_row(self, row: int) -> dict | None:
        """Return the real item dict for a list row, or None for separators."""
        if row < 0 or row >= len(self._row_map):
            return None
        idx = self._row_map[row]
        if idx is None:
            return None
        return self._sorted_items[idx]

    def update_items(self, items: list):
        """
        Merge new items into the popup (used to append AI items after LSP
        results are already showing). Preserves the current selection row
        if possible.
        """
        current_row = self._list.currentRow()
        current_item = self._real_item_at_row(current_row)

        self._populate(items)

        # Try to restore selection to same label
        if current_item:
            label = current_item.get("label", "")
            for row in range(self._list.count()):
                item = self._real_item_at_row(row)
                if item and item.get("label") == label:
                    self._list.setCurrentRow(row)
                    return

        self._select_first_real_row()

    # ── Detail preview ────────────────────────────────────────────────────

    def _on_row_changed(self, row: int):
        item = self._real_item_at_row(row)
        if item is None:
            # Separator row — skip to next real item
            self._detail_label.setText("")
            self._doc_label.setText("")
            return

        detail = item.get("detail", "")
        source = item.get("source", "")
        if source == "ai":
            detail = f"✦ {detail}" if detail else "✦ AI"
        self._detail_label.setText(detail)

        doc = item.get("documentation", "")
        if isinstance(doc, dict):
            doc = doc.get("value", "")
        doc = _strip_markdown(str(doc)) if doc else ""
        doc = doc.split("\n")[0][:60] + ("…" if len(doc) > 60 else "")
        self._doc_label.setText(doc)

    def _on_item_clicked(self, li: QListWidgetItem):
        row = self._list.row(li)
        if self._real_item_at_row(row) is not None:
            self._accept()

    # ── Acceptance ────────────────────────────────────────────────────────

    def _accept(self):
        row  = self._list.currentRow()
        item = self._real_item_at_row(row)
        if item is not None:
            self.item_accepted.emit(item)
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
            self._move_selection(-1)
            return True

        if key == Qt.Key.Key_Down:
            self._move_selection(1)
            return True

        if key == Qt.Key.Key_PageUp:
            self._move_selection(-5)
            return True

        if key == Qt.Key.Key_PageDown:
            self._move_selection(5)
            return True

        # Left/Right/Home/End — dismiss, let editor handle cursor movement
        if key in (Qt.Key.Key_Left, Qt.Key.Key_Right,
                   Qt.Key.Key_Home, Qt.Key.Key_End):
            self._dismiss()
            return False

        # Everything else — let through to editor (typing, backspace, etc.)
        return False

    def _move_selection(self, delta: int):
        """Move selection by delta rows, skipping separator rows."""
        current = self._list.currentRow()
        row     = current + delta
        step    = 1 if delta > 0 else -1
        count   = self._list.count()

        # Walk in the direction of delta, skipping separators
        visited = 0
        while 0 <= row < count and visited < count:
            if self._row_map[row] is not None:
                self._list.setCurrentRow(row)
                self._list.scrollToItem(self._list.currentItem())
                return
            row  += step
            visited += 1

        # Hit a boundary — clamp to last/first real row
        if delta > 0:
            for r in range(count - 1, -1, -1):
                if self._row_map[r] is not None:
                    self._list.setCurrentRow(r)
                    self._list.scrollToItem(self._list.currentItem())
                    return
        else:
            self._select_first_real_row()

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
            y = cursor_rect.top() - self.height() - 2
        y = max(0, y)

        self.move(x, y)
        self.raise_()