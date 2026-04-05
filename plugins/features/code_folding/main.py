"""
plugins/features/code_folding/main.py

Code folding plugin for QuillAI.
Patches the active editor's LineNumberArea to add fold markers.
"""

from PyQt6.QtCore import Qt, QTimer
from core.plugin_base import FeaturePlugin
from core.events import EVT_FILE_OPENED, EVT_FILE_SAVED
from plugins.features.code_folding.fold_manager import FoldManager
from plugins.features.code_folding.fold_gutter import (
    paint_fold_gutter, fold_line_at_y, FOLD_GUTTER_WIDTH
)


class CodeFoldingPlugin(FeaturePlugin):
    name = "code_folding"
    description = "Indent and brace-based code folding with painted gutter markers"
    enabled = True

    def activate(self):
        self._managers: dict = {}   # editor id → FoldManager
        self._refresh_timer = QTimer(self.app)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(800)
        self._refresh_timer.timeout.connect(self._refresh_current)

        self.on(EVT_FILE_OPENED, self._on_file_opened)
        self.on(EVT_FILE_SAVED,  self._on_file_saved)

    # ── Event handlers ────────────────────────────────────────────────────

    def _on_file_opened(self, path=None, editor=None, **kwargs):
        if editor is None:
            editor = self.app.current_editor()
        if editor:
            self._install(editor)

    def _on_file_saved(self, path=None, **kwargs):
        editor = self.app.current_editor()
        if editor:
            self._refresh(editor)

    # ── Install / refresh ─────────────────────────────────────────────────

    def _install(self, editor):
        """Patch the editor's LineNumberArea to add fold gutter support."""
        eid = id(editor)
        if eid in self._managers:
            self._refresh(editor)
            return

        fm = FoldManager()
        self._managers[eid] = fm

        # Widen the gutter
        _patch_gutter_width(editor)

        # Patch paint event
        _patch_paint_event(editor, fm)

        # Patch click event
        _patch_click_event(editor, fm)

        # Refresh regions on text change (debounced)
        editor.textChanged.connect(
            lambda e=editor: self._on_text_changed(e)
        )

        # Initial parse
        self._refresh(editor)

    def _refresh(self, editor):
        eid = id(editor)
        fm  = self._managers.get(eid)
        if fm is None:
            return
        fp = getattr(editor, 'file_path', None) or ''
        fm.refresh(editor.document(), fp)
        editor.line_number_area.update()
        editor.update_line_number_area_width(0)

    def _refresh_current(self):
        editor = self.app.current_editor()
        if editor:
            self._refresh(editor)

    def _on_text_changed(self, editor):
        self._refresh_timer.start()

    def deactivate(self):
        # Unfold everything and remove patches
        for eid, fm in self._managers.items():
            pass   # patches are closures — GC handles them on editor destruction
        self._managers.clear()


# ── Gutter patching ───────────────────────────────────────────────────────────

def _patch_gutter_width(editor):
    original_width = editor.line_number_area_width

    def patched_width():
        return original_width() + FOLD_GUTTER_WIDTH

    editor.line_number_area_width = patched_width
    editor.update_line_number_area_width(0)


def _patch_paint_event(editor, fm: FoldManager):
    """Prepend fold gutter painting to the existing paint event."""
    original_paint = editor.line_number_area_paint_event

    def patched_paint(event):
        original_paint(event)
        from PyQt6.QtGui import QPainter
        painter = QPainter(editor.line_number_area)
        crumb_h = 24 if (hasattr(editor, '_breadcrumb')
                         and editor._breadcrumb.isVisible()) else 0
        paint_fold_gutter(painter, editor, fm, event.rect(), crumb_h)
        painter.end()

    editor.line_number_area_paint_event = patched_paint


def _patch_click_event(editor, fm: FoldManager):
    """Add single-click fold toggle to the LineNumberArea."""
    original_press = editor.line_number_area.mousePressEvent

    def patched_press(event):
        if event.button() == Qt.MouseButton.LeftButton:
            crumb_h = 24 if (hasattr(editor, '_breadcrumb')
                             and editor._breadcrumb.isVisible()) else 0
            x = event.pos().x()
            if x <= FOLD_GUTTER_WIDTH:
                y = event.pos().y()
                line = fold_line_at_y(editor, fm, y, crumb_h)
                if line is not None:
                    fm.toggle(editor.document(), line)
                    editor.line_number_area.update()
                    editor.viewport().update()
                    return
        original_press(event)

    # Assign directly as a plain function — no MethodType binding needed
    # since we're replacing the instance method, not the class method
    editor.line_number_area.mousePressEvent = patched_press