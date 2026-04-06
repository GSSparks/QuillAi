"""
panel.py

Visual pipeline graph panel with:
  - Drag-to-change-stage
  - Child pipeline swimlanes
  - Inline job editing
  - Immediate YAML write-back
"""

import os
from PyQt6.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QScrollArea, QLabel, QPushButton, QSizePolicy,
    QFrame, QTextEdit, QSplitter, QApplication,
    QRubberBand,
)
from PyQt6.QtCore import (
    Qt, pyqtSignal, QPoint, QPointF, QRect, QSize,
    QTimer, QMimeData,
)
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QFont, QFontMetrics,
    QBrush, QPainterPath, QDrag, QPixmap,
)

from ui.theme import get_theme, theme_signals, build_dock_stylesheet
from plugins.features.pipeline_viewer.parsers import (
    Pipeline, PipelineJob, PipelineType
)


# ── Constants ─────────────────────────────────────────────────────────────────

CARD_W        = 164
CARD_H        = 64
CARD_GAP      = 10
COL_W         = 184
PAD           = 16
HEADER_H      = 28
SWIMLANE_GAP  = 32
SWIMLANE_HDR  = 24


# ── Job Card ──────────────────────────────────────────────────────────────────

class JobCard(QFrame):

    clicked        = pyqtSignal(object)         # PipelineJob
    double_clicked = pyqtSignal(object)         # PipelineJob
    drag_started   = pyqtSignal(object, object) # PipelineJob, QPoint

    def __init__(self, job: PipelineJob, theme: dict, parent=None):
        super().__init__(parent)
        self.job       = job
        self._t        = theme
        self._selected = False
        self._drag_pos = None

        self.setFixedSize(CARD_W, CARD_H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(self._tooltip())
        self._style()

    def _style(self):
        t = self._t
        if self.job.trigger:
            border = t.get('purple', '#b16286')
        elif self.job.is_deploy:
            border = t.get('blue',   '#458588')
        elif self.job.is_manual:
            border = t.get('yellow', '#d79921')
        elif self.job.allow_failure:
            border = t.get('orange', '#d65d0e')
        else:
            border = t.get('bg3',    '#665c54')

        bg = t.get('bg2' if self._selected else 'bg1',
                   '#504945' if self._selected else '#3c3836')

        self.setStyleSheet(f"""
            QFrame {{
                background: {bg};
                border: 2px solid {border};
                border-radius: 6px;
            }}
        """)

    def select(self, v: bool):
        self._selected = v
        self._style()

    def _tooltip(self) -> str:
        j = self.job
        lines = [f"Job: {j.name}", f"Stage: {j.stage}"]
        if j.image:     lines.append(f"Image: {j.image}")
        if j.needs:     lines.append(f"Needs: {', '.join(j.needs)}")
        if j.trigger:
            t = j.trigger
            if t.is_remote:
                lines.append(f"Triggers: {t.project}")
            else:
                lines.append(f"Triggers: {t.include}")
            if t.strategy:
                lines.append(f"Strategy: {t.strategy}")
        if j.is_manual: lines.append("⚠ Manual")
        if j.allow_failure: lines.append("⚠ Allow failure")
        return '\n'.join(lines)

    def paintEvent(self, event):
        super().paintEvent(event)
        p  = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        t  = self._t
        fg = QColor(t.get('fg1', '#ebdbb2'))
        fg4= QColor(t.get('fg4', '#a89984'))

        # Icon
        icon = ("⚡" if self.job.trigger else
                "⏸" if self.job.is_manual else
                "🚀" if self.job.is_deploy else "▶")
        f = QFont(); f.setPointSize(9)
        p.setFont(f); p.setPen(fg)
        p.drawText(QRect(6, 6, 20, 20),
                   Qt.AlignmentFlag.AlignCenter, icon)

        # Name
        f.setBold(True); p.setFont(f)
        name = self.job.name
        fm   = QFontMetrics(f)
        if fm.horizontalAdvance(name) > 124:
            name = name[:17] + '…'
        p.drawText(QRect(28, 6, 130, 20),
                   Qt.AlignmentFlag.AlignVCenter, name)

        # Subtitle
        f.setBold(False); f.setPointSize(8); p.setFont(f)
        p.setPen(fg4)
        sub = self.job.image or self.job.stage
        if sub:
            fm = QFontMetrics(f)
            if fm.horizontalAdvance(sub) > 148:
                sub = sub[:20] + '…'
            p.drawText(QRect(6, 30, 152, 16),
                       Qt.AlignmentFlag.AlignVCenter, sub)

        # Needs / trigger hint
        if self.job.needs:
            f.setPointSize(7); p.setFont(f)
            p.setPen(QColor(t.get('aqua', '#689d6a')))
            hint = f"← {', '.join(self.job.needs[:2])}"
            if len(self.job.needs) > 2:
                hint += '…'
            p.drawText(QRect(6, 48, 152, 12),
                       Qt.AlignmentFlag.AlignVCenter, hint)
        elif self.job.trigger and not self.job.trigger.is_remote:
            f.setPointSize(7); p.setFont(f)
            p.setPen(QColor(t.get('purple', '#b16286')))
            p.drawText(QRect(6, 48, 152, 12),
                       Qt.AlignmentFlag.AlignVCenter,
                       f"⤵ {self.job.trigger.include}")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (self._drag_pos and
                event.buttons() & Qt.MouseButton.LeftButton):
            delta = (event.position().toPoint() - self._drag_pos).manhattanLength()
            if delta > 8:
                self.drag_started.emit(self.job, self._drag_pos)
                self._drag_pos = None
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._drag_pos:  # no drag occurred
                self.clicked.emit(self.job)
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        self.double_clicked.emit(self.job)


# ── Drop Zone ─────────────────────────────────────────────────────────────────

class StageDropZone(QWidget):
    """Invisible overlay that accepts card drops for a stage column."""

    card_dropped = pyqtSignal(object, str)   # PipelineJob, stage_name

    def __init__(self, stage: str, parent=None):
        super().__init__(parent)
        self.stage      = stage
        self._highlight = False
        self.setAcceptDrops(True)

    def set_highlight(self, v: bool):
        self._highlight = v
        self.update()

    def paintEvent(self, event):
        if not self._highlight:
            return
        p = QPainter(self)
        t = get_theme()
        c = QColor(t.get('blue', '#458588'))
        c.setAlpha(40)
        p.fillRect(self.rect(), c)
        pen = QPen(QColor(t.get('blue', '#458588')), 2)
        pen.setStyle(Qt.PenStyle.DashLine)
        p.setPen(pen)
        p.drawRect(self.rect().adjusted(1, 1, -1, -1))

    def dragEnterEvent(self, event):
        if event.mimeData().hasText():
            self.set_highlight(True)
            event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self.set_highlight(False)

    def dropEvent(self, event):
        self.set_highlight(False)
        job_name = event.mimeData().text()
        event.acceptProposedAction()
        # We emit with job_name as string — canvas resolves to job object
        self.card_dropped.emit(job_name, self.stage)


# ── Pipeline Canvas ───────────────────────────────────────────────────────────

class PipelineCanvas(QWidget):
    """
    Renders one pipeline (parent or child) as a stage-column grid.
    Handles drag-to-stage and emits signals for job interactions.
    """

    job_selected    = pyqtSignal(object)         # PipelineJob
    job_edit        = pyqtSignal(object)         # PipelineJob
    stage_changed   = pyqtSignal(object, str)    # PipelineJob, new_stage
    card_drag_start = pyqtSignal(object, str)    # job_name, source_stage

    def __init__(self, label: str = "", parent=None):
        super().__init__(parent)
        self._pipeline: Pipeline | None = None
        self._cards:    dict[str, JobCard] = {}
        self._zones:    dict[str, StageDropZone] = {}
        self._selected: str | None = None
        self._t         = get_theme()
        self._label     = label

        self.setAcceptDrops(True)
        theme_signals.theme_changed.connect(self._on_theme)

    def load_pipeline(self, pipeline: Pipeline, label: str = ""):
        self._pipeline = pipeline
        self._label    = label
        self._cards.clear()
        self._selected = None
        self._zones.clear()

        for child in self.findChildren((JobCard, StageDropZone)):
            child.deleteLater()

        if not pipeline or not pipeline.jobs:
            self.setMinimumSize(400, 160)
            self.update()
            return

        self._layout()

    def _layout(self):
        p   = self._pipeline
        if not p:
            return

        # Group jobs by stage — preserve stage order
        stage_jobs: dict[str, list] = {}
        for s in p.stages:
            stage_jobs[s] = []
        for job in p.jobs.values():
            if job.stage in stage_jobs:
                stage_jobs[job.stage].append(job)
            else:
                stage_jobs.setdefault(job.stage, []).append(job)

        stages   = [s for s in p.stages if s in stage_jobs]
        max_jobs = max((len(v) for v in stage_jobs.values()), default=1)

        total_w = PAD + len(stages) * COL_W + PAD
        total_h = (PAD + HEADER_H +
                   max_jobs * (CARD_H + CARD_GAP) + PAD)

        self.setMinimumSize(total_w, total_h)
        self.resize(total_w, total_h)

        for col_idx, stage in enumerate(stages):
            x = PAD + col_idx * COL_W

            # Drop zone for this column
            zone = StageDropZone(stage, self)
            zone.setGeometry(x, 0, COL_W - 8, total_h)
            zone.card_dropped.connect(self._on_card_dropped)
            zone.show()
            self._zones[stage] = zone

            for row_idx, job in enumerate(stage_jobs[stage]):
                y = PAD + HEADER_H + row_idx * (CARD_H + CARD_GAP)
                card = JobCard(job, self._t, self)
                card.move(x + 10, y)
                card.show()
                card.raise_()
                card.clicked.connect(self._on_card_clicked)
                card.double_clicked.connect(self._on_card_double_clicked)
                card.drag_started.connect(self._on_drag_started)
                self._cards[job.name] = card

        self.update()

    def _on_card_dropped(self, job_name_or_job, stage: str):
        # May receive job_name string from drop event
        if isinstance(job_name_or_job, str):
            job_name = job_name_or_job
        else:
            job_name = job_name_or_job.name

        if not self._pipeline:
            return
        job = self._pipeline.jobs.get(job_name)
        if job and job.stage != stage:
            self.stage_changed.emit(job, stage)

    def _on_drag_started(self, job: PipelineJob, offset: QPoint):
        drag = QDrag(self)
        mime = QMimeData()
        mime.setText(job.name)
        drag.setMimeData(mime)

        # Ghost pixmap
        px = QPixmap(CARD_W, CARD_H)
        px.fill(Qt.GlobalColor.transparent)
        card = self._cards.get(job.name)
        if card:
            card.render(px)
        drag.setPixmap(px)
        drag.setHotSpot(offset)
        drag.exec(Qt.DropAction.MoveAction)

    def _on_card_clicked(self, job: PipelineJob):
        if self._selected and self._selected in self._cards:
            self._cards[self._selected].select(False)
        self._selected = job.name
        self._cards[job.name].select(True)
        self.job_selected.emit(job)
        self.update()

    def _on_card_double_clicked(self, job: PipelineJob):
        self.job_edit.emit(job)

    def paintEvent(self, event):
        if not self._pipeline:
            p = QPainter(self)
            t = self._t
            p.setPen(QColor(t.get('fg4', '#a89984')))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                       "No pipeline loaded")
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = self._t

        painter.fillRect(self.rect(),
                         QColor(t.get('bg0', '#282828')))

        pl = self._pipeline

        stage_jobs: dict[str, list] = {}
        for s in pl.stages:
            stage_jobs[s] = []
        for job in pl.jobs.values():
            stage_jobs.setdefault(job.stage, []).append(job)
        stages = [s for s in pl.stages if s in stage_jobs]

        for col_idx, stage in enumerate(stages):
            x = PAD + col_idx * COL_W

            # Column bg
            col_bg = QColor(t.get('bg1', '#3c3836'))
            col_bg.setAlpha(60)
            painter.fillRect(x, PAD, COL_W - 8,
                             self.height() - PAD * 2, col_bg)

            # Header
            hdr_bg = QColor(t.get('bg2', '#504945'))
            painter.fillRect(x, PAD, COL_W - 8, HEADER_H, hdr_bg)

            f = QFont(); f.setPointSize(8); f.setBold(True)
            painter.setFont(f)
            painter.setPen(QColor(t.get('fg1', '#ebdbb2')))
            painter.drawText(
                QRect(x + 8, PAD, COL_W - 16, HEADER_H),
                Qt.AlignmentFlag.AlignVCenter,
                stage.upper()
            )

        # Dependency arrows
        self._draw_arrows(painter, stages, stage_jobs)

    def _draw_arrows(self, painter, stages, stage_jobs):
        t           = self._t
        arrow_color = QColor(t.get('aqua', '#689d6a'))
        arrow_color.setAlpha(150)
        pen = QPen(arrow_color, 1.5)
        pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)

        def right_of(job_name):
            c = self._cards.get(job_name)
            if c:
                return c.pos() + QPoint(c.width(), c.height() // 2)
            return None

        def left_of(job_name):
            c = self._cards.get(job_name)
            if c:
                return c.pos() + QPoint(0, c.height() // 2)
            return None

        if not self._pipeline:
            return

        for job in self._pipeline.jobs.values():
            for need in job.needs:
                src = right_of(need)
                dst = left_of(job.name)
                if not src or not dst:
                    continue
                sf = src.toPointF()
                df = dst.toPointF()
                cx = (sf.x() + df.x()) / 2
                path = QPainterPath()
                path.moveTo(sf)
                path.cubicTo(cx, sf.y(), cx, df.y(), df.x(), df.y())
                painter.drawPath(path)

                # Arrowhead
                painter.setBrush(QBrush(arrow_color))
                painter.setPen(Qt.PenStyle.NoPen)
                ax, ay = int(df.x()), int(df.y())
                from PyQt6.QtGui import QPolygon
                painter.drawPolygon(QPolygon([
                    QPoint(ax,     ay),
                    QPoint(ax - 8, ay - 4),
                    QPoint(ax - 8, ay + 4),
                ]))
                painter.setPen(pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)

    def _on_theme(self, t: dict):
        self._t = t
        for card in self._cards.values():
            card._t = t
            card._style()
        self.update()

    def refresh_job(self, job: PipelineJob):
        """Refresh a single card after a job edit."""
        card = self._cards.get(job.name)
        if card:
            card.job = job
            card._style()
            card.update()
        self._layout()


# ── Main Panel ────────────────────────────────────────────────────────────────

class PipelineViewerPanel(QDockWidget):

    jump_to_job   = pyqtSignal(str, str)   # file_path, job_name

    def __init__(self, parent=None):
        super().__init__("Pipeline", parent)
        self.setObjectName("pipeline_viewer_dock")
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable  |
            QDockWidget.DockWidgetFeature.DockWidgetMovable   |
            QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )

        self._pipeline:   Pipeline | None = None
        self._file_path:  str = ""
        self._patcher     = None
        self._t           = get_theme()

        self._build_ui()
        self._apply_theme(self._t)
        theme_signals.theme_changed.connect(self._apply_theme)

    def _build_ui(self):
        container = QWidget()
        main_layout = QVBoxLayout(container)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Toolbar
        toolbar = QWidget()
        toolbar.setFixedHeight(32)
        tl = QHBoxLayout(toolbar)
        tl.setContentsMargins(8, 0, 4, 0)

        self._file_label = QLabel("No pipeline loaded")
        self._file_label.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred
        )
        tl.addWidget(self._file_label)

        add_job_btn = QPushButton("+ Job")
        add_job_btn.setFixedHeight(22)
        add_job_btn.setToolTip("Add a new job")
        add_job_btn.clicked.connect(self._on_add_job)
        tl.addWidget(add_job_btn)

        add_stage_btn = QPushButton("+ Stage")
        add_stage_btn.setFixedHeight(22)
        add_stage_btn.setToolTip("Add a new stage")
        add_stage_btn.clicked.connect(self._on_add_stage)
        tl.addWidget(add_stage_btn)

        refresh_btn = QPushButton("↻")
        refresh_btn.setFixedSize(24, 22)
        refresh_btn.clicked.connect(self._refresh)
        tl.addWidget(refresh_btn)

        main_layout.addWidget(toolbar)

        # Scroll area containing swimlanes
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        self._swimlane_container = QWidget()
        self._swimlane_layout    = QVBoxLayout(self._swimlane_container)
        self._swimlane_layout.setContentsMargins(0, 0, 0, 0)
        self._swimlane_layout.setSpacing(0)
        self._swimlane_layout.addStretch()

        self._scroll.setWidget(self._swimlane_container)
        main_layout.addWidget(self._scroll)

        # Detail panel
        self._detail = QTextEdit()
        self._detail.setReadOnly(True)
        self._detail.setFixedHeight(130)
        self._detail.setPlaceholderText("Click a job to see details…")
        main_layout.addWidget(self._detail)

        self.setWidget(container)

        # Track canvases
        self._canvases: dict[str, PipelineCanvas] = {}

    def load_pipeline(self, pipeline: Pipeline, file_path: str = ""):
        from plugins.features.pipeline_viewer.patcher import YAMLPatcher

        self._pipeline  = pipeline
        self._file_path = file_path

        if file_path and os.path.exists(file_path):
            try:
                self._patcher = YAMLPatcher(file_path)
            except Exception:
                self._patcher = None

        # Clear existing swimlanes
        for canvas in self._canvases.values():
            canvas.deleteLater()
        self._canvases.clear()

        # Remove all widgets from layout except stretch
        while self._swimlane_layout.count() > 1:
            item = self._swimlane_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Parent pipeline swimlane
        self._add_swimlane(pipeline, "Parent pipeline", file_path)

        # Child pipeline swimlanes
        for trigger_job_name, child in pipeline.children.items():
            label = f"⤵ {trigger_job_name} → {os.path.basename(child.file_path)}"
            self._add_swimlane(child, label, child.file_path)

        name  = os.path.basename(file_path) if file_path else "pipeline"
        jobs  = len(pipeline.jobs)
        total_children = sum(len(c.jobs) for c in pipeline.children.values())
        self._file_label.setText(
            f"{name}  ·  {jobs} jobs"
            + (f"  ·  {total_children} child jobs" if total_children else "")
        )

    def _add_swimlane(self, pipeline: Pipeline,
                      label: str, file_path: str):
        """Add a labeled swimlane for one pipeline."""
        wrapper = QWidget()
        wl      = QVBoxLayout(wrapper)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.setSpacing(0)

        # Swimlane header
        hdr = QLabel(f"  {label}")
        hdr.setFixedHeight(SWIMLANE_HDR)
        hdr.setObjectName("swimlaneHeader")
        wl.addWidget(hdr)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        wl.addWidget(sep)

        # Canvas
        canvas = PipelineCanvas(label, wrapper)
        canvas.load_pipeline(pipeline, label)
        canvas.job_selected.connect(self._on_job_selected)
        canvas.job_edit.connect(self._on_job_edit)
        canvas.stage_changed.connect(
            lambda job, stage, fp=file_path:
            self._on_stage_changed(job, stage, fp)
        )
        wl.addWidget(canvas)

        # Bottom gap
        gap = QWidget()
        gap.setFixedHeight(SWIMLANE_GAP)
        wl.addWidget(gap)

        # Insert before the stretch
        self._swimlane_layout.insertWidget(
            self._swimlane_layout.count() - 1, wrapper
        )
        self._canvases[label] = canvas
        self._apply_swimlane_theme(hdr, sep)

    def _apply_swimlane_theme(self, hdr: QLabel, sep: QFrame):
        t = self._t
        hdr.setStyleSheet(f"""
            QLabel {{
                background: {t.get('bg2', '#504945')};
                color: {t.get('yellow', '#d79921')};
                font-size: 9pt;
                font-weight: bold;
            }}
        """)
        sep.setStyleSheet(
            f"background: {t.get('bg3', '#665c54')};"
        )

    # ── Job interactions ──────────────────────────────────────────────────

    def _on_job_selected(self, job: PipelineJob):
        self._show_detail(job)
        self.jump_to_job.emit(job.file_path or self._file_path, job.name)

    def _on_job_edit(self, job: PipelineJob):
        """Open inline editor for a job."""
        from plugins.features.pipeline_viewer.editor_dialog import (
            JobEditorDialog
        )
        pipeline = self._find_pipeline_for_job(job)
        stages   = pipeline.stages if pipeline else []

        dlg = JobEditorDialog(job, stages, self)
        dlg.job_changed.connect(self._on_job_changed)

        # Position near the card
        canvas = self._find_canvas_for_job(job)
        if canvas:
            card = canvas._cards.get(job.name)
            if card:
                pos = card.mapToGlobal(QPoint(0, card.height()))
                dlg.move(pos)

        dlg.exec()

    def _on_job_changed(self, job_name: str, changes: dict):
        """Apply edits from the inline editor to the YAML."""
        if not self._patcher:
            return

        job      = self._find_job_by_name(job_name)
        fp       = job.file_path if job else self._file_path

        # Get the right patcher for this file
        patcher = self._get_patcher(fp)
        if not patcher:
            return

        for field, value in changes.items():
            if field == 'name':
                patcher.rename_job(job_name, value)
            elif field == 'stage':
                patcher.set_job_stage(job_name, value)
            elif field == 'allow_failure':
                patcher.set_job_allow_failure(job_name, value)
            elif field == 'script':
                # Script is a list — write it back as a block
                patcher.set_job_script(job_name, value)
            else:
                patcher.set_job_field(job_name, field, str(value))

        # Reload pipeline from disk
        QTimer.singleShot(100, self._refresh)

    def _on_stage_changed(self, job, stage: str, file_path: str):
        """Called when a card is dropped onto a different stage."""
        # job may be a string (job_name) from drop event
        if isinstance(job, str):
            job = self._find_job_by_name(job)
        if not job:
            return

        patcher = self._get_patcher(file_path or self._file_path)
        if patcher:
            patcher.set_job_stage(job.name, stage)
            QTimer.singleShot(100, self._refresh)

    # ── Add job / stage ───────────────────────────────────────────────────

    def _on_add_job(self):
        from PyQt6.QtWidgets import QInputDialog
        if not self._pipeline or not self._patcher:
            return

        name, ok = QInputDialog.getText(
            self, "New Job", "Job name:"
        )
        if not ok or not name.strip():
            return

        stage_name, ok = QInputDialog.getItem(
            self, "Stage", "Select stage:",
            self._pipeline.stages, 0, False
        )
        if not ok:
            return

        self._patcher.insert_job(name.strip(), stage_name)
        QTimer.singleShot(100, self._refresh)

    def _on_add_stage(self):
        from PyQt6.QtWidgets import QInputDialog
        if not self._pipeline or not self._patcher:
            return

        name, ok = QInputDialog.getText(
            self, "New Stage", "Stage name:"
        )
        if not ok or not name.strip():
            return

        self._patcher.add_stage(name.strip())
        QTimer.singleShot(100, self._refresh)

    # ── Detail panel ──────────────────────────────────────────────────────

    def _show_detail(self, job: PipelineJob):
        t = self._t
    
        lines = []
    
        lines.append(('heading', f"{job.name}  —  {job.stage}"))
    
        if job.image:
            lines.append(('key_val', ('Image', job.image)))
        if job.environment:
            lines.append(('key_val', ('Environment', job.environment)))
        if job.needs:
            lines.append(('key_val', ('Needs', ', '.join(job.needs))))
        if job.tags:
            lines.append(('key_val', ('Tags', ', '.join(job.tags))))
        if job.trigger:
            tr = job.trigger
            if tr.is_remote:
                lines.append(('key_val', ('Triggers (remote)', tr.project)))
            else:
                lines.append(('key_val', ('Triggers', tr.include)))
            if tr.strategy:
                lines.append(('key_val', ('Strategy', tr.strategy)))
        if job.when and job.when != 'on_success':
            lines.append(('key_val', ('When', job.when)))
        if job.is_manual:
            lines.append(('badge', '⚠  Manual trigger required'))
        if job.allow_failure:
            lines.append(('badge', '⚠  Allow failure'))
        if job.script:
            lines.append(('section', 'Script'))
            for s in job.script[:8]:
                lines.append(('script', s))
            if len(job.script) > 8:
                lines.append(('muted', f'… +{len(job.script) - 8} more steps'))
    
        lines.append(('muted', 'Double-click to edit  ·  Drag to change stage'))
    
        self._detail.clear()
        cursor = self._detail.textCursor()
    
        from PyQt6.QtGui import QTextCharFormat, QTextBlockFormat, QColor, QFont
    
        def fmt(fg_key, bold=False, italic=False, size=9, bg_key=None):
            f = QTextCharFormat()
            f.setForeground(QColor(t.get(fg_key, '#ebdbb2')))
            if bg_key:
                f.setBackground(QColor(t.get(bg_key, '#282828')))
            else:
                f.setBackground(QColor(t.get('bg0', '#282828')))
            font = QFont()
            font.setPointSize(size)
            font.setBold(bold)
            font.setItalic(italic)
            f.setFont(font)
            return f
    
        def block_fmt(left_margin=0):
            bf = QTextBlockFormat()
            bf.setLeftMargin(left_margin)
            bf.setTopMargin(1)
            bf.setBottomMargin(1)
            bf.setBackground(QColor(t.get('bg0', '#282828')))
            return bf
    
        for kind, data in lines:
            cursor.insertBlock(block_fmt())
            if kind == 'heading':
                cursor.insertText(data, fmt('yellow', bold=True, size=10))
            elif kind == 'key_val':
                key, val = data
                cursor.insertText(f"{key}: ", fmt('fg4', italic=True))
                cursor.insertText(val, fmt('fg1'))
            elif kind == 'section':
                cursor.insertBlock(block_fmt())
                cursor.insertText(data, fmt('green', bold=True))
            elif kind == 'script':
                cursor.insertBlock(block_fmt(left_margin=12))
                cursor.insertText('• ', fmt('fg4'))
                cursor.insertText(data, fmt('aqua'))
            elif kind == 'badge':
                cursor.insertText(data, fmt('yellow'))
            elif kind == 'muted':
                cursor.insertBlock(block_fmt())
                cursor.insertText(data, fmt('bg3', italic=True))
    
        self._detail.setTextCursor(cursor)
        self._detail.moveCursor(
            self._detail.textCursor().MoveOperation.Start
        )

    # ── Refresh ───────────────────────────────────────────────────────────

    def _refresh(self):
        if self._file_path and os.path.exists(self._file_path):
            from plugins.features.pipeline_viewer.parsers import detect_and_parse
            pipeline = detect_and_parse(self._file_path)
            if pipeline:
                self.load_pipeline(pipeline, self._file_path)

    # ── Helpers ───────────────────────────────────────────────────────────

    def _find_pipeline_for_job(self, job: PipelineJob) -> Pipeline | None:
        if not self._pipeline:
            return None
        if job.name in self._pipeline.jobs:
            return self._pipeline
        for child in self._pipeline.children.values():
            if job.name in child.jobs:
                return child
        return None

    def _find_job_by_name(self, name: str) -> PipelineJob | None:
        if not self._pipeline:
            return None
        job = self._pipeline.jobs.get(name)
        if job:
            return job
        for child in self._pipeline.children.values():
            job = child.jobs.get(name)
            if job:
                return job
        return None

    def _find_canvas_for_job(self, job: PipelineJob):
        for canvas in self._canvases.values():
            if job.name in canvas._cards:
                return canvas
        return None

    def _get_patcher(self, file_path: str):
        from plugins.features.pipeline_viewer.patcher import YAMLPatcher
        if not file_path or not os.path.exists(file_path):
            return None
        if (self._patcher and
                self._patcher.file_path == file_path):
            self._patcher.reload()
            return self._patcher
        try:
            return YAMLPatcher(file_path)
        except Exception:
            return None

    # ── Theme ─────────────────────────────────────────────────────────────

    def _apply_theme(self, t: dict):
        self._t = t
        self.setStyleSheet(build_dock_stylesheet(t))
    
        self._detail.setStyleSheet(f"""
            QTextEdit {{
                background: {t['bg0']};
                color: {t['fg1']};
                border: none;
                border-top: 1px solid {t['bg3']};
                padding: 4px;
                font-family: monospace;
                font-size: 9pt;
            }}
        """)
    
        self._file_label.setStyleSheet(f"""
            QLabel {{
                color: {t['fg4']};
                font-size: 9pt;
                padding: 0 4px;
            }}
        """)
    
        self._scroll.setStyleSheet(f"""
            QScrollArea {{
                background: {t['bg0']};
                border: none;
            }}
            QScrollBar:vertical {{
                background: {t['bg1']};
                width: 8px;
                border: none;
            }}
            QScrollBar::handle:vertical {{
                background: {t['bg3']};
                border-radius: 4px;
                min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {t['bg4']};
            }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{
                height: 0;
            }}
            QScrollBar:horizontal {{
                background: {t['bg1']};
                height: 8px;
                border: none;
            }}
            QScrollBar::handle:horizontal {{
                background: {t['bg3']};
                border-radius: 4px;
                min-width: 20px;
            }}
            QScrollBar::handle:horizontal:hover {{
                background: {t['bg4']};
            }}
            QScrollBar::add-line:horizontal,
            QScrollBar::sub-line:horizontal {{
                width: 0;
            }}
        """)
    
        self._swimlane_container.setStyleSheet(f"""
            QWidget {{
                background: {t['bg0']};
            }}
        """)
    
        # Refresh swimlane headers and separators
        for wrapper in self._swimlane_container.findChildren(QLabel):
            if wrapper.objectName() == "swimlaneHeader":
                wrapper.setStyleSheet(f"""
                    QLabel {{
                        background: {t['bg2']};
                        color: {t['yellow']};
                        font-size: 9pt;
                        font-weight: bold;
                        padding: 2px 8px;
                    }}
                """)
    
        for sep in self._swimlane_container.findChildren(QFrame):
            if sep.frameShape() == QFrame.Shape.HLine:
                sep.setStyleSheet(f"background: {t['bg3']};")
    
        # Propagate to all canvases
        for canvas in self._canvases.values():
            canvas._on_theme(t)

    def closeEvent(self, event):
        try:
            theme_signals.theme_changed.disconnect(self._apply_theme)
        except (RuntimeError, TypeError):
            pass
        super().closeEvent(event)