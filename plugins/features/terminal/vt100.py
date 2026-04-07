"""
vt100.py

VT100/ANSI terminal state machine and character grid for QuillAI.

Handles:
  - Printable characters
  - Cursor movement (absolute, relative)
  - Erase line / erase display
  - SGR colors and attributes (bold, dim, underline, reverse)
  - Alternate screen buffer (for vim, htop, etc)
  - Scrolling regions
  - Basic terminal modes
"""

from dataclasses import dataclass, field
from typing import Optional


# ── Cell ─────────────────────────────────────────────────────────────────────

@dataclass
class Cell:
    """One character cell in the terminal grid."""
    char:       str  = ' '
    fg:         int  = -1    # -1 = default
    bg:         int  = -1    # -1 = default
    bold:       bool = False
    dim:        bool = False
    underline:  bool = False
    reverse:    bool = False
    blink:      bool = False

    def reset(self):
        self.char      = ' '
        self.fg        = -1
        self.bg        = -1
        self.bold      = False
        self.dim       = False
        self.underline = False
        self.reverse   = False
        self.blink     = False

    def copy_attrs(self, other: 'Cell'):
        """Copy visual attributes but not the character."""
        self.fg        = other.fg
        self.bg        = other.bg
        self.bold      = other.bold
        self.dim       = other.dim
        self.underline = other.underline
        self.reverse   = other.reverse
        self.blink     = other.blink


# ── SGR color table ───────────────────────────────────────────────────────────

# Standard 8 colors (normal and bright)
_ANSI_COLORS = [
    # Normal
    0x282828,  # 0  black   (gruvbox bg)
    0xcc241d,  # 1  red
    0x98971a,  # 2  green
    0xd79921,  # 3  yellow
    0x458588,  # 4  blue
    0xb16286,  # 5  magenta
    0x689d6a,  # 6  cyan
    0xa89984,  # 7  white
    # Bright
    0x928374,  # 8  bright black
    0xfb4934,  # 9  bright red
    0xb8bb26,  # 10 bright green
    0xfabd2f,  # 11 bright yellow
    0x83a598,  # 12 bright blue
    0xd3869b,  # 13 bright magenta
    0x8ec07c,  # 14 bright cyan
    0xebdbb2,  # 15 bright white
]


