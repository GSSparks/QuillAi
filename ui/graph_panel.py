"""
ui/graph_panel.py

Import/dependency graph panel — shows how project files connect.
Pure Qt, no extra dependencies. Force-directed layout with
Barnes-Hut approximation and QThread-based background processing.
"""

import os
import re
import ast
import math
import random
from PyQt6.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QSizePolicy, QSlider,
)
from PyQt6.QtCore import (
    Qt, QTimer, QPointF, QRectF,
    pyqtSignal, QObject, QThread, pyqtSlot,
)
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont,
    QWheelEvent, QMouseEvent,
)
from ui.theme import get_theme, theme_signals, FONT_UI


# ── Language import parsers ───────────────────────────────────────────────────

def _parse_imports(file_path: str, project_root: str) -> list:
    ext  = os.path.splitext(file_path)[1].lower()
    base = os.path.dirname(file_path)
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            src = f.read()
    except Exception:
        return []
    deps = []
    if ext == ".py":
        deps = _parse_python(src, base, project_root)
    elif ext in (".js", ".jsx", ".ts", ".tsx"):
        deps = _parse_js(src, base, project_root)
    elif ext in (".yml", ".yaml"):
        deps = _parse_yaml(src, base, project_root)
    elif ext == ".nix":
        deps = _parse_nix(src, base, project_root)
    elif ext in (".sh", ".bash"):
        deps = _parse_bash(src, base, project_root)
    elif ext == ".lua":
        deps = _parse_lua(src, base, project_root)
    elif ext in (".pl", ".pm", ".t"):
        deps = _parse_perl(src, base, project_root)
    return [d for d in deps if d and os.path.isfile(d)]


def _resolve(rel: str, base: str, project_root: str):
    candidates = [
        os.path.normpath(os.path.join(base, rel)),
        os.path.normpath(os.path.join(project_root, rel)),
    ]
    exts = ["", ".py", ".js", ".ts", ".jsx", ".tsx",
            ".lua", ".sh", ".nix", ".yml", ".yaml"]
    for c in candidates:
        for e in exts:
            full = c + e
            if os.path.isfile(full):
                return full
    return None


def _parse_python(src, base, root):
    deps = []
    try:
        tree = ast.parse(src)
    except Exception:
        return deps
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            r = _resolve(node.module.replace(".", os.sep) + ".py", base, root)
            if r:
                deps.append(r)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                r = _resolve(alias.name.replace(".", os.sep) + ".py", base, root)
                if r:
                    deps.append(r)
    return deps


def _parse_js(src, base, root):
    deps = []
    for pat in [
        r'import\s+.*?from\s+[\'"]([^\'"\n]+)[\'"]',
        r'require\s*\(\s*[\'"]([^\'"\n]+)[\'"]\s*\)',
        r'import\s*\(\s*[\'"]([^\'"\n]+)[\'"]\s*\)',
    ]:
        for m in re.finditer(pat, src):
            if m.group(1).startswith("."):
                r = _resolve(m.group(1), base, root)
                if r:
                    deps.append(r)
    return deps


def _parse_yaml(src, base, root):
    deps = []
    for pat in [
        r'include(?:_tasks|_vars|_role)?:\s*[\'"]?([^\s\'"]+\.ya?ml)',
        r'import_(?:tasks|playbook|role):\s*[\'"]?([^\s\'"]+\.ya?ml)',
    ]:
        for m in re.finditer(pat, src, re.MULTILINE):
            r = _resolve(m.group(1), base, root)
            if r:
                deps.append(r)
    return deps


def _parse_nix(src, base, root):
    deps = []
    for m in re.finditer(r'import\s+([./][^\s;]+)', src):
        r = _resolve(m.group(1), base, root)
        if r:
            deps.append(r)
    return deps


def _parse_bash(src, base, root):
    deps = []
    for m in re.finditer(r'(?:source|\.\s)\s+[\'"]?([^\s\'"]+)[\'"]?', src):
        r = _resolve(m.group(1), base, root)
        if r:
            deps.append(r)
    return deps


