"""
ui/command_palette.py
─────────────────────
Ctrl+P command palette for QuillAI.

Indexes three item types shown together in a unified fuzzy list:

  📄  Project files     — every file under the open project root
  ⬡   Open tabs         — files already open in the editor
  ⚡  Actions           — registered editor/window commands

Usage
─────
    from ui.command_palette import CommandPalette
    palette = CommandPalette(main_window)
    palette.show_palette()          # call from Ctrl+P shortcut
"""

import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLineEdit, QListWidget,
    QListWidgetItem, QApplication, QStyledItemDelegate,
    QStyleOptionViewItem, QStyle,
)
from PyQt6.QtCore import Qt, QEvent, QSize, QRect
from PyQt6.QtGui import QKeySequence, QColor, QFont, QPainter, QPen

from ui.theme import (
    get_theme, theme_signals,
    build_command_palette_stylesheet,
    build_command_palette_parts,
    QFONT_UI, QFONT_CODE,
)

# ─────────────────────────────────────────────────────────────────────────────
# Item kinds
# ─────────────────────────────────────────────────────────────────────────────

KIND_TAB    = "tab"
KIND_FILE   = "file"
KIND_ACTION = "action"

KIND_ICONS = {
    KIND_TAB:    "⬡ ",
    KIND_FILE:   "📄 ",
    KIND_ACTION: "⚡ ",
}

# Data roles stored on each QListWidgetItem
ROLE_KIND  = Qt.ItemDataRole.UserRole
ROLE_LABEL = Qt.ItemDataRole.UserRole + 1
ROLE_HINT  = Qt.ItemDataRole.UserRole + 2
ROLE_DATA  = Qt.ItemDataRole.UserRole + 3


# ─────────────────────────────────────────────────────────────────────────────
# Fuzzy matching
# ─────────────────────────────────────────────────────────────────────────────

def _fuzzy_score(query: str, text: str) -> int:
    if not query:
        return 1
    ql = query.lower()
    tl = text.lower()
    if ql in tl:
        return 1000 - tl.index(ql)
    ti = 0
    consecutive = 0
    score = 0
    for ch in ql:
        found = tl.find(ch, ti)
        if found == -1:
            return 0
        consecutive = consecutive + 1 if found == ti else 0
        score += 10 * consecutive if consecutive else 1
        ti = found + 1
    score += max(0, 100 - ti)
    return score


# ─────────────────────────────────────────────────────────────────────────────
# Custom delegate — paints icon + label + right-aligned hint in one pass,
# no nested widget layering, no background fighting.
# ─────────────────────────────────────────────────────────────────────────────

class PaletteDelegate(QStyledItemDelegate):
    def __init__(self, parts: dict, parent=None):
        super().__init__(parent)
        self._parts      = parts
        self._label_font = QFont(QFONT_UI, 10)
        self._hint_font  = QFont(QFONT_UI, 8)

    def update_parts(self, parts: dict):
        self._parts = parts

    def sizeHint(self, option, index) -> QSize:
        return QSize(option.rect.width(), 34)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        p = self._parts
        is_selected = bool(option.state & QStyle.StateFlag.State_Selected)

        # Fill background — selected or plain list bg, no item-level bg fighting
        if is_selected:
            painter.fillRect(option.rect, QColor(p["selected_bg"]))
        else:
            painter.fillRect(option.rect, option.palette.color(
                option.palette.ColorRole.Base
            ))

        rect = option.rect.adjusted(12, 0, -12, 0)

        kind  = index.data(ROLE_KIND)  or KIND_FILE
        label = index.data(ROLE_LABEL) or ""
        hint  = index.data(ROLE_HINT)  or ""
        icon  = KIND_ICONS.get(kind, "• ")

        fg_label = QColor(p["selected_fg"] if is_selected else p["label_color"])
        fg_hint  = QColor(p["hint_color"])
        fg_icon  = QColor(p["icon_color"])

        # Icon — fixed 26px wide, accent color
        icon_rect = QRect(rect.x(), rect.y(), 26, rect.height())
        painter.setFont(self._label_font)
        painter.setPen(QPen(fg_icon))
        painter.drawText(icon_rect, Qt.AlignmentFlag.AlignVCenter, icon)

        # Hint — right-aligned, measure width first so label doesn't overlap
        painter.setFont(self._hint_font)
        hint_fm = painter.fontMetrics()
        hint_w  = hint_fm.horizontalAdvance(hint) + 4
        hint_rect = QRect(rect.right() - hint_w, rect.y(), hint_w, rect.height())
        painter.setPen(QPen(fg_hint))
        painter.drawText(
            hint_rect,
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
            hint
        )

        # Label — fills the space between icon and hint
        label_rect = QRect(
            rect.x() + 26, rect.y(),
            rect.width() - 26 - hint_w - 8, rect.height()
        )
        painter.setFont(self._label_font)
        painter.setPen(QPen(fg_label))
        painter.drawText(
            label_rect,
            Qt.AlignmentFlag.AlignVCenter,
            painter.fontMetrics().elidedText(
                label, Qt.TextElideMode.ElideMiddle, label_rect.width()
            )
        )


