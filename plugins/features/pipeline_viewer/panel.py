"""
panel.py

Visual pipeline graph panel.
Renders stages as columns, jobs as cards, with dependency arrows.
Clicking a job shows its details and jumps to its definition in the file.
"""

import os
from PyQt6.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QScrollArea, QLabel, QPushButton, QSizePolicy,
    QFrame, QTextEdit, QSplitter,
)
from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QRect, QSize, QTimer
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QFont, QFontMetrics,
    QBrush, QPainterPath,
)

from ui.theme import get_theme, theme_signals, build_dock_stylesheet
from plugins.features.pipeline_viewer.parsers import (
    Pipeline, PipelineJob, PipelineType
)


class JobCard(QFrame):
    """A single job card in the pipeline graph."""

    clicked = pyqtSignal(object)   # PipelineJob

    def __init__(self, job: PipelineJob, theme: dict, parent=None):
        super().__init__(parent)
        self.job   = job
        self._t    = theme
        self._selected = False

        self.setFixedSize(160, 64)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(self._build_tooltip())
        self._apply_style()

    def _apply_style(self):
        t = self._t
        if self.job.is_deploy:
            border = t.get('blue',   '#458588')
        elif self.job.is_manual:
            border = t.get('yellow', '#d79921')
        elif self.job.allow_failure:
            border = t.get('orange', '#d65d0e')
        else:
            border = t.get('bg3',    '#665c54')

        bg = t.get('bg1', '#3c3836')
        if self._selected:
            bg = t.get('bg2', '#504945')

        self.setStyleSheet(f"""
            QFrame {{
                background: {bg};
                border: 2px solid {border};
                border-radius: 6px;
            }}
        """)

    def select(self, selected: bool):
        self._selected = selected
        self._apply_style()

    def _build_tooltip(self) -> str:
        j = self.job
        lines = [f"Job: {j.name}", f"Stage: {j.stage}"]
        if j.image:
            lines.append(f"Image: {j.image}")
        if j.runs_on:
            lines.append(f"Runs on: {j.runs_on}")
        if j.needs:
            lines.append(f"Needs: {', '.join(j.needs)}")
        if j.environment:
            lines.append(f"Environment: {j.environment}")
        if j.is_manual:
            lines.append("⚠ Manual trigger required")
        if j.allow_failure:
            lines.append("⚠ Allow failure")
        return '\n'.join(lines)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        t   = self._t
        fg  = QColor(t.get('fg1',    '#ebdbb2'))
        fg4 = QColor(t.get('fg4',    '#a89984'))

        # Icon
        if self.job.is_manual:
            icon = "⏸"
        elif self.job.is_deploy:
            icon = "🚀"
        elif self.job.uses:
            icon = "⚙"
        else:
            icon = "▶"

        font = QFont()
        font.setPointSize(9)
        painter.setFont(font)
        painter.setPen(fg)
        painter.drawText(QRect(8, 8, 20, 20), Qt.AlignmentFlag.AlignCenter, icon)

        # Job name
        font.setPointSize(9)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(fg)
        name = self.job.name
        fm   = QFontMetrics(font)
        if fm.horizontalAdvance(name) > 120:
            name = name[:16] + '…'
        painter.drawText(QRect(30, 8, 126, 20),
                         Qt.AlignmentFlag.AlignVCenter, name)

        # Stage / image / runs-on subtitle
        font.setBold(False)
        font.setPointSize(8)
        painter.setFont(font)
        painter.setPen(fg4)
        sub = self.job.image or self.job.runs_on or self.job.stage
        if sub:
            fm = QFontMetrics(font)
            if fm.horizontalAdvance(sub) > 140:
                sub = sub[:18] + '…'
            painter.drawText(QRect(8, 32, 148, 16),
                             Qt.AlignmentFlag.AlignVCenter, sub)

        # Needs badge
        if self.job.needs:
            font.setPointSize(7)
            painter.setFont(font)
            painter.setPen(QColor(t.get('aqua', '#689d6a')))
            painter.drawText(QRect(8, 48, 148, 12),
                             Qt.AlignmentFlag.AlignVCenter,
                             f"← {', '.join(self.job.needs[:2])}"
                             + ('…' if len(self.job.needs) > 2 else ''))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.job)
        super().mousePressEvent(event)


