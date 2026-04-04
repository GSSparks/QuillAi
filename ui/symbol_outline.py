"""
ui/symbol_outline.py

Symbol Outline panel for QuillAI.

Shows a tree of symbols (classes → methods, functions, variables) for the
currently active file, powered by LSP textDocument/documentSymbol.

Updates on:
  - Active tab change
  - File save
  - textChanged (debounced 1500ms)

Click a symbol → jump to that line in the editor.
"""

import os
from PyQt6.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QTreeWidget, QTreeWidgetItem, QLabel, QPushButton,
    QSizePolicy, QStyledItemDelegate,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor

from ui.theme import get_theme, theme_signals, build_symbol_outline_stylesheet


# ── LSP SymbolKind → (icon, color_key, kind_name) ────────────────────────────

_SYMBOL_KIND = {
    1:  ("T",   "fg4",    "Text"),
    2:  ("M",   "blue",   "Module"),
    3:  ("N",   "blue",   "Namespace"),
    4:  ("P",   "green",  "Package"),
    5:  ("C",   "yellow", "Class"),
    6:  ("f",   "blue",   "Method"),
    7:  ("·",   "fg1",    "Property"),
    8:  ("■",   "fg1",    "Field"),
    9:  ("f",   "blue",   "Constructor"),
    10: ("E",   "orange", "Enum"),
    11: ("I",   "aqua",   "Interface"),
    12: ("f",   "blue",   "Function"),
    13: ("$",   "fg1",    "Variable"),
    14: ("π",   "purple", "Constant"),
    15: ("S",   "green",  "String"),
    16: ("#",   "orange", "Number"),
    17: ("?",   "orange", "Boolean"),
    18: ("[]",  "orange", "Array"),
    19: ("{}",  "orange", "Object"),
    20: ("k",   "red",    "Key"),
    21: ("∅",   "fg4",    "Null"),
    22: ("e",   "orange", "EnumMember"),
    23: ("S",   "yellow", "Struct"),
    24: ("!",   "red",    "Event"),
    25: ("±",   "fg4",    "Operator"),
    26: ("T",   "aqua",   "TypeParameter"),
}
_DEFAULT_SYMBOL = ("·", "fg4", "Unknown")


def _symbol_info(kind: int):
    return _SYMBOL_KIND.get(kind, _DEFAULT_SYMBOL)


# ── Expand/collapse indicator delegate ───────────────────────────────────────

class _OutlineDelegate(QStyledItemDelegate):
    """Draws ▶/▼ expand indicators for items that have children."""

    def __init__(self, tree, parent=None):
        super().__init__(parent)
        self._tree = tree

    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        item = self._tree.itemFromIndex(index)
        if item and item.childCount() > 0:
            t   = get_theme()
            fg  = t.get("fg4", "#a89984")
            painter.save()
            painter.setPen(QColor(fg))
            indicator = "▼" if item.isExpanded() else "▶"   # ← on the item, not the tree
            rect = option.rect
            painter.drawText(
                rect.left() + 2,
                rect.top(),
                16,
                rect.height(),
                Qt.AlignmentFlag.AlignVCenter,
                indicator,
            )
            painter.restore()


# ── Dock widget ───────────────────────────────────────────────────────────────