def _parse_lua(src, base, root):
    deps = []
    for m in re.finditer(r'require\s*[\(\s][\'"]([^\'"]+)[\'"]', src):
        r = _resolve(m.group(1).replace(".", os.sep), base, root)
        if r:
            deps.append(r)
    return deps
    
def _parse_perl(src: str, base: str, root: str) -> list:
    """
    Parse Perl use/require statements and resolve them to file paths.
 
    Handles:
        use Foo::Bar;                → lib/Foo/Bar.pm
        use Foo::Bar ();             → same
        require Foo::Bar;            → same
        require 'foo/bar.pl';        → relative path
        use parent 'Foo::Bar';       → same module resolution
        use base 'Foo::Bar';         → same
        use lib '/some/path';        → ignored (path manipulation, not a dep)
        use strict; use warnings;    → ignored (pragmas)
    """
    import re
    import os
 
    deps = []
 
    # Pragmas to skip — not real file dependencies
    _PRAGMAS = {
        'strict', 'warnings', 'utf8', 'feature', 'constant',
        'vars', 'lib', 'Exporter', 'Carp', 'POSIX',
        'Scalar::Util', 'List::Util', 'File::Basename',
        'File::Path', 'File::Spec', 'File::Find',
        'Cwd', 'Data::Dumper', 'Storable',
        'Encode', 'MIME::Base64', 'Digest::MD5',
        'Time::HiRes', 'Time::Piece', 'Time::Local',
        'Socket', 'IO::File', 'IO::Socket',
        'DBI', 'LWP', 'HTTP::Request', 'HTTP::Response',
        'JSON', 'YAML', 'XML::Simple', 'XML::LibXML',
        'Moose', 'Moo', 'Mouse', 'Role::Tiny',
        'Try::Tiny', 'Throwable', 'Type::Tiny',
        'Test::More', 'Test::Exception', 'Test::Deep',
        'overload', 'AUTOLOAD', 'BEGIN', 'END',
    }
 
    # use Module::Name; or use Module::Name qw(...);
    for m in re.finditer(
        r'^\s*use\s+([\w:]+)\s*', src, re.MULTILINE
    ):
        mod = m.group(1)
        if mod in _PRAGMAS or mod[0].isdigit():
            continue
        r = _resolve_perl_module(mod, base, root)
        if r:
            deps.append(r)
 
    # use parent/base 'Module::Name' or use parent/base qw(Mod1 Mod2)
    for m in re.finditer(
        r'^\s*use\s+(?:parent|base)\s+(?:qw\(([^)]+)\)|[\'"]([^\'"]+)[\'"])',
        src, re.MULTILINE
    ):
        mods_str = m.group(1) or m.group(2) or ""
        for mod in mods_str.split():
            r = _resolve_perl_module(mod.strip("'\""), base, root)
            if r:
                deps.append(r)
 
    # require Module::Name; or require 'path/to/file.pl';
    for m in re.finditer(
        r'^\s*require\s+([\'"]?)([^\s;\'"\)]+)\1\s*;',
        src, re.MULTILINE
    ):
        quoted = m.group(1)
        target = m.group(2)
        if quoted:
            # require 'path/file.pl' — treat as relative path
            r = _resolve(target, base, root)
            if r:
                deps.append(r)
        else:
            # require Module::Name
            if target not in _PRAGMAS and not target[0].isdigit():
                r = _resolve_perl_module(target, base, root)
                if r:
                    deps.append(r)
 
    return deps
 
 
def _resolve_perl_module(module_name: str, base: str, root: str):
    """
    Convert Module::Name to Module/Name.pm and search common Perl
    include paths relative to the project root.
    """
    import os
    rel = module_name.replace('::', os.sep) + '.pm'
 
    search_dirs = [
        base,
        root,
        os.path.join(root, 'lib'),
        os.path.join(root, 'lib', 'perl5'),
        os.path.join(root, 'local', 'lib', 'perl5'),
    ]
 
    for d in search_dirs:
        full = os.path.normpath(os.path.join(d, rel))
        if os.path.isfile(full):
            return full
 
    return None


# ── Barnes-Hut quad tree ──────────────────────────────────────────────────────

