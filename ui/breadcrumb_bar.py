import os
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QPushButton, QLabel, QSizePolicy,
    QFrame, QVBoxLayout, QLineEdit, QListWidget, QListWidgetItem,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QKeyEvent
from ui.theme import get_theme, FONT_UI


# LSP SymbolKind → (emoji, sort_priority)
_KIND_MAP = {
    1:  ("📦", 3),   # File
    2:  ("🗂",  2),   # Module
    3:  ("🗂",  2),   # Namespace
    4:  ("📦", 3),   # Package
    5:  ("🏛",  0),   # Class
    6:  ("🔧", 1),   # Method
    7:  ("📌", 4),   # Property
    8:  ("📌", 4),   # Field
    9:  ("🔨", 3),   # Constructor
    10: ("⚙️",  2),   # Enum
    11: ("🔌", 2),   # Interface
    12: ("🔧", 1),   # Function
    13: ("📎", 4),   # Variable
    14: ("🔒", 4),   # Constant
    15: ("✏️",  4),   # String
    16: ("🔢", 4),   # Number
    23: ("🏛",  0),   # Struct
    25: ("⚙️",  2),   # EnumMember
}
_DEFAULT_KIND = ("◆",  5)


def _kind_info(symbol: dict):
    return _KIND_MAP.get(symbol.get("kind", 0), _DEFAULT_KIND)


def _build_breadcrumb_stylesheet(t: dict) -> str:
    bg        = t.get("bg1",    "#3c3836")
    fg        = t.get("fg4",    "#a89984")
    fg_active = t.get("fg1",    "#ebdbb2")
    border    = t.get("border", "#3c3836")
    return f"""
        QWidget#BreadcrumbBar {{
            background-color: {bg};
            border-bottom: 1px solid {border};
        }}
        QPushButton {{
            background: transparent;
            color: {fg};
            border: none;
            padding: 2px 4px;
            font-family: '{FONT_UI}', system-ui, sans-serif;
            font-size: 8.5pt;
        }}
        QPushButton:hover {{
            color: {fg_active};
        }}
        QPushButton[active=true] {{
            color: {fg_active};
        }}
        QLabel {{
            color: {fg};
            font-size: 8.5pt;
            padding: 0 1px;
            font-family: '{FONT_UI}', system-ui, sans-serif;
        }}
    """


def _build_picker_stylesheet(t: dict) -> str:
    bg     = t.get("bg1",    "#3c3836")
    bg2    = t.get("bg2",    "#504945")
    bg3    = t.get("bg3",    "#665c54")
    fg     = t.get("fg1",    "#ebdbb2")
    fg_dim = t.get("fg4",    "#a89984")
    border = t.get("border", "#504945")
    accent = t.get("accent", "#fabd2f")
    return f"""
        QFrame#SymbolPicker {{
            background-color: {bg};
            border: 1px solid {border};
        }}
        QLineEdit {{
            background-color: {bg2};
            color: {fg};
            border: none;
            border-bottom: 1px solid {border};
            padding: 4px 8px;
            font-family: '{FONT_UI}', system-ui, sans-serif;
            font-size: 9pt;
        }}
        QListWidget {{
            background-color: {bg};
            color: {fg};
            border: none;
            font-family: '{FONT_UI}', system-ui, sans-serif;
            font-size: 9pt;
            outline: none;
        }}
        QListWidget::item {{
            padding: 3px 8px;
            color: {fg};
        }}
        QListWidget::item:selected {{
            background-color: {bg3};
            color: {fg};
        }}
        QListWidget::item:hover {{
            background-color: {bg2};
        }}
        QScrollBar:vertical {{
            background: {bg};
            width: 6px;
        }}
        QScrollBar::handle:vertical {{
            background: {bg3};
            border-radius: 3px;
        }}
    """