# ─────────────────────────────────────────────────────────────────────────────
# The palette dialog
# ─────────────────────────────────────────────────────────────────────────────

class CommandPalette(QDialog):

    _ACTIONS = [
        ("Save File",               "Ctrl+S",         "save_file"),
        ("Save File As…",           "Ctrl+Shift+S",   "save_as_file"),
        ("New File",                "Ctrl+N",         "new_file"),
        ("New Project…",            "Ctrl+Shift+N",   "new_project"),
        ("Open File…",              "Ctrl+O",         "open_file_dialog"),
        ("Run Script",              "F5",             "run_script"),
        ("Find / Replace",          "Ctrl+F",         "show_find_replace"),
        ("Find in Files",           "Ctrl+Shift+F",   "show_project_search"),
        ("Open Settings",           "Ctrl+,",         "show_settings_dialog"),
        ("Toggle Terminal",         "Ctrl+`",         "toggle_terminal"),
        ("Show Explorer",           "",               "_show_explorer"),
        ("Show Source Control",     "",               "_show_git"),
        ("Show Output",             "",               "_show_output"),
        ("Show Chat",               "",               "_show_chat"),
        ("Show Memory",             "",               "_show_memory"),
        ("Show Markdown Preview",   "",               "_show_md_preview"),
        ("Toggle Inline Completion","",               "_toggle_completion"),
        ("About QuillAI",           "",               "_show_about"),
    ]

    def __init__(self, main_window):
        super().__init__(
            main_window,
            Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint
        )
        self.main_window = main_window
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setModal(False)

        self._all_items: list[dict] = []
        self._parts = build_command_palette_parts(get_theme())
        self._delegate = PaletteDelegate(self._parts, self)

        self._setup_ui()
        self.apply_styles(get_theme())
        theme_signals.theme_changed.connect(self._on_theme_changed)
        QApplication.instance().installEventFilter(self)

    # ── Theme ─────────────────────────────────────────────────────────────

    def _on_theme_changed(self, t: dict):
        self._parts = build_command_palette_parts(t)
        self._delegate.update_parts(self._parts)
        self.apply_styles(t)
        self.list_widget.viewport().update()

    def apply_styles(self, t: dict):
        self.setStyleSheet(build_command_palette_stylesheet(t))

    # ── UI setup ──────────────────────────────────────────────────────────

    def _setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Named frame carries the border — dialog itself is transparent
        from PyQt6.QtWidgets import QWidget
        self._frame = QWidget()
        self._frame.setObjectName("paletteFrame")
        self._frame.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        outer.addWidget(self._frame)

        layout = QVBoxLayout(self._frame)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search files, commands…")
        self.search_input.textChanged.connect(self._on_query_changed)
        self.search_input.installEventFilter(self)
        layout.addWidget(self.search_input)

        self.list_widget = QListWidget()
        self.list_widget.setItemDelegate(self._delegate)
        self.list_widget.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.list_widget.setUniformItemSizes(True)
        self.list_widget.itemActivated.connect(self._activate_current)
        layout.addWidget(self.list_widget)

    # ── Public API ────────────────────────────────────────────────────────

    def show_palette(self):
        self._index_items()
        self.search_input.clear()
        self._populate("")
        self._reposition()
        self.show()
        self.raise_()
        self.activateWindow()
        self.search_input.setFocus()

    # ── Indexing ──────────────────────────────────────────────────────────

    def _index_items(self):
        self._all_items = []
        mw = self.main_window

        # 1. Open tabs
        if hasattr(mw, 'tabs'):
            for i in range(mw.tabs.count()):
                editor = mw.tabs.widget(i)
                path   = getattr(editor, 'file_path', None)
                label  = mw.tabs.tabText(i).rstrip('*').strip()
                self._all_items.append({
                    "kind":   KIND_TAB,
                    "label":  label,
                    "hint":   os.path.dirname(path) if path else "",
                    "path":   path,
                    "index":  i,
                    "action": None,
                })

        # 2. Project files
        if hasattr(mw, 'file_model') and hasattr(mw, 'tree_view'):
            root = mw.file_model.filePath(mw.tree_view.rootIndex())
            if root and os.path.isdir(root):
                skip_dirs = {'__pycache__', '.git', 'node_modules',
                             'venv', '.venv', 'dist', 'build', '.mypy_cache'}
                skip_exts = {'.pyc', '.pyo', '.pyd', '.so', '.egg'}
                open_paths = {
                    getattr(mw.tabs.widget(i), 'file_path', None)
                    for i in range(mw.tabs.count())
                } if hasattr(mw, 'tabs') else set()

                for dirpath, dirnames, filenames in os.walk(root):
                    dirnames[:] = [d for d in dirnames
                                   if not d.startswith('.') and d not in skip_dirs]
                    for fname in filenames:
                        if any(fname.endswith(e) for e in skip_exts):
                            continue
                        full = os.path.join(dirpath, fname)
                        if full in open_paths:
                            continue
                        rel = os.path.relpath(full, root)
                        self._all_items.append({
                            "kind":   KIND_FILE,
                            "label":  fname,
                            "hint":   os.path.dirname(rel),
                            "path":   full,
                            "index":  None,
                            "action": None,
                        })

        # 3. Actions
        for label, hint, action_name in self._ACTIONS:
            self._all_items.append({
                "kind":   KIND_ACTION,
                "label":  label,
                "hint":   hint,
                "path":   None,
                "index":  None,
                "action": action_name,
            })

    # ── Filtering & display ───────────────────────────────────────────────

    def _on_query_changed(self, query: str):
        self._populate(query.strip())

    def _populate(self, query: str):
        self.list_widget.clear()

        scored = []
        for item in self._all_items:
            score = _fuzzy_score(query, item["label"] + " " + item["hint"])
            if score > 0:
                scored.append((score, item))

        kind_order = {KIND_TAB: 0, KIND_FILE: 1, KIND_ACTION: 2}
        scored.sort(key=lambda x: (-x[0], kind_order.get(x[1]["kind"], 9)))

        for _, item in scored[:50]:
            self._add_list_item(item)

        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)

        row_h  = 34
        header = 52
        rows   = min(len(scored), 14)
        self.setFixedHeight(header + rows * row_h)

    def _add_list_item(self, item: dict):
        hint = item["hint"]
        if len(hint) > 55:
            hint = "…" + hint[-53:]

        lw = QListWidgetItem()
        lw.setSizeHint(QSize(0, 34))
        lw.setData(ROLE_KIND,  item["kind"])
        lw.setData(ROLE_LABEL, item["label"])
        lw.setData(ROLE_HINT,  hint)
        lw.setData(ROLE_DATA,  item)
        self.list_widget.addItem(lw)

    # ── Activation ────────────────────────────────────────────────────────

    def _activate_current(self):
        row = self.list_widget.currentRow()
        if row < 0:
            return
        lw = self.list_widget.item(row)
        if not lw:
            return
        self.hide()
        self._run(lw.data(ROLE_DATA))

    def _run(self, data: dict):
        mw   = self.main_window
        kind = data["kind"]

        if kind in (KIND_TAB, KIND_FILE):
            path = data["path"]
            if kind == KIND_TAB and data["index"] is not None:
                mw.tabs.setCurrentIndex(data["index"])
            elif path and os.path.exists(path):
                mw.open_file_in_tab(path)
            return

        action = data.get("action")
        if not action:
            return

        dispatch = {
            "_show_explorer":     lambda: (mw.sidebar_dock.show(), mw.sidebar_dock.raise_()),
            "_show_git":          lambda: (mw.git_dock.show(),     mw.git_dock.raise_()),
            "_show_output":       lambda: (mw.output_dock.show(),  mw.output_dock.raise_()),
            "_show_chat":         lambda: mw.chat_panel.switch_to_chat(),
            "_show_memory":       lambda: mw.chat_panel.switch_to_memory(),
            "_show_md_preview":   lambda: (mw.md_preview_dock.show(),
                                           mw.md_preview_dock.raise_(),
                                           mw._refresh_markdown_preview()),
            "_toggle_completion": lambda: mw.toggle_inline_completion(
                not mw.inline_completion_enabled
            ),
            "_show_about":        lambda: mw._show_about(),
            "new_file":           lambda: mw.add_new_tab("Untitled", ""),
            "new_project":        lambda: mw._new_project() if hasattr(mw, '_new_project') else None,
            "open_file_dialog":   lambda: mw.show_find_replace(),
            "save_as_file":       lambda: mw.save_file(),
        }

        if action in dispatch:
            dispatch[action]()
        elif hasattr(mw, action):
            getattr(mw, action)()

    # ── Positioning ───────────────────────────────────────────────────────

    def _reposition(self):
        mw  = self.main_window
        geo = mw.geometry()
        w   = 620
        self.setFixedWidth(w)
        self.move(
            geo.x() + (geo.width() - w) // 2,
            geo.y() + mw.menuBar().height() + 40,
        )

    # ── Event filter ──────────────────────────────────────────────────────

    def eventFilter(self, obj, event):
        from PyQt6.QtCore import QEvent

        if obj == self.search_input and event.type() == QEvent.Type.KeyPress:
            key = event.key()

            if key == Qt.Key.Key_Escape:
                self.hide()
                self.main_window.activateWindow()
                return True

            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._activate_current()
                return True

            if key in (Qt.Key.Key_Down, Qt.Key.Key_Tab):
                self.list_widget.setCurrentRow(
                    min(self.list_widget.currentRow() + 1,
                        self.list_widget.count() - 1)
                )
                return True

            if key == Qt.Key.Key_Up:
                self.list_widget.setCurrentRow(
                    max(self.list_widget.currentRow() - 1, 0)
                )
                return True

        if event.type() == QEvent.Type.MouseButtonPress and self.isVisible():
            if not self.geometry().contains(event.globalPosition().toPoint()):
                self.hide()
                return False

        return super().eventFilter(obj, event)

    def closeEvent(self, event):
        try:
            theme_signals.theme_changed.disconnect(self._on_theme_changed)
        except RuntimeError:
            pass
        QApplication.instance().removeEventFilter(self)
        super().closeEvent(event)