class _QuadNode:
    __slots__ = ("cx", "cy", "mass", "children", "x1", "y1", "x2", "y2")

    def __init__(self, x1, y1, x2, y2):
        self.x1 = x1;  self.y1 = y1
        self.x2 = x2;  self.y2 = y2
        self.cx = 0.0; self.cy = 0.0
        self.mass = 0
        self.children = None


def _bh_insert(root: _QuadNode, x: float, y: float):
    node = root
    while True:
        node.cx = (node.cx * node.mass + x) / (node.mass + 1)
        node.cy = (node.cy * node.mass + y) / (node.mass + 1)
        node.mass += 1
        if node.mass == 1:
            return
        mx = (node.x1 + node.x2) / 2
        my = (node.y1 + node.y2) / 2
        if node.children is None:
            node.children = [
                _QuadNode(node.x1, node.y1, mx,      my),
                _QuadNode(mx,      node.y1, node.x2, my),
                _QuadNode(node.x1, my,      mx,      node.y2),
                _QuadNode(mx,      my,      node.x2, node.y2),
            ]
        qi = (2 if y >= my else 0) + (1 if x >= mx else 0)
        node = node.children[qi]


def _bh_force(root: _QuadNode, x: float, y: float,
              kr: float, theta: float = 0.9):
    if root is None or root.mass == 0:
        return 0.0, 0.0
    dx   = x - root.cx
    dy   = y - root.cy
    dist = math.hypot(dx, dy) + 0.01
    size = root.x2 - root.x1
    if root.children is None or (size / dist) < theta:
        f = kr * root.mass / (dist * dist)
        return f * dx / dist, f * dy / dist
    fx, fy = 0.0, 0.0
    for child in root.children:
        if child.mass > 0:
            cfx, cfy = _bh_force(child, x, y, kr, theta)
            fx += cfx
            fy += cfy
    return fx, fy


# ── Build + simulation worker ─────────────────────────────────────────────────

class _BuildWorker(QObject):
    """
    Runs entirely on a QThread. Never touches the main thread directly.
    All results delivered via queued signals.
    """
    progress = pyqtSignal(list)                # [(path, x, y), ...]
    status   = pyqtSignal(int, int, int, list) # visible, total, edges, edge_list
    finished = pyqtSignal()

    def __init__(self, all_nodes: dict, project_root: str, min_degree: int):
        super().__init__()
        self._all_nodes    = all_nodes
        self._project_root = project_root
        self._min_degree   = min_degree
        self._stop_flag    = False

    def stop(self):
        self._stop_flag = True

    @pyqtSlot()
    def run(self):
        # ── Phase 1: parse imports ────────────────────────────────────────
        edges = []
        seen  = set()
        for fp in self._all_nodes:
            if self._stop_flag:
                self.finished.emit()
                return
            for dep in _parse_imports(fp, self._project_root):
                if dep in self._all_nodes:
                    key = (fp, dep)
                    if key not in seen:
                        seen.add(key)
                        edges.append(key)

        # Compute degree
        for ea, eb in edges:
            self._all_nodes[ea].degree += 1
            self._all_nodes[eb].degree += 1

        # Filter by min degree
        visible   = {k: v for k, v in self._all_nodes.items()
                     if v.degree >= self._min_degree}
        vis_edges = [(a, b) for a, b in edges
                     if a in visible and b in visible]

        self.status.emit(
            len(visible), len(self._all_nodes), len(vis_edges), vis_edges
        )

        if not visible or self._stop_flag:
            self.finished.emit()
            return

        # ── Phase 2: force simulation ─────────────────────────────────────
        positions = {p: [n.x, n.y, 0.0, 0.0] for p, n in visible.items()}
        paths     = list(positions.keys())
        k         = 80.0
        kr        = 15000.0
        damp      = 0.82

        for step in range(250):
            if self._stop_flag:
                self.finished.emit()
                return

            xs = [positions[p][0] for p in paths]
            ys = [positions[p][1] for p in paths]
            margin = 50
            x1 = min(xs) - margin;  x2 = max(xs) + margin
            y1 = min(ys) - margin;  y2 = max(ys) + margin
            if x2 - x1 < 1: x2 = x1 + 1
            if y2 - y1 < 1: y2 = y1 + 1

            root = _QuadNode(x1, y1, x2, y2)
            for p in paths:
                _bh_insert(root, positions[p][0], positions[p][1])

            for p in paths:
                px, py, vx, vy = positions[p]
                fx, fy = _bh_force(root, px, py, kr)

                for ea, eb in vis_edges:
                    op = eb if ea == p else (ea if eb == p else None)
                    if op and op in positions:
                        dx   = positions[op][0] - px
                        dy   = positions[op][1] - py
                        dist = math.hypot(dx, dy) + 0.01
                        f    = (dist - k) * 0.05
                        fx  += f * dx / dist
                        fy  += f * dy / dist

                fx -= px * 0.005
                fy -= py * 0.005
                vx  = (vx + fx) * damp
                vy  = (vy + fy) * damp
                positions[p] = [px + vx, py + vy, vx, vy]

            if step % 8 == 0:
                self.progress.emit(
                    [(p, positions[p][0], positions[p][1]) for p in paths]
                )

        self.progress.emit(
            [(p, positions[p][0], positions[p][1]) for p in paths]
        )
        self.finished.emit()


