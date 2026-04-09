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
    QRubberBand, QTabWidget,
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

# Port geometry
PORT_R        = 5    # port circle radius
PORT_HIT      = 12   # click detection radius
PORT_OUT_X    = CARD_W - PORT_R   # output port x (right edge)
PORT_IN_X     = PORT_R            # input port x (left edge)
PORT_Y        = CARD_H // 2       # port y (vertical center)


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
        self._hovered  = False

        self.setFixedSize(CARD_W, CARD_H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(self._tooltip())
        self.setMouseTracking(True)
        self._style()

    def _style(self):
        t = self._t
        if getattr(self.job, 'is_template', False):
            border = t.get('bg4',    '#7c6f64')
        elif self.job.trigger:
            border = t.get('purple', '#b16286')
        elif self.job.is_deploy:
            border = t.get('blue',   '#458588')
        elif self.job.is_manual:
            border = t.get('yellow', '#d79921')
        elif self.job.allow_failure:
            border = t.get('orange', '#d65d0e')
        else:
            border = t.get('bg3',    '#665c54')

        is_tmpl = getattr(self.job, 'is_template', False)
        bg = t.get('bg2' if self._selected else 'bg1',
                   '#504945' if self._selected else '#3c3836')

        opacity = '0.6' if is_tmpl else '1.0'
        self.setStyleSheet(f"""
            QFrame {{
                background: {bg};
                border: 2px solid {border};
                border-radius: 6px;
                opacity: {opacity};
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

        # Parallel count badge
        pc = getattr(self.job, 'parallel_count', 0)
        if pc > 0:
            badge_w = 28
            f.setPointSize(7); f.setBold(True); p.setFont(f)
            badge_color = QColor(t.get('purple', '#b16286'))
            p.setBrush(QBrush(badge_color))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(CARD_W - badge_w - 4, 4, badge_w, 14, 3, 3)
            p.setPen(QColor(t.get('bg0', '#282828')))
            p.drawText(QRect(CARD_W - badge_w - 4, 4, badge_w, 14),
                       Qt.AlignmentFlag.AlignCenter, f"×{pc}")
            f.setBold(False)

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

        # Draw connection ports when hovered
        if self._hovered:
            port_color = QColor(t.get('aqua', '#689d6a'))
            p.setBrush(QBrush(port_color))
            p.setPen(QPen(QColor(t.get('bg0', '#282828')), 1.5))
            # Output port (right edge)
            p.drawEllipse(PORT_OUT_X - PORT_R, PORT_Y - PORT_R,
                          PORT_R * 2, PORT_R * 2)
            # Input port (left edge)
            p.drawEllipse(PORT_IN_X - PORT_R, PORT_Y - PORT_R,
                          PORT_R * 2, PORT_R * 2)

    def enterEvent(self, event):
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self.update()
        super().leaveEvent(event)

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
    needs_changed   = pyqtSignal(object, str, bool)  # job, need_name, add(True)/remove(False)

    def __init__(self, label: str = "", parent=None):
        super().__init__(parent)
        self._pipeline: Pipeline | None = None
        self._cards:    dict[str, JobCard] = {}
        self._zones:    dict[str, StageDropZone] = {}
        self._selected: str | None = None
        self._t         = get_theme()
        self._label     = label

        # Wire drag state
        self._wire_source: str | None    = None   # job name
        self._wire_pos:    QPointF | None = None   # current mouse pos

        self.setAcceptDrops(True)
        self.setMouseTracking(True)
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

    # ── Port / wire interaction ───────────────────────────────────────

    def _card_output_port_pos(self, job_name: str) -> QPointF | None:
        """Global position of a card's output port."""
        card = self._cards.get(job_name)
        if not card:
            return None
        return QPointF(card.x() + PORT_OUT_X, card.y() + PORT_Y)

    def _card_input_port_pos(self, job_name: str) -> QPointF | None:
        """Global position of a card's input port."""
        card = self._cards.get(job_name)
        if not card:
            return None
        return QPointF(card.x() + PORT_IN_X, card.y() + PORT_Y)

    def _job_near_output_port(self, pos: QPointF) -> str | None:
        """Return job name if pos is within PORT_HIT of any output port."""
        for name in self._cards:
            p = self._card_output_port_pos(name)
            if p and (pos - p).manhattanLength() <= PORT_HIT:
                return name
        return None

    def _job_near_input_port(self, pos: QPointF) -> str | None:
        """Return job name if pos is within PORT_HIT of any input port."""
        for name in self._cards:
            p = self._card_input_port_pos(name)
            if p and (pos - p).manhattanLength() <= PORT_HIT:
                return name
        return None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = QPointF(event.position())
            hit = self._job_near_output_port(pos)
            if hit:
                self._wire_source = hit
                self._wire_pos    = pos
                self.setCursor(Qt.CursorShape.CrossCursor)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._wire_source:
            self._wire_pos = QPointF(event.position())
            self.update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._wire_source and event.button() == Qt.MouseButton.LeftButton:
            pos = QPointF(event.position())
            target = self._job_near_input_port(pos)
            if target and target != self._wire_source:
                if self._pipeline:
                    job = self._pipeline.jobs.get(target)
                    if job and self._wire_source not in job.needs:
                        self.needs_changed.emit(
                            job, self._wire_source, True
                        )
            self._wire_source = None
            self._wire_pos    = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.update()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event):
        """Right-click on an arrow to remove a dependency."""
        if not self._pipeline:
            return
        pos = QPointF(event.pos())
        # Find if pos is near any dependency arrow
        hit_job, hit_need = self._arrow_hit_test(pos)
        if hit_job and hit_need:
            from PyQt6.QtWidgets import QMenu
            menu = QMenu(self)
            act  = menu.addAction(
                f'Remove dependency: {hit_job.name} ← {hit_need}'
            )
            if menu.exec(event.globalPos()) == act:
                self.needs_changed.emit(hit_job, hit_need, False)

    def _arrow_hit_test(
        self, pos: QPointF, tol: float = 8.0
    ) -> tuple:
        """Return (job, need_name) if pos is near a dependency arrow."""
        if not self._pipeline:
            return None, None
        for job in self._pipeline.jobs.values():
            for need in job.needs:
                src = self._card_output_port_pos(need)
                dst = self._card_input_port_pos(job.name)
                if not src or not dst:
                    continue
                # Sample points along the bezier and check distance
                cx = (src.x() + dst.x()) / 2
                for t in [i / 10 for i in range(11)]:
                    u  = 1 - t
                    bx = (u**3 * src.x() +
                          3*u**2*t * cx +
                          3*u*t**2 * cx +
                          t**3 * dst.x())
                    by = (u**3 * src.y() +
                          3*u**2*t * src.y() +
                          3*u*t**2 * dst.y() +
                          t**3 * dst.y())
                    if abs(bx - pos.x()) + abs(by - pos.y()) < tol:
                        return job, need
        return None, None

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

        # Live wire while dragging
        if self._wire_source and self._wire_pos:
            src = self._card_output_port_pos(self._wire_source)
            if src:
                wire_color = QColor(t.get('yellow', '#d79921'))
                wire_color.setAlpha(200)
                pen2 = QPen(wire_color, 2)
                pen2.setStyle(Qt.PenStyle.DashLine)
                painter.setPen(pen2)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                cx  = (src.x() + self._wire_pos.x()) / 2
                path = QPainterPath()
                path.moveTo(src)
                path.cubicTo(
                    cx, src.y(),
                    cx, self._wire_pos.y(),
                    self._wire_pos.x(), self._wire_pos.y()
                )
                painter.drawPath(path)
                # Target port highlight
                target = self._job_near_input_port(self._wire_pos)
                if target:
                    tp = self._card_input_port_pos(target)
                    if tp:
                        painter.setBrush(QBrush(wire_color))
                        painter.setPen(Qt.PenStyle.NoPen)
                        painter.drawEllipse(
                            int(tp.x()) - PORT_R - 2,
                            int(tp.y()) - PORT_R - 2,
                            (PORT_R + 2) * 2,
                            (PORT_R + 2) * 2
                        )

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

        # Toolbar (above tabs, always visible)
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

        # Tab widget
        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        main_layout.addWidget(self._tabs)

        # ── Graph tab ──────────────────────────────────────────────────
        graph_widget = QWidget()
        graph_layout = QVBoxLayout(graph_widget)
        graph_layout.setContentsMargins(0, 0, 0, 0)
        graph_layout.setSpacing(0)

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
        graph_layout.addWidget(self._scroll)

        # Detail panel (bottom of graph tab)
        self._detail = QTextEdit()
        self._detail.setReadOnly(True)
        self._detail.setFixedHeight(130)
        self._detail.setPlaceholderText("Click a job to see details…")
        graph_layout.addWidget(self._detail)

        self._tabs.addTab(graph_widget, "Graph")

        # ── Info tab ───────────────────────────────────────────────────
        self._info_view = QTextEdit()
        self._info_view.setReadOnly(True)
        self._info_view.setPlaceholderText("Load a pipeline to see info…")
        self._tabs.addTab(self._info_view, "Info")

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

        # Template jobs swimlane (dot-prefixed jobs)
        templates = getattr(pipeline, 'templates', {})
        if templates:
            # Create a fake pipeline just for the templates
            from plugins.features.pipeline_viewer.parsers import Pipeline, PipelineType
            tmpl_stages = list({j.stage for j in templates.values()})
            tmpl_pipeline = Pipeline(
                PipelineType.GITLAB, tmpl_stages, templates,
                file_path=file_path
            )
            self._add_swimlane(tmpl_pipeline, "⬡ Templates", file_path)

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

        # Populate Info tab
        self._populate_info_tab(pipeline)

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
        canvas.needs_changed.connect(
            lambda job, need, add, fp=file_path:
            self._on_needs_changed(job, need, add, fp)
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

        all_jobs = list(pipeline.jobs.keys()) if pipeline else []
        dlg = JobEditorDialog(job, stages, all_jobs=all_jobs, parent=self)
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
                patcher.set_job_script(job_name, value)
            elif field == 'needs':
                # value is the complete new needs list
                # Find what was added and removed
                job = self._find_job_by_name(job_name)
                old_needs = set(job.needs if job else [])
                new_needs = set(value)
                for n in new_needs - old_needs:
                    patcher.add_need(job_name, n)
                for n in old_needs - new_needs:
                    patcher.remove_need(job_name, n)
            else:
                patcher.set_job_field(job_name, field, str(value))

        # Reload pipeline from disk
        QTimer.singleShot(100, self._refresh)

    def _on_needs_changed(
        self, job, need_name: str, add: bool, file_path: str
    ):
        """Add or remove a needs: dependency."""
        if isinstance(job, str):
            job = self._find_job_by_name(job)
        if not job:
            return
        patcher = self._get_patcher(file_path or self._file_path)
        if not patcher:
            return
        if add:
            patcher.add_need(job.name, need_name)
        else:
            patcher.remove_need(job.name, need_name)
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
        from PyQt6.QtWidgets import QInputDialog, QMessageBox
        if not self._pipeline or not self._patcher:
            return

        name, ok = QInputDialog.getText(
            self, "New Stage", "Stage name:"
        )
        if not ok or not name.strip():
            return
        stage_name = name.strip()

        self._patcher.add_stage(stage_name)

        # A stage with no jobs won't appear as a column.
        # Offer to add a placeholder job so the column is visible.
        reply = QMessageBox.question(
            self,
            "Add placeholder job?",
            f"Stage '{stage_name}' added.\n\n"
            f"Stages only appear as columns when they have jobs.\n"
            f"Add a placeholder job to '{stage_name}'?",
            QMessageBox.StandardButton.Yes |
            QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if reply == QMessageBox.StandardButton.Yes:
            job_name, ok2 = QInputDialog.getText(
                self, "Placeholder job",
                "Job name:",
                text=f"{stage_name}_job"
            )
            if ok2 and job_name.strip():
                self._patcher.insert_job(job_name.strip(), stage_name)

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

    # ── Info tab ──────────────────────────────────────────────────────

    def _populate_info_tab(self, pipeline):
        """Render includes, workflow rules, and variables into the Info tab."""
        try:
            self._populate_info_tab_inner(pipeline)
        except Exception as e:
            import traceback
            print(f'[PipelineInfo] ERROR: {e}')
            traceback.print_exc()
            self._info_view.setPlainText(f'Error rendering info tab:\n{e}')

    def _populate_info_tab_inner(self, pipeline):
        t = self._t
        self._info_view.clear()
        cursor = self._info_view.textCursor()

        from PyQt6.QtGui import QTextCharFormat, QTextBlockFormat, QColor, QFont

        def char_fmt(fg_key, bold=False, italic=False, size=9, mono=False):
            f = QTextCharFormat()
            f.setForeground(QColor(t.get(fg_key, '#ebdbb2')))
            f.setBackground(QColor(t.get('bg0', '#282828')))
            font = QFont()
            font.setPointSize(size)
            font.setBold(bold)
            font.setItalic(italic)
            if mono:
                font.setFamily('monospace')
            f.setFont(font)
            return f

        def block_fmt(left_margin=0, top=2, bottom=2):
            bf = QTextBlockFormat()
            bf.setLeftMargin(left_margin)
            bf.setTopMargin(top)
            bf.setBottomMargin(bottom)
            bf.setBackground(QColor(t.get('bg0', '#282828')))
            return bf

        def section(icon, title, count=None):
            cursor.insertBlock(block_fmt(top=8, bottom=4))
            label = f'{icon}  {title}'
            if count is not None:
                label += f'  ({count})'
            cursor.insertText(label, char_fmt('yellow', bold=True, size=10))

        def row(key, val, key_color='fg4', val_color='fg1',
                indent=16, mono_val=False):
            cursor.insertBlock(block_fmt(left_margin=indent))
            cursor.insertText(f'{key}', char_fmt(key_color, italic=True))
            if val:
                cursor.insertText('  ', char_fmt('bg3'))
                cursor.insertText(f'  {val}',
                    char_fmt(val_color, mono=mono_val))

        def muted(text, indent=16):
            cursor.insertBlock(block_fmt(left_margin=indent))
            cursor.insertText(text, char_fmt('bg4', italic=True))

        # Includes
        includes = getattr(pipeline, 'includes', [])
        section('📦', 'Includes', len(includes) if includes else None)
        if includes:
            for inc in includes:
                if isinstance(inc, dict):
                    if 'project' in inc:
                        row('remote', inc['project'], val_color='purple')
                        if 'file' in inc:
                            row('  └─ file', inc['file'],
                                val_color='aqua', indent=32)
                        if 'ref' in inc:
                            row('  └─ ref', inc['ref'],
                                val_color='fg4', indent=32)
                    elif 'local' in inc:
                        row('local', inc['local'], val_color='green')
                    elif 'template' in inc:
                        row('template', inc['template'], val_color='blue')
                    elif 'remote' in inc:
                        row('url', inc['remote'], val_color='blue')
                    else:
                        row('include', str(inc), val_color='fg1')
                elif isinstance(inc, str):
                    row('local', inc, val_color='green')
        else:
            muted('None')

        # Workflow
        workflow = getattr(pipeline, 'workflow', [])
        section('🔀', 'Workflow — Pipeline runs when',
                len(workflow) if workflow else None)
        if workflow:
            for rule in workflow:
                when = rule.get('when', 'on_success')
                cond = rule.get('if', '')
                icon_c = '✗' if when == 'never' else '✓'
                key_c  = 'red' if when == 'never' else 'green'
                val_c  = 'fg4' if when == 'never' else 'fg1'
                suffix = f'  → {when}' if when != 'on_success' else ''
                cursor.insertBlock(block_fmt(left_margin=16))
                cursor.insertText(f'{icon_c} ',
                    char_fmt(key_c, bold=True))
                cursor.insertText(cond,
                    char_fmt(val_c, mono=True, size=8))
                if suffix:
                    cursor.insertText(suffix,
                        char_fmt('orange', italic=True, size=8))
        else:
            muted('No workflow rules — pipeline always runs')

        # Variables
        variables = getattr(pipeline, 'variables', {})
        section('📋', 'Variables', len(variables) if variables else None)
        if variables:
            max_key = max((len(k) for k in variables), default=10)
            for key, val in sorted(variables.items()):
                is_secret = any(s in key.upper()
                    for s in ('PASSWORD', 'TOKEN', 'SECRET', 'KEY', 'PASS'))
                is_runtime = ('$CI_' in val or '${CI_' in val
                               or val.startswith('$'))
                display_val = '●●●●●●●●' if is_secret else val
                val_color   = 'fg4' if is_runtime else 'aqua'
                row(key.ljust(max_key), display_val,
                    val_color=val_color, mono_val=True)
        else:
            muted('No pipeline-level variables defined')

        self._info_view.moveCursor(
            self._info_view.textCursor().MoveOperation.Start
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
    
        # Tab widget styling
        if hasattr(self, '_tabs'):
            self._tabs.setStyleSheet(f"""
                QTabWidget::pane {{
                    border: none;
                    background: {t['bg0']};
                }}
                QTabBar::tab {{
                    background: {t['bg1']};
                    color: {t['fg4']};
                    padding: 4px 16px;
                    border: none;
                    border-right: 1px solid {t['bg3']};
                    font-size: 9pt;
                }}
                QTabBar::tab:selected {{
                    background: {t['bg2']};
                    color: {t['yellow']};
                    border-bottom: 2px solid {t['yellow']};
                }}
                QTabBar::tab:hover:!selected {{
                    background: {t['bg2']};
                    color: {t['fg1']};
                }}
            """)

        # Info view styling
        if hasattr(self, '_info_view'):
            self._info_view.setStyleSheet(f"""
                QTextEdit {{
                    background: {t['bg0']};
                    color: {t['fg1']};
                    border: none;
                    padding: 8px;
                    font-size: 9pt;
                }}
            """)

        # Propagate to all canvases
        for canvas in self._canvases.values():
            canvas._on_theme(t)

    def closeEvent(self, event):
        try:
            theme_signals.theme_changed.disconnect(self._apply_theme)
        except (RuntimeError, TypeError):
            pass
        super().closeEvent(event)