def ansi_color_to_rgb(index: int) -> int:
    """Convert an ANSI color index to an RGB int."""
    if 0 <= index <= 15:
        return _ANSI_COLORS[index]

    if 16 <= index <= 231:
        # 6x6x6 color cube
        index -= 16
        b = index % 6
        g = (index // 6) % 6
        r = index // 36
        to_byte = lambda v: 0 if v == 0 else 55 + v * 40
        return (to_byte(r) << 16) | (to_byte(g) << 8) | to_byte(b)

    if 232 <= index <= 255:
        # Grayscale ramp
        v = 8 + (index - 232) * 10
        return (v << 16) | (v << 8) | v

    return 0xebdbb2  # fallback


# ── Screen buffer ─────────────────────────────────────────────────────────────

class Screen:
    """
    A 2D grid of Cells representing one terminal screen.
    Rows and columns are 0-indexed internally.
    """

    def __init__(self, rows: int, cols: int):
        self.rows = rows
        self.cols = cols
        self._cells: list[list[Cell]] = [
            [Cell() for _ in range(cols)]
            for _ in range(rows)
        ]

    def cell(self, row: int, col: int) -> Cell:
        row = max(0, min(self.rows - 1, row))
        col = max(0, min(self.cols - 1, col))
        return self._cells[row][col]

    def resize(self, rows: int, cols: int):
        # Grow or shrink — preserve existing content
        new_cells = [
            [Cell() for _ in range(cols)]
            for _ in range(rows)
        ]
        for r in range(min(rows, self.rows)):
            for c in range(min(cols, self.cols)):
                src = self._cells[r][c]
                dst = new_cells[r][c]
                dst.char      = src.char
                dst.fg        = src.fg
                dst.bg        = src.bg
                dst.bold      = src.bold
                dst.dim       = src.dim
                dst.underline = src.underline
                dst.reverse   = src.reverse
        self.rows   = rows
        self.cols   = cols
        self._cells = new_cells

    def scroll_up(self, top: int, bottom: int, attrs: Cell,
                  scrollback: list = None, scrollback_max: int = 5000):
        """Scroll lines [top..bottom] up by one, blank the bottom line.
        If scrollback is provided and top==0, save the evicted line."""
        if scrollback is not None and top == 0:
            # Save the line being scrolled off
            saved = [Cell() for _ in range(self.cols)]
            for c in range(self.cols):
                src = self._cells[top][c]
                saved[c].char      = src.char
                saved[c].fg        = src.fg
                saved[c].bg        = src.bg
                saved[c].bold      = src.bold
                saved[c].dim       = src.dim
                saved[c].underline = src.underline
                saved[c].reverse   = src.reverse
            scrollback.append(saved)
            if len(scrollback) > scrollback_max:
                scrollback.pop(0)
    
        for r in range(top, bottom):
            self._cells[r] = self._cells[r + 1]
        self._cells[bottom] = [Cell() for _ in range(self.cols)]
        for c in self._cells[bottom]:
            c.copy_attrs(attrs)

    def scroll_down(self, top: int, bottom: int, attrs: Cell):
        """Scroll lines [top..bottom] down by one, blank the top line."""
        for r in range(bottom, top, -1):
            self._cells[r] = self._cells[r - 1]
        self._cells[top] = [Cell() for _ in range(self.cols)]
        for c in self._cells[top]:
            c.copy_attrs(attrs)

    def erase_line(self, row: int, col_start: int, col_end: int, attrs: Cell):
        for c in range(col_start, min(col_end + 1, self.cols)):
            cell = self._cells[row][c]
            cell.reset()
            cell.copy_attrs(attrs)

    def erase_display(self, row_start: int, row_end: int, attrs: Cell):
        for r in range(row_start, min(row_end + 1, self.rows)):
            self.erase_line(r, 0, self.cols - 1, attrs)

    def clear(self):
        for r in range(self.rows):
            for c in range(self.cols):
                self._cells[r][c].reset()


# ── VT100 state machine ───────────────────────────────────────────────────────

class VT100:
    """
    Parses a byte stream and updates a Screen accordingly.
    Feed data with process(data: bytes).
    Read state via .screen, .cursor_row, .cursor_col, .dirty.
    """

    # Parser states
    _STATE_NORMAL   = 0
    _STATE_ESC      = 1   # received \x1b
    _STATE_CSI      = 2   # received \x1b[
    _STATE_OSC      = 3   # received \x1b]
    _STATE_CHARSET  = 4   # received \x1b( or \x1b)

    def __init__(self, rows: int = 24, cols: int = 80):
        self.rows = rows
        self.cols = cols

        # Two screen buffers — normal and alternate (for vim/htop)
        self._normal_screen    = Screen(rows, cols)
        self._alternate_screen = Screen(rows, cols)
        self.screen            = self._normal_screen
        self._alt_active       = False

        # Cursor
        self.cursor_row  = 0
        self.cursor_col  = 0
        self._saved_row  = 0
        self._saved_col  = 0
        
        self._app_cursor_keys = False

        # Current SGR attributes (template cell)
        self._attrs = Cell()

        # Scroll region — default is full screen
        self._scroll_top    = 0
        self._scroll_bottom = rows - 1
        
        # Scrollback buffer — list of saved rows (oldest first)
        self.scrollback:     list = []
        self.scrollback_max: int  = 5000

        # Parser state
        self._state    = self._STATE_NORMAL
        self._params   = []    # CSI parameter accumulator
        self._cur_param = ''   # current digit string

        # Dirty flag — set True whenever screen changes
        self.dirty = False

        # Modes
        self._insert_mode    = False
        self._auto_wrap      = True
        self._origin_mode    = False
        self._cursor_visible = True

        # Line feed mode
        self._lnm = False   # if True, LF also does CR

    # ── Public ────────────────────────────────────────────────────────────

    def resize(self, rows: int, cols: int):
        self.rows = rows
        self.cols = cols
        self._normal_screen.resize(rows, cols)
        self._alternate_screen.resize(rows, cols)
        self._scroll_top    = 0
        self._scroll_bottom = rows - 1
        self.cursor_row = min(self.cursor_row, rows - 1)
        self.cursor_col = min(self.cursor_col, cols - 1)
        self.dirty = True

    def process(self, data: bytes):
        """Feed raw bytes from the PTY into the state machine."""
        text = data.decode('utf-8', errors='replace')
        for ch in text:
            self._dispatch(ch)

    # ── Dispatcher ────────────────────────────────────────────────────────

    def _dispatch(self, ch: str):
        s = self._state

        if s == self._STATE_NORMAL:
            self._handle_normal(ch)
        elif s == self._STATE_ESC:
            self._handle_esc(ch)
        elif s == self._STATE_CSI:
            self._handle_csi(ch)
        elif s == self._STATE_OSC:
            self._handle_osc(ch)
        elif s == self._STATE_CHARSET:
            # Ignore charset designation — just return to normal
            self._state = self._STATE_NORMAL

    # ── Normal state ──────────────────────────────────────────────────────

    def _handle_normal(self, ch: str):
        o = ord(ch)
    
        if o == 0x1b:    # ESC
            self._state = self._STATE_ESC
        elif o == 0x00:  # NUL — ignore
            pass
        elif o == 0x01 or o == 0x02:  # SOH/STX — readline prompt markers
            pass
        elif o == 0x07:  # BEL — ignore
            pass
        elif o == 0x08:  # BS
            if self.cursor_col > 0:
                self.cursor_col -= 1
                self.dirty = True
        elif o == 0x09:  # HT (tab)
            self.cursor_col = min(
                self.cols - 1,
                (self.cursor_col // 8 + 1) * 8
            )
            self.dirty = True
        elif o == 0x0a or o == 0x0b or o == 0x0c:  # LF / VT / FF
            self._linefeed()
        elif o == 0x0d:  # CR
            self.cursor_col = 0
            self.dirty = True
        elif o == 0x0e or o == 0x0f:  # SO/SI charset — ignore
            pass
        elif o == 0x7f:  # DEL — backspace
            if self.cursor_col > 0:
                self.cursor_col -= 1
                # Erase the cell we backed over
                cell = self.screen.cell(self.cursor_row, self.cursor_col)
                cell.reset()
                cell.copy_attrs(self._attrs)
                self.dirty = True
        elif 0x20 <= o < 0x7f or o >= 0xa0:  # Printable
            self._put_char(ch)

    # ── ESC state ─────────────────────────────────────────────────────────

    def _handle_esc(self, ch: str):
        self._state = self._STATE_NORMAL

        if ch == '[':
            self._state     = self._STATE_CSI
            self._params    = []
            self._cur_param = ''
            self._csi_priv  = False
        elif ch == ']':
            self._state    = self._STATE_OSC
            self._osc_buf  = ''
        elif ch in ('(', ')'):
            self._state = self._STATE_CHARSET
        elif ch == '7':   # Save cursor
            self._saved_row = self.cursor_row
            self._saved_col = self.cursor_col
        elif ch == '8':   # Restore cursor
            self.cursor_row = self._saved_row
            self.cursor_col = self._saved_col
            self.dirty = True
        elif ch == 'M':   # Reverse index (scroll down)
            if self.cursor_row == self._scroll_top:
                self.screen.scroll_down(
                    self._scroll_top, self._scroll_bottom, self._attrs
                )
            else:
                self.cursor_row = max(0, self.cursor_row - 1)
            self.dirty = True
        elif ch == 'D':   # Index (scroll up)
            self._linefeed()
        elif ch == 'E':   # Next line
            self.cursor_col = 0
            self._linefeed()
        elif ch == 'c':   # Full reset
            self._full_reset()

    # ── CSI state ─────────────────────────────────────────────────────────

    def _handle_csi(self, ch: str):
        if ch == '?':
            self._csi_priv = True
            return
        if ch.isdigit() or ch == ';':
            if ch == ';':
                try:
                    self._params.append(int(self._cur_param) if self._cur_param else 0)
                except ValueError:
                    self._params.append(0)
                self._cur_param = ''
            else:
                self._cur_param += ch
            return

        # Final byte — flush last param and dispatch
        try:
            self._params.append(int(self._cur_param) if self._cur_param else 0)
        except ValueError:
            self._params.append(0)
        self._cur_param = ''

        params    = self._params
        priv      = getattr(self, '_csi_priv', False)
        self._state    = self._STATE_NORMAL
        self._csi_priv = False

        self._exec_csi(ch, params, priv)

    def _exec_csi(self, cmd: str, params: list, priv: bool):
        p = params

        def P(i, default=0):
            v = p[i] if i < len(p) else 0
            return v if v != 0 else default

        if cmd == 'A':   # Cursor up
            self.cursor_row = max(self._scroll_top,
                                  self.cursor_row - P(0, 1))
            self.dirty = True

        elif cmd == 'B' or cmd == 'e':  # Cursor down
            self.cursor_row = min(self._scroll_bottom,
                                  self.cursor_row + P(0, 1))
            self.dirty = True

        elif cmd == 'C' or cmd == 'a':  # Cursor right
            self.cursor_col = min(self.cols - 1,
                                  self.cursor_col + P(0, 1))
            self.dirty = True

        elif cmd == 'D':  # Cursor left
            self.cursor_col = max(0, self.cursor_col - P(0, 1))
            self.dirty = True

        elif cmd == 'E':  # Cursor next line
            self.cursor_row = min(self._scroll_bottom,
                                  self.cursor_row + P(0, 1))
            self.cursor_col = 0
            self.dirty = True

        elif cmd == 'F':  # Cursor previous line
            self.cursor_row = max(self._scroll_top,
                                  self.cursor_row - P(0, 1))
            self.cursor_col = 0
            self.dirty = True

        elif cmd == 'G' or cmd == '`':  # Cursor horizontal absolute
            self.cursor_col = min(self.cols - 1, max(0, P(0, 1) - 1))
            self.dirty = True

        elif cmd == 'H' or cmd == 'f':  # Cursor position
            self.cursor_row = min(self.rows - 1, max(0, P(0, 1) - 1))
            self.cursor_col = min(self.cols - 1, max(0, P(1, 1) - 1))
            self.dirty = True

        elif cmd == 'J':  # Erase display
            n = P(0, 0)
            if n == 0:
                self.screen.erase_display(
                    self.cursor_row, self.rows - 1, self._attrs)
                self.screen.erase_line(
                    self.cursor_row, self.cursor_col,
                    self.cols - 1, self._attrs)
            elif n == 1:
                self.screen.erase_display(0, self.cursor_row, self._attrs)
                self.screen.erase_line(
                    self.cursor_row, 0, self.cursor_col, self._attrs)
            elif n == 2 or n == 3:
                self.screen.erase_display(0, self.rows - 1, self._attrs)
            self.dirty = True

        elif cmd == 'K':  # Erase line
            n = P(0, 0)
            if n == 0:
                self.screen.erase_line(
                    self.cursor_row, self.cursor_col,
                    self.cols - 1, self._attrs)
            elif n == 1:
                self.screen.erase_line(
                    self.cursor_row, 0, self.cursor_col, self._attrs)
            elif n == 2:
                self.screen.erase_line(
                    self.cursor_row, 0, self.cols - 1, self._attrs)
            self.dirty = True

        elif cmd == 'L':  # Insert lines
            n = P(0, 1)
            for _ in range(n):
                self.screen.scroll_down(
                    self.cursor_row, self._scroll_bottom, self._attrs)
            self.dirty = True

        elif cmd == 'M':  # Delete lines
            n = P(0, 1)
            for _ in range(n):
                self.screen.scroll_up(
                    self.cursor_row, self._scroll_bottom, self._attrs)
            self.dirty = True

        elif cmd == 'P':  # Delete characters
            n = P(0, 1)
            row = self.cursor_row
            col = self.cursor_col
            for c in range(col, self.cols - n):
                src = self.screen.cell(row, c + n)
                dst = self.screen.cell(row, c)
                dst.char      = src.char
                dst.fg        = src.fg
                dst.bg        = src.bg
                dst.bold      = src.bold
                dst.underline = src.underline
                dst.reverse   = src.reverse
            self.screen.erase_line(
                row, self.cols - n, self.cols - 1, self._attrs)
            self.dirty = True

        elif cmd == 'S':  # Scroll up
            n = P(0, 1)
            for _ in range(n):
                self.screen.scroll_up(
                    self._scroll_top, self._scroll_bottom, self._attrs)
            self.dirty = True

        elif cmd == 'T':  # Scroll down
            n = P(0, 1)
            for _ in range(n):
                self.screen.scroll_down(
                    self._scroll_top, self._scroll_bottom, self._attrs)
            self.dirty = True

        elif cmd == 'X':  # Erase characters
            n = P(0, 1)
            self.screen.erase_line(
                self.cursor_row, self.cursor_col,
                self.cursor_col + n - 1, self._attrs)
            self.dirty = True

        elif cmd == 'd':  # Line position absolute
            self.cursor_row = min(self.rows - 1, max(0, P(0, 1) - 1))
            self.dirty = True

        elif cmd == 'm':  # SGR
            self._handle_sgr(p)

        elif cmd == 'r':  # Set scroll region
            top    = max(0,           P(0, 1) - 1)
            bottom = min(self.rows - 1, P(1, self.rows) - 1)
            if top < bottom:
                self._scroll_top    = top
                self._scroll_bottom = bottom
            self.cursor_row = 0
            self.cursor_col = 0

        elif cmd == 's':  # Save cursor
            self._saved_row = self.cursor_row
            self._saved_col = self.cursor_col

        elif cmd == 'u':  # Restore cursor
            self.cursor_row = self._saved_row
            self.cursor_col = self._saved_col
            self.dirty = True

        elif cmd == 'h':  # Set mode
            self._set_mode(params, priv, True)

        elif cmd == 'l':  # Reset mode
            self._set_mode(params, priv, False)

        elif cmd == 'n':  # DSR — device status report
            pass   # we don't respond to these

        elif cmd == 'c':  # DA — device attributes
            pass

    # ── OSC state ─────────────────────────────────────────────────────────

    def _handle_osc(self, ch: str):
        if ch == '\x07' or ch == '\x1b':
            # End of OSC — ignore title changes etc
            self._state = self._STATE_NORMAL
        else:
            self._osc_buf = getattr(self, '_osc_buf', '') + ch

    # ── SGR (colors + attributes) ─────────────────────────────────────────

    def _handle_sgr(self, params: list):
        if not params or params == [0]:
            self._attrs = Cell()
            return

        i = 0
        while i < len(params):
            p = params[i]

            if p == 0:
                self._attrs = Cell()
            elif p == 1:
                self._attrs.bold = True
            elif p == 2:
                self._attrs.dim = True
            elif p == 3:
                pass   # italic — ignore
            elif p == 4:
                self._attrs.underline = True
            elif p == 5:
                self._attrs.blink = True
            elif p == 7:
                self._attrs.reverse = True
            elif p == 21:
                self._attrs.bold = False
            elif p == 22:
                self._attrs.dim = False
            elif p == 24:
                self._attrs.underline = False
            elif p == 25:
                self._attrs.blink = False
            elif p == 27:
                self._attrs.reverse = False
            elif 30 <= p <= 37:
                self._attrs.fg = p - 30
            elif p == 38:
                # Extended fg color
                if i + 1 < len(params) and params[i + 1] == 5:
                    if i + 2 < len(params):
                        self._attrs.fg = params[i + 2] + 256
                        i += 2
                elif i + 1 < len(params) and params[i + 1] == 2:
                    if i + 4 < len(params):
                        r = params[i + 2]
                        g = params[i + 3]
                        b = params[i + 4]
                        self._attrs.fg = (r << 16) | (g << 8) | b | 0x1000000
                        i += 4
            elif p == 39:
                self._attrs.fg = -1
            elif 40 <= p <= 47:
                self._attrs.bg = p - 40
            elif p == 48:
                # Extended bg color
                if i + 1 < len(params) and params[i + 1] == 5:
                    if i + 2 < len(params):
                        self._attrs.bg = params[i + 2] + 256
                        i += 2
                elif i + 1 < len(params) and params[i + 1] == 2:
                    if i + 4 < len(params):
                        r = params[i + 2]
                        g = params[i + 3]
                        b = params[i + 4]
                        self._attrs.bg = (r << 16) | (g << 8) | b | 0x1000000
                        i += 4
            elif p == 49:
                self._attrs.bg = -1
            elif 90 <= p <= 97:
                self._attrs.fg = p - 90 + 8
            elif 100 <= p <= 107:
                self._attrs.bg = p - 100 + 8

            i += 1

    # ── Mode setting ──────────────────────────────────────────────────────

    def _set_mode(self, params: list, priv: bool, value: bool):
        for p in params:
            if priv:
                if p == 1:   # Application cursor keys
                    self._app_cursor_keys = value
                    self.dirty = True
                elif p == 7:    # Auto-wrap
                    self._auto_wrap = value
                elif p == 12:   # Cursor blink — ignore
                    pass
                elif p == 25:   # Cursor visible
                    self._cursor_visible = value
                    self.dirty = True
                elif p == 47 or p == 1047:  # Alternate screen
                    self._switch_screen(value)
                elif p == 1049:  # Alternate screen + save/restore cursor
                    if value:
                        self._saved_row = self.cursor_row
                        self._saved_col = self.cursor_col
                    self._switch_screen(value)
                    if not value:
                        self.cursor_row = self._saved_row
                        self.cursor_col = self._saved_col
                        self.dirty = True
            else:
                if p == 20:     # LNM
                    self._lnm = value

    def _switch_screen(self, alt: bool):
        if alt and not self._alt_active:
            self._alternate_screen.clear()
            self.screen      = self._alternate_screen
            self._alt_active = True
            self.cursor_row  = 0
            self.cursor_col  = 0
        elif not alt and self._alt_active:
            self.screen      = self._normal_screen
            self._alt_active = False
        self.dirty = True

    # ── Character placement ───────────────────────────────────────────────

    def _put_char(self, ch: str):
        if self.cursor_col >= self.cols:
            if self._auto_wrap:
                self.cursor_col = 0
                self._linefeed()
            else:
                self.cursor_col = self.cols - 1

        # Insert mode — shift existing characters right before placing
        if self._insert_mode:
            row = self.cursor_row
            # Shift cells right from the last column down to cursor+1
            for c in range(self.cols - 1, self.cursor_col, -1):
                src_cell = self.screen.cell(row, c - 1)
                dst_cell = self.screen.cell(row, c)
                dst_cell.char      = src_cell.char
                dst_cell.fg        = src_cell.fg
                dst_cell.bg        = src_cell.bg
                dst_cell.bold      = src_cell.bold
                dst_cell.dim       = src_cell.dim
                dst_cell.underline = src_cell.underline
                dst_cell.reverse   = src_cell.reverse
                dst_cell.blink     = src_cell.blink

        cell = self.screen.cell(self.cursor_row, self.cursor_col)
        cell.char      = ch
        cell.fg        = self._attrs.fg
        cell.bg        = self._attrs.bg
        cell.bold      = self._attrs.bold
        cell.dim       = self._attrs.dim
        cell.underline = self._attrs.underline
        cell.reverse   = self._attrs.reverse
        cell.blink     = self._attrs.blink

        self.cursor_col += 1
        self.dirty = True

    def _linefeed(self):
        if self.cursor_row >= self._scroll_bottom:
            self.screen.scroll_up(
                self._scroll_top, self._scroll_bottom, self._attrs,
                scrollback=self.scrollback if not self._alt_active else None,
                scrollback_max=self.scrollback_max,
            )
        else:
            self.cursor_row += 1
        if self._lnm:
            self.cursor_col = 0
        self.dirty = True

    def _full_reset(self):
        self._normal_screen.clear()
        self._alternate_screen.clear()
        self.screen         = self._normal_screen
        self._alt_active    = False
        self.cursor_row     = 0
        self.cursor_col     = 0
        self._saved_row     = 0
        self._saved_col     = 0
        self._attrs         = Cell()
        self._scroll_top    = 0
        self._scroll_bottom = self.rows - 1
        self._state         = self._STATE_NORMAL
        self._insert_mode   = False
        self._auto_wrap     = True
        self._lnm           = False
        self.dirty          = True

    # ── Scrollback ────────────────────────────────────────────────────────

    def get_line_text(self, row: int) -> str:
        """Return the text content of a row as a plain string."""
        return ''.join(
            self.screen.cell(row, c).char
            for c in range(self.cols)
        ).rstrip()

    def get_all_text(self) -> str:
        """Return all visible text — used by the run analyzer."""
        lines = [self.get_line_text(r) for r in range(self.rows)]
        return '\n'.join(lines)