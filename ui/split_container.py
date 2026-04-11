"""
ui/split_container.py

Split editor pane support for QuillAI.

EditorPane     — a QTabWidget with an active-state indicator border
SplitContainer — a QSplitter that holds EditorPanes or nested SplitContainers

Usage:
    container = SplitContainer()
    container.pane_activated.connect(main_window._on_active_pane_changed)
    main_window.central_layout.addWidget(container)

    # Split active pane
    container.split_active(Qt.Orientation.Horizontal)   # side by side
    container.split_active(Qt.Orientation.Vertical)     # top / bottom

    # Access
    container.active_pane()         → EditorPane
    container.all_panes()           → [EditorPane, ...]
    container.all_editors()         → [(tab_index, editor), ...]
"""

from PyQt6.QtWidgets import (
    QWidget, QSplitter, QTabWidget, QVBoxLayout, QApplication, QTabBar
)
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QMimeData, QPoint, QByteArray
from PyQt6.QtGui import QColor, QDrag, QPixmap, QPainter

from ui.theme import get_theme, theme_signals, build_tab_widget_stylesheet


# -- DraggableTabBar ---------------------------------------------------------

_MIME_TAB = "application/x-quillai-tab"


class DraggableTabBar(QTabBar):
    """
    QTabBar subclass that initiates a cross-pane drag when a tab is
    dragged more than a few pixels. Drag payload: "<pane_id>:<tab_index>".
    """

    def __init__(self, pane, parent=None):
        super().__init__(parent)
        self._pane       = pane
        self._drag_start = QPoint()
        self._drag_index = -1
        self.setAcceptDrops(True)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = event.pos()
            self._drag_index = self.tabAt(event.pos())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (event.buttons() & Qt.MouseButton.LeftButton
                and self._drag_index >= 0):
            dist = (event.pos() - self._drag_start).manhattanLength()
            if dist > QApplication.startDragDistance():
                self._start_drag(self._drag_index)
                self._drag_index = -1
                return
        super().mouseMoveEvent(event)

    def _start_drag(self, index):
        payload = (str(id(self._pane)) + ":" + str(index)).encode()
        mime = QMimeData()
        mime.setData(_MIME_TAB, QByteArray(payload))
    
        tab_rect = self.tabRect(index)
        pixmap   = QPixmap(tab_rect.size())
        pixmap.fill(Qt.GlobalColor.transparent)
        painter  = QPainter(pixmap)
        painter.setOpacity(0.7)
        from PyQt6.QtGui import QRegion
        self.render(painter, QPoint(0, 0), QRegion(tab_rect))
        painter.end()
    
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.setPixmap(pixmap)
        drag.setHotSpot(self._drag_start - tab_rect.topLeft())
        drag.exec(Qt.DropAction.MoveAction)


# ── EditorPane ────────────────────────────────────────────────────────────────