class SymbolOutlineDock(QDockWidget):
    """
    Symbol outline panel. Wire it up in main.py:

        self.symbol_dock = SymbolOutlineDock(self)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.symbol_dock)
        self.tabifyDockWidget(self.sidebar_dock, self.symbol_dock)

    Then call:
        self.symbol_dock.set_editor(editor, lsp_manager)
    whenever the active editor changes.
    """

    def __init__(self, parent=None):
        super().__init__("Outline", parent)
        self.setObjectName("symbol_outline_dock")
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable |
            QDockWidget.DockWidgetFeature.DockWidgetMovable
        )

        self._editor      = None
        self._lsp_manager = None
        self._file_path   = None
        self._t           = get_theme()

        # Debounce — refresh 1.5s after last text change
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(1500)
        self._refresh_timer.timeout.connect(self._request_symbols)

        self._build_ui()
        self._apply_theme(self._t)
        theme_signals.theme_changed.connect(self._apply_theme)

    # ── UI ────────────────────────────────────────────────────────────────

    def _build_ui(self):
        container = QWidget()
        container.setObjectName("outlineContainer")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QWidget()
        header.setObjectName("outlineHeader")
        header.setFixedHeight(32)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(8, 0, 4, 0)
        hl.setSpacing(4)

        self._file_label = QLabel("No file")
        self._file_label.setObjectName("outlineFileLabel")
        self._file_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        hl.addWidget(self._file_label)

        self._refresh_btn = QPushButton("↻")
        self._refresh_btn.setObjectName("outlineRefreshBtn")
        self._refresh_btn.setFixedSize(22, 22)
        self._refresh_btn.setToolTip("Refresh symbols")
        self._refresh_btn.clicked.connect(self._request_symbols)
        hl.addWidget(self._refresh_btn)

        layout.addWidget(header)

        # Tree
        self._tree = QTreeWidget()
        self._tree.setObjectName("outlineTree")
        self._tree.setHeaderHidden(True)
        self._tree.setIndentation(20)
        self._tree.setAnimated(True)
        self._tree.setRootIsDecorated(False)   # we draw our own indicators
        self._tree.setItemDelegate(_OutlineDelegate(self._tree))
        self._tree.itemClicked.connect(self._on_item_clicked)
        self._tree.itemExpanded.connect(lambda _: self._tree.viewport().update())
        self._tree.itemCollapsed.connect(lambda _: self._tree.viewport().update())
        layout.addWidget(self._tree)

        self.setWidget(container)

    # ── Theme ─────────────────────────────────────────────────────────────

    def _apply_theme(self, t: dict):
        self._t = t
        self.widget().setStyleSheet(build_symbol_outline_stylesheet(t))
        if self._file_path:
            self._request_symbols()

    # ── Public API ────────────────────────────────────────────────────────

    def set_editor(self, editor, lsp_manager):
        """Call whenever the active editor changes."""
        if self._editor is not None:
            try:
                self._editor.textChanged.disconnect(self._on_text_changed)
            except RuntimeError:
                pass

        self._editor      = editor
        self._lsp_manager = lsp_manager
        self._refresh_timer.stop()

        if editor is None:
            self._file_label.setText("No file")
            self._tree.clear()
            self._file_path = None
            return

        file_path = getattr(editor, 'file_path', None)
        self._file_path = file_path
        self._file_label.setText(
            os.path.basename(file_path) if file_path else "Untitled"
        )

        editor.textChanged.connect(self._on_text_changed)
        self._request_symbols()

    def refresh_for_path(self, file_path: str):
        """Force refresh — called after save."""
        if self._file_path == file_path:
            self._request_symbols()

    # ── Symbol fetching ───────────────────────────────────────────────────

    def _on_text_changed(self):
        self._refresh_timer.start()

    def _request_symbols(self):
        if not self._editor or not self._file_path:
            self._tree.clear()
            return
        if not self._lsp_manager:
            self._tree.clear()
            return
        if not self._lsp_manager.is_supported(self._file_path):
            self._show_empty("LSP not available for this file type")
            return

        file_path = self._file_path
        self._lsp_manager.request_document_symbols(
            file_path,
            callback=lambda fp, syms: self._on_symbols(syms, file_path)
        )

    def _on_symbols(self, symbols: list, file_path: str):
        if file_path != self._file_path:
            return

        self._tree.clear()

        if not symbols:
            self._show_empty("No symbols found")
            return

        t = self._t

        # Sort by line number so parents always appear before children
        def line_of(s):
            return (s.get("location", {})
                     .get("range", {})
                     .get("start", {})
                     .get("line", 0))

        sorted_syms = sorted(symbols, key=line_of)

        top_level = []
        by_name   = {}   # symbol name → QTreeWidgetItem

        for sym in sorted_syms:
            container  = sym.get("containerName") or ""
            icon, color_key, kind_name = _symbol_info(sym.get("kind", 0))
            name       = sym.get("name", "?")
            # Leave room for the ▶/▼ indicator drawn by the delegate
            label      = f"     {icon}  {name}"

            item = QTreeWidgetItem([label])
            item.setForeground(0, QColor(t.get(color_key, t.get("fg1", "#ebdbb2"))))
            item.setToolTip(0, f"{kind_name}: {name}")

            rng   = sym.get("location", {}).get("range", {})
            start = rng.get("start", {})
            item.setData(0, Qt.ItemDataRole.UserRole,
                         (start.get("line", 0), start.get("character", 0)))

            by_name[name] = item

            if container and container in by_name:
                by_name[container].addChild(item)
            else:
                top_level.append(item)

        for item in top_level:
            self._tree.addTopLevelItem(item)

        self._tree.expandAll()

    def _show_empty(self, message: str):
        self._tree.clear()
        item = QTreeWidgetItem(self._tree, [message])
        item.setForeground(0, QColor(self._t.get("fg4", "#a89984")))
        item.setFlags(Qt.ItemFlag.NoItemFlags)

    # ── Navigation ────────────────────────────────────────────────────────

    def _on_item_clicked(self, item: QTreeWidgetItem, column: int):
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data is None or self._editor is None:
            return
        line, col = data

        from PyQt6.QtGui import QTextCursor
        doc   = self._editor.document()
        block = doc.findBlockByLineNumber(line)
        if not block.isValid():
            return

        cursor = QTextCursor(block)
        if col > 0:
            cursor.movePosition(
                QTextCursor.MoveOperation.Right,
                QTextCursor.MoveMode.MoveAnchor,
                min(col, max(0, block.length() - 1))
            )
        self._editor.setTextCursor(cursor)
        self._editor.centerCursor()
        self._editor.setFocus()