class SymbolPickerPopup(QFrame):
    """Searchable symbol picker that drops down from a breadcrumb button."""

    def __init__(self, symbols: list, callback, parent=None):
        super().__init__(parent, Qt.WindowType.Popup)
        self.setObjectName("SymbolPicker")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self._callback = callback
        self._all_symbols = _sort_symbols(symbols)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Filter symbols...")
        self._search.textChanged.connect(self._filter)
        layout.addWidget(self._search)

        self._list = QListWidget()
        self._list.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list.itemActivated.connect(self._on_activated)
        layout.addWidget(self._list)

        self._populate(self._all_symbols)
        self.setStyleSheet(_build_picker_stylesheet(get_theme()))

        # Size: fixed width, up to 300px tall
        self.setFixedWidth(260)
        count = min(len(self._all_symbols), 12)
        item_h = 24
        self.setFixedHeight(32 + max(count, 3) * item_h)

        self._search.installEventFilter(self)

    def _populate(self, symbols: list):
        self._list.clear()
        for sym in symbols:
            icon, _ = _kind_info(sym)
            name    = sym.get("name", "?")
            item    = QListWidgetItem(f"  {icon}  {name}")
            item.setData(Qt.ItemDataRole.UserRole, sym)
            self._list.addItem(item)
        if self._list.count():
            self._list.setCurrentRow(0)

    def _filter(self, text: str):
        q = text.lower()
        filtered = [s for s in self._all_symbols
                    if q in s.get("name", "").lower()]
        self._populate(filtered)

    def _on_activated(self, item: QListWidgetItem):
        sym = item.data(Qt.ItemDataRole.UserRole)
        self.hide()
        if sym:
            self._callback(sym)

    def eventFilter(self, obj, event):
        if obj == self._search and isinstance(event, QKeyEvent):
            if event.key() == Qt.Key.Key_Down:
                self._list.setFocus()
                if self._list.count():
                    self._list.setCurrentRow(0)
                return True
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                item = self._list.currentItem()
                if item:
                    self._on_activated(item)
                return True
            if event.key() == Qt.Key.Key_Escape:
                self.hide()
                return True
        if obj == self._list and isinstance(event, QKeyEvent):
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                item = self._list.currentItem()
                if item:
                    self._on_activated(item)
                return True
            if event.key() == Qt.Key.Key_Escape:
                self.hide()
                return True
        return super().eventFilter(obj, event)

    def showEvent(self, event):
        super().showEvent(event)
        self._search.setFocus()
        self._list.installEventFilter(self)


def _sort_symbols(symbols: list) -> list:
    """Sort by kind priority first, then alphabetically."""
    return sorted(symbols, key=lambda s: (_kind_info(s)[1], s.get("name", "").lower()))