class EditorPane(QWidget):
    """
    A single editor pane — a QTabWidget with an active-state
    top-border indicator and signals for tab events.
    """

    activated       = pyqtSignal(object)   # self
    tab_close_requested = pyqtSignal(object, int)   # pane, index
    current_changed = pyqtSignal(object, int)       # pane, index

    def __init__(self, parent=None):
        super().__init__(parent)
        self._active = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Active indicator — a thin accent bar at the top
        self._indicator = QWidget(self)
        self._indicator.setFixedHeight(2)
        layout.addWidget(self._indicator)

        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.tabCloseRequested.connect(
            lambda idx: self.tab_close_requested.emit(self, idx)
        )
        self.tabs.currentChanged.connect(
            lambda idx: self.current_changed.emit(self, idx)
        )
        # Clicking anywhere in the pane activates it
        self.tabs.currentChanged.connect(lambda _: self._on_focus())
        layout.addWidget(self.tabs)

        # Drag-and-drop between panes
        self._draggable_bar = DraggableTabBar(self)
        self.tabs.setTabBar(self._draggable_bar)
        self.tabs.setTabsClosable(True)
        self.setAcceptDrops(True)

        self._apply_theme(get_theme())
        theme_signals.theme_changed.connect(self._apply_theme)

    # ── Activation ────────────────────────────────────────────────────────

    def _on_focus(self):
        self.set_active(True)
        self.activated.emit(self)

    def set_active(self, active: bool):
        if self._active == active:
            return
        self._active = active
        t = get_theme()
        if active:
            self._indicator.setStyleSheet(
                f"background-color: {t.get('accent', '#fabd2f')};"
            )
        else:
            self._indicator.setStyleSheet(
                f"background-color: {t.get('bg1', '#3c3836')};"
            )

    def is_active(self) -> bool:
        return self._active

    # ── Tab widget pass-through ───────────────────────────────────────────

    def count(self) -> int:
        return self.tabs.count()

    def widget(self, index: int):
        return self.tabs.widget(index)

    def currentWidget(self):
        return self.tabs.currentWidget()

    def currentIndex(self) -> int:
        return self.tabs.currentIndex()

    def setCurrentIndex(self, index: int):
        self.tabs.setCurrentIndex(index)

    def addTab(self, widget, label: str) -> int:
        return self.tabs.addTab(widget, label)

    def removeTab(self, index: int):
        self.tabs.removeTab(index)

    def tabText(self, index: int) -> str:
        return self.tabs.tabText(index)

    def setTabText(self, index: int, text: str):
        self.tabs.setTabText(index, text)

    def indexOf(self, widget) -> int:
        return self.tabs.indexOf(widget)

    def setStyleSheet(self, style: str):
        self.tabs.setStyleSheet(style)

    # -- Drag-and-drop --------------------------------------------------------

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(_MIME_TAB):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(_MIME_TAB):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        if not event.mimeData().hasFormat(_MIME_TAB):
            event.ignore()
            return

        payload = bytes(event.mimeData().data(_MIME_TAB)).decode()
        try:
            parts       = payload.split(":")
            src_pane_id = int(parts[0])
            src_idx     = int(parts[1])
        except (ValueError, IndexError):
            event.ignore()
            return

        container = self._find_split_container()
        if container is None:
            event.ignore()
            return

        src_pane = None
        for pane in container.all_panes():
            if id(pane) == src_pane_id:
                src_pane = pane
                break

        if src_pane is None or src_pane is self:
            event.ignore()
            return

        drop_pos = event.position().toPoint()
        dst_idx  = self._tab_index_at(drop_pos)
        container._move_tab(src_pane, src_idx, self, dst_idx)
        event.acceptProposedAction()

    def _tab_index_at(self, pos):
        bar = self.tabs.tabBar()
        for i in range(bar.count()):
            if bar.tabRect(i).contains(pos):
                return i
        return self.tabs.count()

    def _find_split_container(self):
        w = self.parent()
        while w is not None:
            if isinstance(w, SplitContainer):
                return w
            w = w.parent() if hasattr(w, 'parent') else None
        return None

    # ── Theme ─────────────────────────────────────────────────────────────

    def _apply_theme(self, t: dict):
        self.tabs.setStyleSheet(build_tab_widget_stylesheet(t))
        bg = t.get('bg1', '#3c3836')
        accent = t.get('accent', '#fabd2f')
        if self._active:
            self._indicator.setStyleSheet(f"background-color: {accent};")
        else:
            self._indicator.setStyleSheet(f"background-color: {bg};")


# ── SplitContainer ────────────────────────────────────────────────────────────