# ── Node ──────────────────────────────────────────────────────────────────────

class Node:
    __slots__ = ("path", "label", "short", "ext", "x", "y", "vx", "vy",
                 "pinned", "degree")

    def __init__(self, path: str, project_root: str):
        self.path   = path
        self.label  = os.path.relpath(path, project_root)
        self.short  = os.path.basename(path)
        self.ext    = os.path.splitext(path)[1].lower()
        self.x      = random.uniform(-300, 300)
        self.y      = random.uniform(-300, 300)
        self.vx     = 0.0
        self.vy     = 0.0
        self.pinned = False
        self.degree = 0


# ── Canvas ────────────────────────────────────────────────────────────────────

_EXT_COLORS = {
    ".py":   "blue",
    ".js":   "yellow",  ".jsx":  "yellow",
    ".ts":   "yellow",  ".tsx":  "yellow",
    ".yml":  "green",   ".yaml": "green",
    ".nix":  "purple",
    ".sh":   "orange",  ".bash": "orange",
    ".lua":  "aqua",
    ".md":   "fg4",
    ".pl":   "red",   ".pm":  "red",   ".t":   "red",
}
_SKIP_DIRS = {
    "__pycache__", "node_modules", ".git", "venv", ".venv",
    "dist", "build", ".mypy_cache", ".pytest_cache",
}
_SUPPORTED_EXTS = {
    ".py", ".js", ".jsx", ".ts", ".tsx",
    ".yml", ".yaml", ".nix", ".sh", ".bash", ".lua",
    ".pl", ".pm", ".t",
}


