"""
terminal_view.py

Custom paint widget for the VT100 terminal.
Renders the character grid with full color, cursor, and selection support.
Handles PTY I/O and keyboard input.
"""

import os
import pty
import fcntl
import termios
import struct

from PyQt6.QtWidgets import QWidget, QApplication, QScrollBar, QAbstractScrollArea
from PyQt6.QtGui import (
    QPainter, QColor, QFont, QFontMetrics,
    QKeyEvent, QMouseEvent, QPen, QBrush,
)
from PyQt6.QtCore import (
    Qt, QRect, QTimer, QSocketNotifier,
    pyqtSignal, QPoint,
)

from ui.theme import get_theme, theme_signals
from plugins.features.terminal.vt100 import VT100, ansi_color_to_rgb


# ── Default colors (Gruvbox dark) ─────────────────────────────────────────────

_DEFAULT_FG = 0xebdbb2
_DEFAULT_BG = 0x1d2021


def _rgb(value: int):
    return QColor(
        (value >> 16) & 0xff,
        (value >>  8) & 0xff,
         value        & 0xff,
    )


class TerminalView(QWidget):
    """
    Renders a VT100 grid and manages the PTY connection.

    Signals:
        data_received(str) — emitted with each chunk of output text,
                             used by the run analyzer plugin.
    """

    data_received = pyqtSignal(str)

    def __init__(self, cwd: str = None, clean_shell: bool = False, parent=None):
        super().__init__(parent)

        self._cwd         = cwd or os.getcwd()
        self._clean_shell = clean_shell
        self._master_fd   = None
        self._pid         = None
        self._notifier    = None

        # Font — monospace, same family as the editor
        from ui.theme import QFONT_CODE
        self._font = QFont(QFONT_CODE, 10)
        self._font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        self._font.setFixedPitch(True)
        self.setFont(self._font)

        fm           = QFontMetrics(self._font)
        self._cell_w = fm.horizontalAdvance('M')
        self._cell_h = fm.height()

        # Terminal grid — sized to widget later
        self._cols = 80
        self._rows = 24
        self._vt   = VT100(self._rows, self._cols)

        # Cursor blink
        self._cursor_visible = True
        self._blink_timer    = QTimer(self)
        self._blink_timer.setInterval(500)
        self._blink_timer.timeout.connect(self._blink_tick)
        self._blink_timer.start()

        # Selection
        self._sel_start: QPoint | None = None
        self._sel_end:   QPoint | None = None
        self._selecting  = False

        # Scrollback — list of row snapshots (list of Cell)
        self._scrollback:     list = []
        self._scrollback_max  = 5000
        self._scroll_offset   = 0   # lines scrolled back from bottom

        # Theme
        self._t = get_theme()
        theme_signals.theme_changed.connect(self._on_theme)

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setCursor(Qt.CursorShape.IBeamCursor)

        # Start shell after first paint
        QTimer.singleShot(0, self._start_shell)

    def event(self, event):
        from PyQt6.QtCore import QEvent
        # Handle key presses here before parent can intercept them
        if event.type() == QEvent.Type.KeyPress:
            self.keyPressEvent(event)
            return True
        return super().event(event)

    # ── Shell / PTY ───────────────────────────────────────────────────────

    def _start_shell(self):
        shell = os.environ.get('SHELL', '/bin/bash')
    
        if self._clean_shell:
            args = [shell, '--login', '--norc'] if 'bash' in shell \
                   else [shell, '--login', '--no-rcs']
        else:
            args = [shell, '-i']
    
        self._pid, self._master_fd = pty.fork()
    
        if self._pid == 0:
            os.chdir(self._cwd)
    
            winsize = struct.pack('HHHH', self._rows, self._cols, 0, 0)
            fcntl.ioctl(pty.STDOUT_FILENO, termios.TIOCSWINSZ, winsize)
    
            env = os.environ.copy()
            env['TERM']      = 'xterm-256color'
            env['COLORTERM'] = 'truecolor'
            env['COLUMNS']   = str(self._cols)
            env['LINES']     = str(self._rows)
    
            os.execvpe(shell, args, env)
            os._exit(1)
    
        # ── Parent ────────────────────────────────────────────────────
        flags = fcntl.fcntl(self._master_fd, fcntl.F_GETFL)
        fcntl.fcntl(self._master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
    
        # Set proper terminal attributes so readline works correctly
        try:
            attrs = termios.tcgetattr(self._master_fd)
            # Input flags
            attrs[0] |= (termios.ICRNL | termios.IXON)
            # Output flags  
            attrs[1] |= termios.OPOST | termios.ONLCR
            # Control flags
            attrs[2] |= termios.CS8
            # Local flags — the critical ones for readline
            attrs[3] |= (
                termios.ECHO   |   # echo input chars
                termios.ECHOE  |   # echo erase as BS SP BS
                termios.ECHOK  |   # echo kill
                termios.ICANON |   # canonical mode (readline)
                termios.ISIG   |   # enable signals (Ctrl+C etc)
                termios.IEXTEN     # extended processing
            )
            # Special chars
            attrs[6][termios.VMIN]  = 1
            attrs[6][termios.VTIME] = 0
            termios.tcsetattr(self._master_fd, termios.TCSANOW, attrs)
        except termios.error as e:
            print(f"[terminal] tcsetattr failed: {e}")
    
        self._resize_pty()
    
        self._notifier = QSocketNotifier(
            self._master_fd,
            QSocketNotifier.Type.Read,
            self,
        )
        self._notifier.activated.connect(self._on_pty_output)
    
        QTimer.singleShot(100, self._drain)
        QTimer.singleShot(300, self._drain)
        QTimer.singleShot(600, self._drain)
        
    def _drain(self):
        """Read any pending PTY output — used to catch the initial prompt."""
        if self._master_fd is None:
            return
        import select
        try:
            ready, _, _ = select.select([self._master_fd], [], [], 0)
            if ready:
                self._on_pty_output()
        except (OSError, ValueError):
            pass

    def _resize_pty(self):
        if self._master_fd is None:
            return
        try:
            winsize = struct.pack('HHHH', self._rows, self._cols, 0, 0)
            fcntl.ioctl(self._master_fd, termios.TIOCSWINSZ, winsize)
        except OSError:
            pass

    # ── PTY output ────────────────────────────────────────────────────────

    def _on_pty_output(self):
        try:
            data = os.read(self._master_fd, 4096)
        except OSError:
            if self._notifier:
                self._notifier.setEnabled(False)
            return
    
        # Strip readline prompt width markers — both raw bytes and literal strings
        data = data.replace(b'\x01', b'').replace(b'\x02', b'')
    
        # Also strip literal \[ and \] that some prompts output
        data = data.replace(b'\\[', b'').replace(b'\\]', b'')
    
        self._vt.process(data)
    
        try:
            self.data_received.emit(data.decode('utf-8', errors='replace'))
        except Exception:
            pass
    
        if self._vt.dirty:
            self._vt.dirty = False
            self.update()

    # ── Scrollback ────────────────────────────────────────────────────────

    def wheelEvent(self, event):
        delta  = event.angleDelta().y()
        lines  = delta // 40
        max_scroll = len(self._vt.scrollback)
        self._scroll_offset = max(0, min(max_scroll, self._scroll_offset + lines))
        self.update()
        event.accept()

    # ── Painting ──────────────────────────────────────────────────────────

    def _get_display_cell(self, row: int, col: int):
        """
        Return the cell to display at (row, col) accounting for scroll offset.
        When scrolled back, rows come from scrollback buffer.
        """
        from plugins.features.terminal.vt100 import Cell
        scrollback = self._vt.scrollback
        sb_len     = len(scrollback)
        offset     = self._scroll_offset
    
        if offset > 0:
            # First 'offset' rows come from scrollback (if available)
            sb_start = sb_len - offset
            sb_row   = sb_start + row
            if 0 <= sb_row < sb_len:
                row_cells = scrollback[sb_row]
                if col < len(row_cells):
                    return row_cells[col]
                return Cell()
            else:
                # Past the scrollback — show screen rows
                screen_row = row - min(offset, sb_len)
                if 0 <= screen_row < self._rows:
                    return self._vt.screen.cell(screen_row, col)
                return Cell()
        else:
            return self._vt.screen.cell(row, col)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setFont(self._font)
    
        t      = self._t
        def_fg = _rgb(_DEFAULT_FG)
        def_bg = _rgb(int(t.get('bg0_hard', '#1d2021').lstrip('#'), 16))
    
        painter.fillRect(self.rect(), def_bg)
    
        cw = self._cell_w
        ch = self._cell_h
    
        for row in range(self._rows):
            for col in range(self._cols):
                cell = self._get_display_cell(row, col)
    
                fg = self._resolve_color(cell.fg, def_fg, cell.bold)
                bg = self._resolve_color(cell.bg, def_bg, False)
    
                if cell.reverse:
                    fg, bg = bg, fg
    
                x = col * cw
                y = row * ch
    
                if bg != def_bg:
                    painter.fillRect(x, y, cw, ch, bg)
    
                if cell.char != ' ':
                    f = QFont(self._font)
                    if cell.bold:
                        f.setBold(True)
                    if cell.underline:
                        f.setUnderline(True)
                    if cell.dim:
                        fg = QColor(fg.red(), fg.green(), fg.blue(), 128)
                    painter.setFont(f)
                    painter.setPen(fg)
                    painter.drawText(
                        x, y + QFontMetrics(f).ascent(),
                        cell.char
                    )
    
        # Cursor — only when not scrolled back
        if self._scroll_offset == 0 and self._cursor_visible and self._vt._cursor_visible:
            cr     = self._vt.cursor_row
            cc     = self._vt.cursor_col
            cx     = cc * cw
            cy     = cr * ch
            accent = QColor(t.get('accent', '#fabd2f'))
            painter.fillRect(cx, cy, cw, ch, accent)
            cell = self._vt.screen.cell(cr, cc)
            if cell.char != ' ':
                painter.setPen(def_bg)
                painter.setFont(self._font)
                painter.drawText(
                    cx, cy + QFontMetrics(self._font).ascent(),
                    cell.char
                )
    
        # Scrollback indicator — outside the cursor block
        if self._scroll_offset > 0:
            indicator = f" ↑ {self._scroll_offset} lines "
            painter.fillRect(
                0, 0, len(indicator) * cw, ch,
                QColor(t.get('accent', '#fabd2f'))
            )
            painter.setPen(def_bg)
            painter.setFont(self._font)
            painter.drawText(0, QFontMetrics(self._font).ascent(), indicator)
    
        # Selection — always drawn, outside everything else
        self._paint_selection(painter, cw, ch)

    def _resolve_color(self, index: int, default: QColor,
                       bold: bool) -> QColor:
        if index == -1:
            return default
        if index & 0x1000000:
            # True color
            return _rgb(index & 0xffffff)
        if index >= 256:
            return _rgb(ansi_color_to_rgb(index - 256))
        return _rgb(ansi_color_to_rgb(index))

    def _paint_selection(self, painter: QPainter, cw: int, ch: int):
        if self._sel_start is None or self._sel_end is None:
            return
        r1, c1 = self._sel_start.y(), self._sel_start.x()
        r2, c2 = self._sel_end.y(),   self._sel_end.x()
        if (r1, c1) > (r2, c2):
            r1, c1, r2, c2 = r2, c2, r1, c1

        sel_color = QColor(self._t.get('accent', '#fabd2f'))
        sel_color.setAlpha(80)

        for row in range(r1, r2 + 1):
            col_start = c1 if row == r1 else 0
            col_end   = c2 if row == r2 else self._cols - 1
            painter.fillRect(
                col_start * cw, row * ch,
                (col_end - col_start + 1) * cw, ch,
                sel_color,
            )

    # ── Cursor blink ──────────────────────────────────────────────────────

    def _blink_tick(self):
        self._cursor_visible = not self._cursor_visible
        self.update()

    # ── Resize ────────────────────────────────────────────────────────────

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w = self.width()
        h = self.height()
        if self._cell_w > 0 and self._cell_h > 0:
            new_cols = max(10, w // self._cell_w)
            new_rows = max(4,  h // self._cell_h)
            if new_cols != self._cols or new_rows != self._rows:
                self._cols = new_cols
                self._rows = new_rows
                self._vt.resize(new_rows, new_cols)
                self._resize_pty()
                self.update()

    # ── Keyboard input ────────────────────────────────────────────────────

    def keyPressEvent(self, event: QKeyEvent):
        if self._master_fd is None:
            return

        # Reset blink on keypress
        self._cursor_visible = True
        self._blink_timer.start()

        # Scroll back to bottom on any keypress
        self._scroll_offset = 0

        key  = event.key()
        mods = event.modifiers()
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)

        data = None

        # ── Ctrl+Shift shortcuts (don't send to PTY) ──────────────────
        if ctrl and shift:
            if key == Qt.Key.Key_C:
                self._copy_selection()
                return
            if key == Qt.Key.Key_V:
                self._paste()
                return

        # ── Ctrl sequences ────────────────────────────────────────────
        if ctrl and not shift:
            ctrl_map = {
                Qt.Key.Key_At:        b'\x00',
                Qt.Key.Key_A:         b'\x01',
                Qt.Key.Key_B:         b'\x02',
                Qt.Key.Key_C:         b'\x03',
                Qt.Key.Key_D:         b'\x04',
                Qt.Key.Key_E:         b'\x05',
                Qt.Key.Key_F:         b'\x06',
                Qt.Key.Key_G:         b'\x07',
                Qt.Key.Key_H:         b'\x08',
                Qt.Key.Key_I:         b'\x09',
                Qt.Key.Key_J:         b'\x0a',
                Qt.Key.Key_K:         b'\x0b',
                Qt.Key.Key_L:         b'\x0c',
                Qt.Key.Key_M:         b'\x0d',
                Qt.Key.Key_N:         b'\x0e',
                Qt.Key.Key_O:         b'\x0f',
                Qt.Key.Key_P:         b'\x10',
                Qt.Key.Key_Q:         b'\x11',
                Qt.Key.Key_R:         b'\x12',
                Qt.Key.Key_S:         b'\x13',
                Qt.Key.Key_T:         b'\x14',
                Qt.Key.Key_U:         b'\x15',
                Qt.Key.Key_V:         b'\x16',
                Qt.Key.Key_W:         b'\x17',
                Qt.Key.Key_X:         b'\x18',
                Qt.Key.Key_Y:         b'\x19',
                Qt.Key.Key_Z:         b'\x1a',
                Qt.Key.Key_BracketLeft:  b'\x1b',
                Qt.Key.Key_Backslash:    b'\x1c',
                Qt.Key.Key_BracketRight: b'\x1d',
                Qt.Key.Key_AsciiCircum:  b'\x1e',
                Qt.Key.Key_Underscore:   b'\x1f',
            }
            data = ctrl_map.get(key)
            if data:
                self._write(data)
                return

        # ── Special keys ──────────────────────────────────────────────
        app_keys = getattr(self._vt, '_app_cursor_keys', False)
        
        if app_keys:
            special = {
                Qt.Key.Key_Return:    b'\r',
                Qt.Key.Key_Enter:     b'\r',
                Qt.Key.Key_Backspace: b'\x7f',
                Qt.Key.Key_Tab:       b'\t',
                Qt.Key.Key_Escape:    b'\x1b',
                Qt.Key.Key_Up:        b'\x1bOA',
                Qt.Key.Key_Down:      b'\x1bOB',
                Qt.Key.Key_Right:     b'\x1bOC',
                Qt.Key.Key_Left:      b'\x1bOD',
                Qt.Key.Key_Home:      b'\x1bOH',
                Qt.Key.Key_End:       b'\x1bOF',
                Qt.Key.Key_Delete:    b'\x1b[3~',
                Qt.Key.Key_Insert:    b'\x1b[2~',
                Qt.Key.Key_PageUp:    b'\x1b[5~',
                Qt.Key.Key_PageDown:  b'\x1b[6~',
                Qt.Key.Key_F1:        b'\x1bOP',
                Qt.Key.Key_F2:        b'\x1bOQ',
                Qt.Key.Key_F3:        b'\x1bOR',
                Qt.Key.Key_F4:        b'\x1bOS',
                Qt.Key.Key_F5:        b'\x1b[15~',
                Qt.Key.Key_F6:        b'\x1b[17~',
                Qt.Key.Key_F7:        b'\x1b[18~',
                Qt.Key.Key_F8:        b'\x1b[19~',
                Qt.Key.Key_F9:        b'\x1b[20~',
                Qt.Key.Key_F10:       b'\x1b[21~',
                Qt.Key.Key_F11:       b'\x1b[23~',
                Qt.Key.Key_F12:       b'\x1b[24~',
            }
        else:
            special = {
                Qt.Key.Key_Return:    b'\r',
                Qt.Key.Key_Enter:     b'\r',
                Qt.Key.Key_Backspace: b'\x7f',
                Qt.Key.Key_Tab:       b'\t',
                Qt.Key.Key_Escape:    b'\x1b',
                Qt.Key.Key_Up:        b'\x1b[A',
                Qt.Key.Key_Down:      b'\x1b[B',
                Qt.Key.Key_Right:     b'\x1b[C',
                Qt.Key.Key_Left:      b'\x1b[D',
                Qt.Key.Key_Home:      b'\x1b[H',
                Qt.Key.Key_End:       b'\x1b[F',
                Qt.Key.Key_Delete:    b'\x1b[3~',
                Qt.Key.Key_Insert:    b'\x1b[2~',
                Qt.Key.Key_PageUp:    b'\x1b[5~',
                Qt.Key.Key_PageDown:  b'\x1b[6~',
                Qt.Key.Key_F1:        b'\x1bOP',
                Qt.Key.Key_F2:        b'\x1bOQ',
                Qt.Key.Key_F3:        b'\x1bOR',
                Qt.Key.Key_F4:        b'\x1bOS',
                Qt.Key.Key_F5:        b'\x1b[15~',
                Qt.Key.Key_F6:        b'\x1b[17~',
                Qt.Key.Key_F7:        b'\x1b[18~',
                Qt.Key.Key_F8:        b'\x1b[19~',
                Qt.Key.Key_F9:        b'\x1b[20~',
                Qt.Key.Key_F10:       b'\x1b[21~',
                Qt.Key.Key_F11:       b'\x1b[23~',
                Qt.Key.Key_F12:       b'\x1b[24~',
            }
        data = special.get(key)
        if data:
            self._write(data)
            return

        # ── Printable text ────────────────────────────────────────────
        text = event.text()
        if text:
            self._write(text.encode('utf-8'))

    def _write(self, data: bytes):
        if self._master_fd is None:
            return
        try:
            os.write(self._master_fd, data)
        except OSError:
            pass

    # ── Mouse / selection ─────────────────────────────────────────────────

    def mousePressEvent(self, event: QMouseEvent):
        self.setFocus()
        if event.button() == Qt.MouseButton.LeftButton:
            self._sel_start = self._pixel_to_cell(event.pos())
            self._sel_end   = self._sel_start
            self._selecting = True
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._selecting:
            self._sel_end = self._pixel_to_cell(event.pos())
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._selecting = False
            # Single click with no drag — clear selection
            if self._sel_start == self._sel_end:
                self._sel_start = None
                self._sel_end   = None
                self.update()

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        """Select the word under the cursor."""
        cell = self._pixel_to_cell(event.pos())
        row, col = cell.y(), cell.x()
        line = self._vt.get_line_text(row)
        # Find word boundaries
        start = col
        end   = col
        while start > 0 and (line[start - 1].isalnum() or line[start - 1] in '_-.'):
            start -= 1
        while end < len(line) - 1 and (line[end].isalnum() or line[end] in '_-.'):
            end += 1
        self._sel_start = QPoint(start, row)
        self._sel_end   = QPoint(end,   row)
        self.update()

    def _pixel_to_cell(self, pos) -> QPoint:
        col = max(0, min(self._cols - 1, pos.x() // self._cell_w))
        row = max(0, min(self._rows - 1, pos.y() // self._cell_h))
        return QPoint(col, row)

    def _get_selected_text(self) -> str:
        if self._sel_start is None or self._sel_end is None:
            return ''
        r1, c1 = self._sel_start.y(), self._sel_start.x()
        r2, c2 = self._sel_end.y(),   self._sel_end.x()
        if (r1, c1) > (r2, c2):
            r1, c1, r2, c2 = r2, c2, r1, c1
        lines = []
        for row in range(r1, r2 + 1):
            line = self._vt.get_line_text(row)
            col_start = c1 if row == r1 else 0
            col_end   = c2 if row == r2 else len(line)
            lines.append(line[col_start:col_end])
        return '\n'.join(lines)

    def _copy_selection(self):
        text = self._get_selected_text()
        if text:
            QApplication.clipboard().setText(text)

    def _paste(self):
        text = QApplication.clipboard().text()
        if text:
            # Bracketed paste if supported
            self._write(('\x1b[200~' + text + '\x1b[201~').encode('utf-8'))

    # ── Public API ────────────────────────────────────────────────────────

    def set_cwd(self, path: str):
        if os.path.isdir(path) and self._master_fd is not None:
            self._write(f'cd {path}\n'.encode())

    def restart(self):
        self._cleanup()
        self._vt = VT100(self._rows, self._cols)
        self._start_shell()
        self.update()

    def apply_styles(self, t: dict):
        self._t = t
        self.update()

    # ── Theme ─────────────────────────────────────────────────────────────

    def _on_theme(self, t: dict):
        self._t = t
        self.update()

    # ── Cleanup ───────────────────────────────────────────────────────────

    def _cleanup(self):
        self._blink_timer.stop()
        if self._notifier:
            self._notifier.setEnabled(False)
            self._notifier = None
        if self._master_fd is not None:
            try:
                os.close(self._master_fd)
            except OSError:
                pass
            self._master_fd = None
        if self._pid is not None:
            try:
                os.waitpid(self._pid, os.WNOHANG)
            except ChildProcessError:
                pass
            self._pid = None

    def closeEvent(self, event):
        self._cleanup()
        super().closeEvent(event)

    def __del__(self):
        try:
            self._cleanup()
        except Exception:
            pass