class SplitContainer(QWidget):
    """
    Manages a tree of EditorPanes separated by QSplitters.
    Exactly one pane is "active" at any time.
    """

    pane_activated  = pyqtSignal(object)   # EditorPane
    tab_close_requested = pyqtSignal(object, int)   # pane, index
    current_changed = pyqtSignal(object, int)       # pane, index

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Root splitter — horizontal by default (will be replaced on first split)
        self._splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self._splitter.setHandleWidth(3)
        layout.addWidget(self._splitter)

        # Create the initial single pane
        self._active_pane: EditorPane = None
        first_pane = self._make_pane()
        self._splitter.addWidget(first_pane)
        self._set_active(first_pane)

        theme_signals.theme_changed.connect(self._on_theme)

    # ── Public API ────────────────────────────────────────────────────────

    def active_pane(self) -> EditorPane:
        return self._active_pane

    def all_panes(self) -> list:
        return self._collect_panes(self._splitter)

    def all_editors(self) -> list:
        """Return [(tab_index, editor), ...] across all panes."""
        result = []
        for pane in self.all_panes():
            for i in range(pane.count()):
                editor = pane.widget(i)
                if editor and hasattr(editor, "toPlainText"):
                    result.append((i, editor))
        return result

    def split_active(self, orientation: Qt.Orientation):
        """Split the active pane in the given orientation."""
        pane = self._active_pane
        if pane is None:
            return

        parent_splitter = self._find_parent_splitter(pane)
        if parent_splitter is None:
            return

        idx = parent_splitter.indexOf(pane)

        if parent_splitter.orientation() == orientation:
            # Same orientation — just insert a new pane next to the active one
            new_pane = self._make_pane()
            parent_splitter.insertWidget(idx + 1, new_pane)
            # Distribute space evenly
            sizes = parent_splitter.sizes()
            total = sum(sizes)
            equal = total // len(sizes)
            parent_splitter.setSizes([equal] * len(sizes))
        else:
            # Different orientation — wrap active pane in a new splitter
            new_splitter = QSplitter(orientation)
            new_splitter.setHandleWidth(3)

            # Replace pane with new_splitter in parent
            # QSplitter doesn't have replaceWidget in older Qt — use insertWidget + hide trick
            pane.setParent(None)
            parent_splitter.insertWidget(idx, new_splitter)

            new_pane = self._make_pane()
            new_splitter.addWidget(pane)
            new_splitter.addWidget(new_pane)
            new_splitter.setSizes([500, 500])

            self._style_splitter(new_splitter)

        self._set_active(self._active_pane)   # re-assert active styling

    def close_pane(self, pane: EditorPane):
        """Remove a pane. Collapses splitter if only one child remains."""
        if len(self.all_panes()) <= 1:
            return   # never close the last pane

        parent_splitter = self._find_parent_splitter(pane)
        if parent_splitter is None:
            return

        pane.setParent(None)
        pane.deleteLater()

        # If the parent splitter now has only one child, collapse it
        if parent_splitter.count() == 1:
            surviving = parent_splitter.widget(0)
            grandparent = self._find_parent_splitter_of_splitter(parent_splitter)
            if grandparent:
                idx = grandparent.indexOf(parent_splitter)
                surviving.setParent(None)
                grandparent.insertWidget(idx, surviving)
                parent_splitter.setParent(None)
                parent_splitter.deleteLater()
            # else: parent_splitter is the root — leave it

        # Activate the first remaining pane
        remaining = self.all_panes()
        if remaining:
            self._set_active(remaining[-1])

    # -- Tab move (cross-pane drag result) ------------------------------------

    def _move_tab(self, src_pane, src_idx, dst_pane, dst_idx):
        """
        Move a tab from src_pane[src_idx] to dst_pane at dst_idx.
        Activates destination pane, collapses source if empty.
        """
        if src_pane is dst_pane:
            return

        editor = src_pane.widget(src_idx)
        title  = src_pane.tabText(src_idx)
        if editor is None:
            return

        src_pane.tabs.removeTab(src_idx)

        if dst_idx < 0 or dst_idx >= dst_pane.tabs.count():
            new_idx = dst_pane.tabs.addTab(editor, title)
        else:
            new_idx = dst_pane.tabs.insertTab(dst_idx, editor, title)

        self._set_active(dst_pane)
        dst_pane.tabs.setCurrentIndex(new_idx)
        editor.setFocus()

        if src_pane.count() == 0 and len(self.all_panes()) > 1:
            self.close_pane(src_pane)

        self.pane_activated.emit(dst_pane)

    # ── Internals ─────────────────────────────────────────────────────────

    def _make_pane(self) -> EditorPane:
        pane = EditorPane(self)
        pane.activated.connect(self._set_active)
        pane.tab_close_requested.connect(
            lambda p, idx: self.tab_close_requested.emit(p, idx)
        )
        pane.current_changed.connect(
            lambda p, idx: self.current_changed.emit(p, idx)
        )
        # Activate when an editor inside gets focus
        pane.tabs.currentChanged.connect(lambda _: self._set_active(pane))
        return pane

    def _set_active(self, pane: EditorPane):
        if self._active_pane and self._active_pane is not pane:
            self._active_pane.set_active(False)
        self._active_pane = pane
        pane.set_active(True)
        self.pane_activated.emit(pane)

    def _collect_panes(self, splitter: QSplitter) -> list:
        panes = []
        for i in range(splitter.count()):
            w = splitter.widget(i)
            if isinstance(w, EditorPane):
                panes.append(w)
            elif isinstance(w, QSplitter):
                panes.extend(self._collect_panes(w))
        return panes

    def _find_parent_splitter(self, pane: EditorPane):
        """Find the QSplitter that directly contains this pane."""
        return self._find_parent_splitter_of_widget(pane, self._splitter)

    def _find_parent_splitter_of_widget(self, target, splitter: QSplitter):
        for i in range(splitter.count()):
            w = splitter.widget(i)
            if w is target:
                return splitter
            if isinstance(w, QSplitter):
                result = self._find_parent_splitter_of_widget(target, w)
                if result:
                    return result
        return None

    def _find_parent_splitter_of_splitter(self, target: QSplitter):
        return self._find_parent_splitter_of_widget(target, self._splitter)

    def _style_splitter(self, splitter: QSplitter):
        t = get_theme()
        splitter.setStyleSheet(
            f"QSplitter::handle {{ background: {t.get('border', '#3c3836')}; }}"
        )

    def _on_theme(self, t: dict):
        self._style_all_splitters(self._splitter, t)

    def _style_all_splitters(self, splitter: QSplitter, t: dict):
        splitter.setStyleSheet(
            f"QSplitter::handle {{ background: {t.get('border', '#3c3836')}; }}"
        )
        for i in range(splitter.count()):
            w = splitter.widget(i)
            if isinstance(w, QSplitter):
                self._style_all_splitters(w, t)