class GraphCanvas(QWidget):

    graph_status = pyqtSignal(int, int, int)  # visible, total, edges

    def __init__(self, parent=None):
        super().__init__(parent)
        self._t              = get_theme()
        self._nodes: dict    = {}
        self._visible_nodes: dict = {}
        self._visible_edges: list = []
        self._project_root   = ""
        self._active_path    = ""
        self._scale          = 1.0
        self._offset         = QPointF(0, 0)
        self._drag_node      = None
        self._drag_offset    = QPointF()
        self._pan_last       = None
        self._open_cb        = None
        self._min_degree     = 1
        self._loading        = False

        # Keep thread + worker as instance vars — prevents GC while running
        self._thread: QThread = None
        self._worker: _BuildWorker = None

        # Debounce slider changes — only relaunch 600ms after last move
        self._relaunch_timer = QTimer(self)
        self._relaunch_timer.setSingleShot(True)
        self._relaunch_timer.setInterval(600)
        self._relaunch_timer.timeout.connect(self._launch_worker)

        self.setMinimumSize(200, 200)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)
        theme_signals.theme_changed.connect(self._on_theme)

    # ── Public ────────────────────────────────────────────────────────────

    def set_open_callback(self, cb):
        self._open_cb = cb

    def set_min_degree(self, value: int):
        self._min_degree = value
        if self._nodes:
            self._relaunch_timer.start()

    def load_project(self, project_root: str):
        self._project_root = project_root
        self._nodes.clear()
        self._visible_nodes.clear()
        self._visible_edges.clear()
        self._loading = True

        for dirpath, dirnames, filenames in os.walk(project_root):
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
            for fn in filenames:
                ext = os.path.splitext(fn)[1].lower()
                if ext in _SUPPORTED_EXTS:
                    fp = os.path.join(dirpath, fn)
                    self._nodes[fp] = Node(fp, project_root)

        # Defer heavy work until after UI is fully painted
        QTimer.singleShot(300, self._launch_worker)
        self.update()

    def set_active_file(self, path: str):
        self._active_path = path
        self.update()

    # ── Worker management ─────────────────────────────────────────────────

    def _launch_worker(self):
        self._stop_worker()

        if not self._nodes:
            return

        self._loading = True
        self.update()

        # Preserve existing positions on re-launch (e.g. slider change)
        fresh = {}
        for k, n in self._nodes.items():
            fn       = Node(n.path, self._project_root)
            fn.x     = n.x
            fn.y     = n.y
            fresh[k] = fn

        self._worker = _BuildWorker(fresh, self._project_root, self._min_degree)

        # parent=self keeps Qt from GC'ing the thread before it finishes
        self._thread = QThread(self)

        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(
            self._on_progress, Qt.ConnectionType.QueuedConnection)
        self._worker.status.connect(
            self._on_status, Qt.ConnectionType.QueuedConnection)
        self._worker.finished.connect(
            self._thread.quit, Qt.ConnectionType.QueuedConnection)
        self._worker.finished.connect(
            self._worker.deleteLater, Qt.ConnectionType.QueuedConnection)
        self._thread.finished.connect(
            self._on_worker_done, Qt.ConnectionType.QueuedConnection)
        self._thread.finished.connect(
            self._thread.deleteLater, Qt.ConnectionType.QueuedConnection)

        self._thread.start()

    def _stop_worker(self):
        """Signal worker to stop and wait cleanly — no 'destroyed while running'."""
        if self._worker is not None:
            self._worker.stop()
            self._worker = None

        if self._thread is not None:
            self._thread.quit()
            if not self._thread.wait(2000):
                self._thread.terminate()
                self._thread.wait(500)
            self._thread = None

    # ── Worker slots ──────────────────────────────────────────────────────

    @pyqtSlot(list)
    def _on_progress(self, positions: list):
        for path, x, y in positions:
            node = self._visible_nodes.get(path)
            if node and not node.pinned:
                node.x = x
                node.y = y
        self.update()

    @pyqtSlot(int, int, int, list)
    def _on_status(self, visible: int, total: int,
                   edge_count: int, edges: list):
        visible_paths = set()
        for ea, eb in edges:
            visible_paths.add(ea)
            visible_paths.add(eb)
        self._visible_nodes = {
            k: self._nodes[k] for k in visible_paths if k in self._nodes
        }
        self._visible_edges = edges
        self.graph_status.emit(visible, total, edge_count)

    @pyqtSlot()
    def _on_worker_done(self):
        self._loading = False
        self._worker  = None
        self._thread  = None
        self.update()

    # ── Drawing ───────────────────────────────────────────────────────────

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(),
                         QColor(self._t.get("bg0_hard", "#1d2021")))

        if self._loading and not self._visible_nodes:
            painter.setPen(QColor(self._t.get("fg4", "#a89984")))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             "Building graph…")
            return

        if not self._visible_nodes:
            painter.setPen(QColor(self._t.get("fg4", "#a89984")))
            painter.drawText(
                self.rect(), Qt.AlignmentFlag.AlignCenter,
                "No connections found.\nTry lowering the Min links slider.",
            )
            return

        cx = self.width()  / 2 + self._offset.x()
        cy = self.height() / 2 + self._offset.y()

        def s(x, y):
            return cx + x * self._scale, cy + y * self._scale

        # ── Edges ─────────────────────────────────────────────────────────
        edge_color = QColor(self._t.get("bg3", "#665c54"))
        painter.setPen(QPen(edge_color, 1))
        for ea, eb in self._visible_edges:
            na = self._visible_nodes.get(ea)
            nb = self._visible_nodes.get(eb)
            if not na or not nb:
                continue
            ax, ay = s(na.x, na.y)
            bx, by = s(nb.x, nb.y)
            painter.drawLine(int(ax), int(ay), int(bx), int(by))
            angle = math.atan2(by - ay, bx - ax)
            aw    = max(4, 7 * self._scale)
            painter.drawLine(
                int(bx), int(by),
                int(bx - aw * math.cos(angle - 0.4)),
                int(by - aw * math.sin(angle - 0.4)),
            )
            painter.drawLine(
                int(bx), int(by),
                int(bx - aw * math.cos(angle + 0.4)),
                int(by - aw * math.sin(angle + 0.4)),
            )

        # ── Nodes ─────────────────────────────────────────────────────────
        font = QFont(FONT_UI)
        font.setPointSize(max(6, int(8 * self._scale)))
        painter.setFont(font)

        for fp, node in self._visible_nodes.items():
            sx, sy    = s(node.x, node.y)
            is_active = (fp == self._active_path)
            r = max(5, int((6 + min(node.degree, 10)) * self._scale))

            color_key = _EXT_COLORS.get(node.ext, "fg4")
            color     = QColor(self._t.get(color_key, "#a89984"))

            if is_active:
                glow = QColor(self._t.get("accent", "#fabd2f"))
                glow.setAlpha(60)
                painter.setBrush(QBrush(glow))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(
                    QRectF(sx - r - 5, sy - r - 5, (r + 5) * 2, (r + 5) * 2)
                )
                painter.setPen(
                    QPen(QColor(self._t.get("accent", "#fabd2f")), 2)
                )
            else:
                painter.setPen(QPen(color.darker(150), 1))

            painter.setBrush(QBrush(color))
            painter.drawEllipse(QRectF(sx - r, sy - r, r * 2, r * 2))

            if self._scale > 0.4:
                painter.setPen(QColor(self._t.get("fg1", "#ebdbb2")))
                painter.drawText(
                    int(sx + r + 3),
                    int(sy + font.pointSize() // 2),
                    node.short,
                )

    # ── Interaction ───────────────────────────────────────────────────────

    def _node_at(self, sx: float, sy: float):
        if not self._visible_nodes:
            return None
        cx = self.width()  / 2 + self._offset.x()
        cy = self.height() / 2 + self._offset.y()
        best, best_d = None, float("inf")
        for node in self._visible_nodes.values():
            nx = cx + node.x * self._scale
            ny = cy + node.y * self._scale
            r  = max(5, (6 + min(node.degree, 10)) * self._scale) + 4
            d  = math.hypot(sx - nx, sy - ny)
            if d < r and d < best_d:
                best, best_d = node, d
        return best

    def mousePressEvent(self, event: QMouseEvent):
        pos  = event.position()
        node = self._node_at(pos.x(), pos.y())
        if node and event.button() == Qt.MouseButton.LeftButton:
            self._drag_node   = node
            node.pinned       = True
            cx = self.width()  / 2 + self._offset.x()
            cy = self.height() / 2 + self._offset.y()
            self._drag_offset = QPointF(
                pos.x() - (cx + node.x * self._scale),
                pos.y() - (cy + node.y * self._scale),
            )
        else:
            self._pan_last = pos

    def mouseMoveEvent(self, event: QMouseEvent):
        pos = event.position()
        if self._drag_node:
            cx = self.width()  / 2 + self._offset.x()
            cy = self.height() / 2 + self._offset.y()
            self._drag_node.x  = (pos.x() - self._drag_offset.x() - cx) / self._scale
            self._drag_node.y  = (pos.y() - self._drag_offset.y() - cy) / self._scale
            self._drag_node.vx = 0
            self._drag_node.vy = 0
            self.update()
        elif self._pan_last is not None:
            self._offset  += pos - self._pan_last
            self._pan_last = pos
            self.update()
        node = self._node_at(pos.x(), pos.y())
        self.setCursor(
            Qt.CursorShape.PointingHandCursor if node
            else Qt.CursorShape.ArrowCursor
        )

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self._drag_node:
            self._drag_node.pinned = False
            self._drag_node = None
        self._pan_last = None

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        node = self._node_at(event.position().x(), event.position().y())
        if node and self._open_cb:
            self._open_cb(node.path)

    def wheelEvent(self, event: QWheelEvent):
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self._scale = max(0.1, min(5.0, self._scale * factor))
        self.update()

    def _on_theme(self, t: dict):
        self._t = t
        self.update()


# ── Dock widget ───────────────────────────────────────────────────────────────

class GraphDockWidget(QDockWidget):

    def __init__(self, parent=None):
        super().__init__("Import Graph", parent)
        self.setObjectName("graph_dock")

        container = QWidget()
        layout    = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Toolbar ───────────────────────────────────────────────────────
        toolbar   = QWidget()
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(6, 3, 6, 3)
        tb_layout.setSpacing(6)

        self._status = QLabel("No project")
        self._status.setStyleSheet(
            f"color: #a89984; font-size: 8pt; font-family: '{FONT_UI}';"
        )
        tb_layout.addWidget(self._status)
        tb_layout.addStretch()

        min_lbl = QLabel("Min links:")
        min_lbl.setStyleSheet(
            f"color: #a89984; font-size: 8pt; font-family: '{FONT_UI}';"
        )
        tb_layout.addWidget(min_lbl)

        self._degree_slider = QSlider(Qt.Orientation.Horizontal)
        self._degree_slider.setRange(1, 10)
        self._degree_slider.setValue(1)
        self._degree_slider.setFixedWidth(70)
        self._degree_slider.setToolTip(
            "Hide files with fewer than N connections"
        )
        self._degree_slider.valueChanged.connect(self._on_degree_changed)
        tb_layout.addWidget(self._degree_slider)

        self._degree_label = QLabel("1")
        self._degree_label.setFixedWidth(16)
        self._degree_label.setStyleSheet(
            f"color: #a89984; font-size: 8pt; font-family: '{FONT_UI}';"
        )
        tb_layout.addWidget(self._degree_label)

        btn_style = f"""
            QPushButton {{
                background: transparent;
                color: #a89984;
                border: 1px solid #504945;
                border-radius: 3px;
                padding: 1px 8px;
                font-size: 8pt;
                font-family: '{FONT_UI}';
            }}
            QPushButton:hover {{
                color: #ebdbb2;
                border-color: #665c54;
            }}
        """

        refresh_btn = QPushButton("⟳")
        refresh_btn.setFixedSize(24, 22)
        refresh_btn.setToolTip("Refresh graph")
        refresh_btn.setStyleSheet(btn_style)
        refresh_btn.clicked.connect(self._refresh)
        tb_layout.addWidget(refresh_btn)

        center_btn = QPushButton("⊕")
        center_btn.setFixedSize(24, 22)
        center_btn.setToolTip("Reset zoom and pan")
        center_btn.setStyleSheet(btn_style)
        center_btn.clicked.connect(self._center)
        tb_layout.addWidget(center_btn)

        layout.addWidget(toolbar)

        # ── Canvas ────────────────────────────────────────────────────────
        self._canvas = GraphCanvas()
        self._canvas.graph_status.connect(self._on_graph_status)
        layout.addWidget(self._canvas)

        self.setWidget(container)
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable  |
            QDockWidget.DockWidgetFeature.DockWidgetMovable   |
            QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )

    # ── Public ────────────────────────────────────────────────────────────

    def load_project(self, project_root: str, open_cb=None):
        self._project_root = project_root
        self._canvas.set_open_callback(open_cb)
        self._canvas.load_project(project_root)
        self._status.setText("Building graph…")

    def set_active_file(self, path: str):
        self._canvas.set_active_file(path)

    # ── Slots ─────────────────────────────────────────────────────────────

    @pyqtSlot(int, int, int)
    def _on_graph_status(self, visible: int, total: int, edges: int):
        self._status.setText(
            f"{visible}/{total} files · {edges} connections"
        )

    def _on_degree_changed(self, value: int):
        self._degree_label.setText(str(value))
        self._canvas.set_min_degree(value)

    def _refresh(self):
        if hasattr(self, "_project_root"):
            self.load_project(self._project_root, self._canvas._open_cb)

    def _center(self):
        self._canvas._offset = QPointF(0, 0)
        self._canvas._scale  = 1.0
        self._canvas.update()