class PipelineCanvas(QWidget):
    """
    Renders the full pipeline graph — stages as columns, jobs as cards,
    dependency arrows between them.
    """

    job_selected = pyqtSignal(object)   # PipelineJob

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pipeline:  Pipeline | None = None
        self._cards:     dict[str, JobCard] = {}
        self._selected:  str | None = None
        self._t          = get_theme()

        self.setMinimumHeight(200)
        theme_signals.theme_changed.connect(self._on_theme)

    def load_pipeline(self, pipeline: Pipeline):
        self._pipeline = pipeline
        self._cards.clear()
        self._selected = None

        # Remove old cards
        for child in self.findChildren(JobCard):
            child.deleteLater()

        if not pipeline or not pipeline.jobs:
            self.setMinimumSize(400, 200)
            self.update()
            return

        self._layout_cards()

    def _layout_cards(self):
        p   = self._pipeline
        t   = self._t
        pad = 20
        col_w  = 180   # column width
        card_h = 64
        card_gap = 12
        stage_header_h = 32

        # Group jobs by stage
        stage_jobs: dict[str, list] = {s: [] for s in p.stages}
        for job in p.jobs.values():
            if job.stage in stage_jobs:
                stage_jobs[job.stage].append(job)
            else:
                # Stage not in stages list — add it
                stage_jobs.setdefault(job.stage, []).append(job)

        stages = [s for s in p.stages if stage_jobs.get(s)]

        total_w = pad + len(stages) * col_w + pad
        max_jobs = max((len(v) for v in stage_jobs.values()), default=1)
        total_h = pad + stage_header_h + max_jobs * (card_h + card_gap) + pad

        self.setMinimumSize(total_w, total_h)
        self.resize(total_w, total_h)

        for col_idx, stage in enumerate(stages):
            x = pad + col_idx * col_w
            for row_idx, job in enumerate(stage_jobs[stage]):
                y = pad + stage_header_h + row_idx * (card_h + card_gap)
                card = JobCard(job, t, self)
                card.move(x + 10, y)
                card.show()
                card.clicked.connect(self._on_card_clicked)
                self._cards[job.name] = card

        self.update()

    def _on_card_clicked(self, job: PipelineJob):
        # Deselect previous
        if self._selected and self._selected in self._cards:
            self._cards[self._selected].select(False)
        self._selected = job.name
        self._cards[job.name].select(True)
        self.job_selected.emit(job)
        self.update()

    def paintEvent(self, event):
        if not self._pipeline:
            painter = QPainter(self)
            t = self._t
            painter.setPen(QColor(t.get('fg4', '#a89984')))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             "No pipeline file found in this project.\n"
                             "Open a .gitlab-ci.yml or .github/workflows/*.yml file.")
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = self._t

        bg = QColor(t.get('bg0', '#282828'))
        painter.fillRect(self.rect(), bg)

        p      = self._pipeline
        pad    = 20
        col_w  = 180
        stage_header_h = 32

        # Stage column headers and separators
        stage_jobs: dict[str, list] = {s: [] for s in p.stages}
        for job in p.jobs.values():
            stage_jobs.setdefault(job.stage, []).append(job)
        stages = [s for s in p.stages if stage_jobs.get(s)]

        for col_idx, stage in enumerate(stages):
            x = pad + col_idx * col_w

            # Column background
            col_bg = QColor(t.get('bg1', '#3c3836'))
            col_bg.setAlpha(80)
            painter.fillRect(x, pad, col_w - 8,
                             self.height() - pad * 2, col_bg)

            # Stage header
            header_color = QColor(t.get('bg3', '#665c54'))
            painter.fillRect(x, pad, col_w - 8, stage_header_h, header_color)

            font = QFont()
            font.setPointSize(9)
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QColor(t.get('fg1', '#ebdbb2')))
            painter.drawText(QRect(x + 8, pad, col_w - 16, stage_header_h),
                             Qt.AlignmentFlag.AlignVCenter,
                             stage.upper())

        # Draw dependency arrows
        self._draw_arrows(painter, stages, stage_jobs)

    def _draw_arrows(self, painter: QPainter, stages: list,
                     stage_jobs: dict):
        t        = self._t
        arrow_color = QColor(t.get('aqua', '#689d6a'))
        arrow_color.setAlpha(160)
        pen = QPen(arrow_color, 1.5)
        pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
    
        def card_center_right(job_name):
            card = self._cards.get(job_name)
            if card:
                pos = card.pos()
                return QPoint(pos.x() + card.width(),
                              pos.y() + card.height() // 2)
            return None
    
        def card_center_left(job_name):
            card = self._cards.get(job_name)
            if card:
                pos = card.pos()
                return QPoint(pos.x(), pos.y() + card.height() // 2)
            return None
    
        p = self._pipeline
        for job in p.jobs.values():
            for need in job.needs:
                src = card_center_right(need)
                dst = card_center_left(job.name)
                if src and dst:
                    # Convert QPoint → QPointF for QPainterPath
                    sf = src.toPointF()
                    df = dst.toPointF()
                    ctrl_x = (sf.x() + df.x()) / 2
    
                    path = QPainterPath()
                    path.moveTo(sf)
                    path.cubicTo(
                        ctrl_x, sf.y(),
                        ctrl_x, df.y(),
                        df.x(), df.y(),
                    )
                    painter.drawPath(path)
    
                    # Arrowhead at dst
                    painter.setBrush(QBrush(arrow_color))
                    painter.setPen(Qt.PenStyle.NoPen)
                    ax, ay = dst.x(), dst.y()
                    painter.drawPolygon([
                        QPoint(ax,     ay),
                        QPoint(ax - 8, ay - 4),
                        QPoint(ax - 8, ay + 4),
                    ])
                    painter.setPen(pen)
                    painter.setBrush(Qt.BrushStyle.NoBrush)

    def _on_theme(self, t: dict):
        self._t = t
        for card in self._cards.values():
            card._t = t
            card._apply_style()
        self.update()


class PipelineViewerPanel(QDockWidget):

    jump_to_job = pyqtSignal(str, str)   # file_path, job_name

    def __init__(self, parent=None):
        super().__init__("Pipeline", parent)
        self.setObjectName("pipeline_viewer_dock")
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable  |
            QDockWidget.DockWidgetFeature.DockWidgetMovable   |
            QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )

        self._pipeline: Pipeline | None = None
        self._t = get_theme()

        self._build_ui()
        self._apply_theme(self._t)
        theme_signals.theme_changed.connect(self._apply_theme)

    def _build_ui(self):
        container = QWidget()
        main_layout = QVBoxLayout(container)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Header
        header = QWidget()
        header.setFixedHeight(32)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(8, 0, 4, 0)

        self._file_label = QLabel("No pipeline loaded")
        self._file_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        hl.addWidget(self._file_label)

        self._refresh_btn = QPushButton("↻")
        self._refresh_btn.setFixedSize(24, 22)
        self._refresh_btn.setToolTip("Reload pipeline file")
        self._refresh_btn.clicked.connect(self._refresh)
        hl.addWidget(self._refresh_btn)

        main_layout.addWidget(header)

        # Splitter — canvas top, detail bottom
        splitter = QSplitter(Qt.Orientation.Vertical)

        # Canvas in scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(False)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        self._canvas = PipelineCanvas()
        self._canvas.job_selected.connect(self._on_job_selected)
        scroll.setWidget(self._canvas)
        splitter.addWidget(scroll)

        # Detail panel
        self._detail = QTextEdit()
        self._detail.setReadOnly(True)
        self._detail.setMaximumHeight(160)
        self._detail.setPlaceholderText("Click a job to see details…")
        splitter.addWidget(self._detail)

        splitter.setSizes([300, 160])
        main_layout.addWidget(splitter)

        self.setWidget(container)

    def load_pipeline(self, pipeline, file_path: str = ""):
        self._pipeline  = pipeline
        self._file_path = file_path
        self._canvas.load_pipeline(pipeline)

        name = os.path.basename(file_path) if file_path else "pipeline"
        ptype = pipeline.type.value if pipeline else "unknown"
        jobs  = len(pipeline.jobs) if pipeline else 0
        self._file_label.setText(f"{name}  ·  {ptype}  ·  {jobs} jobs")

        if pipeline and pipeline.errors:
            self._detail.setPlainText(
                "Parse errors:\n" + "\n".join(pipeline.errors)
            )

    def _on_job_selected(self, job: PipelineJob):
        t = self._t
        lines = [
            f"<b style='color:{t.get('yellow','#d79921')}'>{job.name}</b>",
            f"<span style='color:{t.get('fg4','#a89984')}'>Stage: {job.stage}</span>",
        ]
        if job.image:
            lines.append(f"Image: <code>{job.image}</code>")
        if job.runs_on:
            lines.append(f"Runs on: <code>{job.runs_on}</code>")
        if job.uses:
            lines.append(f"Uses: <code>{job.uses}</code>")
        if job.environment:
            lines.append(f"Environment: <b>{job.environment}</b>")
        if job.needs:
            lines.append(f"Needs: {', '.join(job.needs)}")
        if job.tags:
            lines.append(f"Tags: {', '.join(job.tags)}")
        if job.is_manual:
            lines.append(f"<span style='color:{t.get('yellow','#d79921')}'>⚠ Manual trigger</span>")
        if job.allow_failure:
            lines.append(f"<span style='color:{t.get('orange','#d65d0e')}'>⚠ Allow failure</span>")
        if job.script:
            lines.append("<br><b>Steps:</b>")
            for s in job.script[:8]:
                lines.append(f"  • {s}")
            if len(job.script) > 8:
                lines.append(f"  … +{len(job.script) - 8} more")

        self._detail.setHtml(
            f"<div style='font-family:monospace;font-size:9pt;"
            f"color:{t.get('fg1','#ebdbb2')};padding:8px'>"
            + "<br>".join(lines) + "</div>"
        )

        # Emit jump signal
        if self._file_path:
            self.jump_to_job.emit(self._file_path, job.name)

    def _refresh(self):
        if hasattr(self, '_file_path') and self._file_path:
            from plugins.features.pipeline_viewer.parsers import detect_and_parse
            pipeline = detect_and_parse(self._file_path)
            if pipeline:
                self.load_pipeline(pipeline, self._file_path)

    def _apply_theme(self, t: dict):
        self._t = t
        self.setStyleSheet(build_dock_stylesheet(t))
        bg  = t.get('bg0', '#282828')
        fg  = t.get('fg1', '#ebdbb2')
        fg4 = t.get('fg4', '#a89984')
        self._detail.setStyleSheet(f"""
            QTextEdit {{
                background: {bg};
                color: {fg};
                border: none;
                border-top: 1px solid {t.get('bg3', '#665c54')};
            }}
        """)
        self._file_label.setStyleSheet(f"color: {fg4}; font-size: 9pt;")

    def closeEvent(self, event):
        try:
            theme_signals.theme_changed.disconnect(self._apply_theme)
        except (RuntimeError, TypeError):
            pass
        super().closeEvent(event)