class BreadcrumbBar(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("BreadcrumbBar")
        self.setFixedHeight(24)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(8, 0, 8, 0)
        self._layout.setSpacing(0)
        self._layout.addStretch()

        self._symbols    = []
        self._crumb_path = []
        self._file_path  = ""

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(300)

        self.apply_theme()

    # ── Public API ────────────────────────────────────────────────────────

    def set_lsp_manager(self, lsp_manager):
        self._lsp = lsp_manager

    def connect_editor(self, editor):
        try:
            editor.cursorPositionChanged.connect(self._on_cursor_moved)
        except Exception:
            pass
        self._editor = editor
        self._request_symbols()

    def apply_theme(self):
        self.setStyleSheet(_build_breadcrumb_stylesheet(get_theme()))

    # ── Internals ─────────────────────────────────────────────────────────

    def _on_cursor_moved(self):
        self._debounce.stop()
        try:
            self._debounce.timeout.disconnect()
        except Exception:
            pass
        self._debounce.timeout.connect(self._request_symbols)
        self._debounce.start()

    def _request_symbols(self):
        editor = getattr(self, "_editor", None)
        lsp    = getattr(self, "_lsp",    None)
        if not editor or not lsp:
            # Still render filename even without LSP
            fp = getattr(editor, "file_path", None) if editor else None
            self._render(fp or "", [])
            return
        file_path = getattr(editor, "file_path", None)
        if not file_path:
            self._render("", [])
            return
        lsp.request_document_symbols(file_path, self._on_symbols_received)

    def _on_symbols_received(self, file_path: str, symbols: list):
        editor = getattr(self, "_editor", None)
        if not editor:
            return
        self._file_path = file_path
        self._symbols   = symbols
        line  = editor.textCursor().blockNumber()   # 0-based
        path  = _find_symbol_path(symbols, line)
        self._crumb_path = path
        self._render(file_path, path)

    def _render(self, file_path: str, path: list):
        while self._layout.count():
            item = self._layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        fname    = os.path.basename(file_path) if file_path else "Untitled"
        file_btn = QPushButton(fname)
        file_btn.setProperty("active", len(path) == 0)
        # File crumb opens top-level symbol picker
        file_btn.clicked.connect(
            lambda: self._open_picker(self._symbols, file_btn)
        )
        self._layout.addWidget(file_btn)

        for i, symbol in enumerate(path):
            sep = QLabel("›")
            self._layout.addWidget(sep)

            is_last      = (i == len(path) - 1)
            icon, _      = _kind_info(symbol)
            btn          = QPushButton(f"{icon} {symbol['name']}")
            btn.setProperty("active", is_last)

            captured_i = i
            btn.clicked.connect(
                lambda checked, idx=captured_i, b=btn:
                    self._open_picker(
                        _get_siblings_at_depth(self._symbols, idx),
                        b
                    )
            )
            self._layout.addWidget(btn)

        self._layout.addStretch()

    def _open_picker(self, symbols: list, button: QPushButton):
        if not symbols:
            return
        picker = SymbolPickerPopup(
            symbols,
            callback=self._jump_to_symbol,
            parent=self.window(),
        )
        global_pos = button.mapToGlobal(button.rect().bottomLeft())
    
        # Nudge left if it would clip off screen right edge
        from PyQt6.QtWidgets import QApplication
        screen = QApplication.screenAt(global_pos)
        if screen:
            sr = screen.availableGeometry()
            if global_pos.x() + picker.width() > sr.right():
                global_pos.setX(sr.right() - picker.width())
    
        picker.move(global_pos)
        picker.show()
        picker.raise_()
    
    def _jump_to_symbol(self, symbol: dict):
        editor = getattr(self, "_editor", None)
        if not editor:
            return

        # DocumentSymbol uses 'range'; SymbolInformation uses 'location.range'
        r = (symbol.get("range")
             or symbol.get("location", {}).get("range")
             or {})
        line = r.get("start", {}).get("line", 0)

        block = editor.document().findBlockByLineNumber(line)
        if not block.isValid():
            return
        cursor = editor.textCursor()
        cursor.setPosition(block.position())
        editor.setTextCursor(cursor)
        editor.centerCursor()
        editor.setFocus()


# ── Symbol tree helpers ───────────────────────────────────────────────────────

def _find_symbol_path(symbols: list, line: int) -> list:
    path = []
    _walk(symbols, line, path)
    return path


def _walk(symbols: list, line: int, path: list) -> bool:
    for sym in symbols:
        r     = sym.get("range", sym.get("location", {}).get("range", {}))
        start = r.get("start", {}).get("line", -1)
        end   = r.get("end",   {}).get("line", -1)
        if start <= line <= end:
            path.append(sym)
            children = sym.get("children", [])
            if children:
                _walk(children, line, path)
            return True
    return False


def _get_siblings_at_depth(symbols: list, depth: int) -> list:
    if depth == 0:
        return symbols
    def _find_at_depth(syms, current_depth, target):
        if current_depth == target:
            return syms
        for sym in syms:
            children = sym.get("children", [])
            if children:
                result = _find_at_depth(children, current_depth + 1, target)
                if result is not None:
                    return result
        return None
    return _find_at_depth(symbols, 0, depth) or []