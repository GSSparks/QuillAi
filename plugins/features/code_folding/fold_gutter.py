"""
fold_gutter.py

Painting and click handling for the fold marker column.
Integrates with GhostEditor's existing LineNumberArea.
"""

from PyQt6.QtGui import QPainter, QColor, QPen, QFontMetrics
from PyQt6.QtCore import Qt, QRect


FOLD_GUTTER_WIDTH = 16  # px — sits to the left of line numbers


def paint_fold_gutter(painter: QPainter,
                      editor,
                      fold_manager,
                      event_rect,
                      crumb_h: int):
    """
    Paint fold markers into the fold gutter column.
    Called from line_number_area_paint_event.

    Draws:
      [+]  at the start of a folded region
      [-]  at the start of an expanded region  (top of vertical line)
           a vertical line along the region body
           └  a small end cap at the bottom of the region
    """
    t        = editor._t
    fg       = QColor(t.get('fg4',     '#a89984'))
    border   = QColor(t.get('border',  '#504945'))
    accent   = QColor(t.get('accent',  '#fabd2f'))

    fm      = editor.fontMetrics()
    fm_h    = fm.height()
    offset  = editor.contentOffset()

    block        = editor.firstVisibleBlock()
    block_number = block.blockNumber()
    top    = round(editor.blockBoundingGeometry(block).translated(offset).top()) + crumb_h
    bottom = top + round(editor.blockBoundingRect(block).height())

    # Precompute which lines are visible and their y coords
    line_tops: dict[int, int] = {}
    b = block
    bn = block_number
    t_y = top
    b_y = bottom
    while b.isValid() and t_y <= event_rect.bottom():
        if b.isVisible():
            line_tops[bn] = t_y
        b    = b.next()
        t_y  = b_y
        b_y  = t_y + round(editor.blockBoundingRect(b).height())
        bn  += 1

    gutter_x = 0   # fold gutter is the leftmost column

    for start, end in fold_manager.regions:
        folded     = fold_manager.is_folded(start)
        start_y    = line_tops.get(start)

        if start_y is None:
            continue

        # ── Draw [+] or [-] box at the start line ─────────────────────
        box_size = 10
        box_x    = gutter_x + (FOLD_GUTTER_WIDTH - box_size) // 2
        box_y    = start_y + (fm_h - box_size) // 2

        pen = QPen(fg)
        pen.setWidth(1)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(box_x, box_y, box_size, box_size)

        # + or - sign inside the box
        mid_x = box_x + box_size // 2
        mid_y = box_y + box_size // 2
        painter.drawLine(box_x + 2, mid_y, box_x + box_size - 2, mid_y)  # horizontal
        if folded:
            painter.drawLine(mid_x, box_y + 2, mid_x, box_y + box_size - 2)  # vertical

        if not folded:
            # ── Draw vertical line down the region body ────────────────
            line_x   = gutter_x + FOLD_GUTTER_WIDTH // 2
            line_top = start_y + fm_h

            # Find the y of the end line (may be off-screen)
            end_y = line_tops.get(end)
            if end_y is None:
                # Region extends below visible area — draw to bottom of event rect
                line_bottom = event_rect.bottom()
                draw_end_cap = False
            else:
                line_bottom  = end_y + fm_h // 2
                draw_end_cap = True

            pen2 = QPen(border)
            pen2.setWidth(1)
            painter.setPen(pen2)
            painter.drawLine(line_x, line_top, line_x, line_bottom)

            # └ end cap
            if draw_end_cap:
                painter.drawLine(line_x, line_bottom,
                                 line_x + FOLD_GUTTER_WIDTH // 2 - 1, line_bottom)


def fold_line_at_y(editor, fold_manager, y: int, crumb_h: int) -> int | None:
    """
    Given a y coordinate in the LineNumberArea, return the block number
    of the fold region start under that y, or None.
    Only hits within the FOLD_GUTTER_WIDTH column count.
    """
    y -= crumb_h
    if y < 0:
        return None

    offset = editor.contentOffset()
    block  = editor.firstVisibleBlock()
    bn     = block.blockNumber()
    top    = round(editor.blockBoundingGeometry(block).translated(offset).top())
    bottom = top + round(editor.blockBoundingRect(block).height())

    while block.isValid():
        if block.isVisible() and top <= y <= bottom:
            if fold_manager.is_fold_start(bn):
                return bn
            return None
        if top > y:
            return None
        block  = block.next()
        bn    += 1
        top    = bottom
        bottom = top + round(editor.blockBoundingRect(block).height())

    return None