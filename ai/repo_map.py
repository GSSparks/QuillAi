"""
ai/repo_map.py

Builds a compact structural map of a Python project for LLM context.
Each entry is one line: file path → class/function signature + docstring.

Usage:
    repo_map = RepoMap(project_root)
    repo_map.build()                          # call on project open
    repo_map.invalidate()                     # call on file save
    ctx = repo_map.get_context(query)         # call per chat message
"""

import ast
import os
import threading
import time


# Hard cap so the map never crowds out active code context
MAX_MAP_TOKENS   = 4000
CHARS_PER_TOKEN  = 4

# Skip these directories entirely
SKIP_DIRS = {
    "__pycache__", ".git", "node_modules",
    "venv", ".venv", "dist", "build", ".mypy_cache",
    ".pytest_cache", ".ruff_cache",
}


class RepoMap:
    """
    Lazily-built, cache-invalidated structural map of a project.

    Thread safety: build() runs in a background thread. get_context()
    always returns immediately — either from cache or with an empty string
    if the build hasn't completed yet.
    """

    def __init__(self, project_root: str):
        self.project_root = project_root
        self._cache: dict[str, "_FileEntry"] = {}   # rel_path → _FileEntry
        self._dirty: set[str] = set()               # rel_paths needing rebuild
        self._lock  = threading.Lock()
        self._building = False

    # ─────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────

    def build(self):
        """
        Parse every .py file in the project and cache its structure.
        Runs in a background thread — non-blocking.
        """
        if self._building:
            return
        threading.Thread(target=self._build_all, daemon=True).start()

    def invalidate(self, file_path: str = None):
        """
        Mark a file (or the entire project) as needing a rebuild.
        The rebuild happens lazily on the next get_context() call.
        """
        with self._lock:
            if file_path:
                rel = self._rel(file_path)
                if rel:
                    self._dirty.add(rel)
            else:
                # Full invalidation — mark everything dirty
                self._dirty.update(self._cache.keys())

    def get_context(self, query: str = "", token_budget: int = MAX_MAP_TOKENS) -> str:
        """
        Return a filtered repo map string ready for LLM injection.
        Files are scored by symbol overlap with the query; only relevant
        files are included. Falls back to top files by symbol count if
        no query is provided.

        Always returns immediately from cache — rebuilds dirty files
        synchronously only if the delta is small (< 5 files), otherwise
        schedules a background rebuild and returns the stale map.
        """
        self._maybe_rebuild_dirty()

        with self._lock:
            entries = dict(self._cache)

        if not entries:
            return ""

        q_words = set(query.lower().split()) if query else set()
        scored  = self._score_entries(entries, q_words)

        if not scored:
            return ""

        lines        = []
        used_chars   = 0
        char_budget  = token_budget * CHARS_PER_TOKEN

        for _, rel_path, entry in scored:
            chunk = entry.format()
            if used_chars + len(chunk) > char_budget:
                break
            lines.append(chunk)
            used_chars += len(chunk)

        if not lines:
            return ""

        return "[Repo Map]\n" + "\n".join(lines)

    # ─────────────────────────────────────────────────────────────
    # Scoring
    # ─────────────────────────────────────────────────────────────

    def _score_entries(self, entries: dict, q_words: set) -> list:
        """
        Score each file by how many query words appear as symbol names.
        Returns sorted list of (score, rel_path, entry), highest first.
        Files with score 0 are excluded when a query is provided.
        """
        scored = []

        for rel_path, entry in entries.items():
            if q_words:
                score = sum(
                    1 for sym in entry.symbols
                    if any(w in sym.name.lower() for w in q_words)
                )
                if score == 0:
                    continue
            else:
                # No query — rank by symbol count (most complex files first)
                score = len(entry.symbols)

            scored.append((score, rel_path, entry))

        scored.sort(key=lambda x: x[0], reverse=True)
        return scored

    # ─────────────────────────────────────────────────────────────
    # Build / cache internals
    # ─────────────────────────────────────────────────────────────

    def _build_all(self):
        self._building = True
        try:
            new_cache = {}
            for py_file in self._walk_python_files():
                rel   = self._rel(py_file)
                entry = self._parse_file(py_file, rel)
                if entry:
                    new_cache[rel] = entry

            with self._lock:
                self._cache = new_cache
                self._dirty.clear()
        finally:
            self._building = False

    def _maybe_rebuild_dirty(self):
        with self._lock:
            dirty = set(self._dirty)

        if not dirty:
            return

        # Small delta — rebuild synchronously so this call gets fresh data
        if len(dirty) <= 5:
            for rel in dirty:
                full = os.path.join(self.project_root, rel)
                entry = self._parse_file(full, rel)
                with self._lock:
                    if entry:
                        self._cache[rel] = entry
                    else:
                        self._cache.pop(rel, None)
                    self._dirty.discard(rel)
        else:
            # Large delta — schedule background rebuild, return stale data
            self.build()

    def _parse_file(self, full_path: str, rel_path: str):
        """Parse a single .py file and return a _FileEntry or None."""
        try:
            with open(full_path, "r", encoding="utf-8") as f:
                source = f.read()
        except Exception:
            return None

        try:
            tree = ast.parse(source)
        except SyntaxError:
            return None
        except Exception:
            return None

        entry = _FileEntry(rel_path)

        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                doc  = ast.get_docstring(node) or ""
                cls  = _Symbol(
                    kind    = "class",
                    name    = node.name,
                    sig     = f"class {node.name}",
                    doc     = doc[:80] if doc else "",
                    indent  = 0,
                )
                entry.add(cls)

                for item in node.body:
                    if isinstance(item, ast.FunctionDef):
                        args    = _format_args(item)
                        m_doc   = ast.get_docstring(item) or ""
                        method  = _Symbol(
                            kind   = "method",
                            name   = item.name,
                            sig    = f"def {item.name}({args})",
                            doc    = m_doc[:80] if m_doc else "",
                            indent = 1,
                        )
                        entry.add(method)

            elif isinstance(node, ast.FunctionDef):
                args = _format_args(node)
                doc  = ast.get_docstring(node) or ""
                fn   = _Symbol(
                    kind   = "function",
                    name   = node.name,
                    sig    = f"def {node.name}({args})",
                    doc    = doc[:80] if doc else "",
                    indent = 0,
                )
                entry.add(fn)

        return entry if entry.symbols else None

    def _walk_python_files(self):
        for dirpath, dirnames, filenames in os.walk(self.project_root):
            # Prune skip dirs in-place so os.walk doesn't descend into them
            dirnames[:] = [
                d for d in dirnames
                if d not in SKIP_DIRS and not d.startswith(".")
            ]
            for fname in filenames:
                if fname.endswith(".py"):
                    yield os.path.join(dirpath, fname)

    def _rel(self, full_path: str) -> str:
        try:
            return os.path.relpath(full_path, self.project_root)
        except ValueError:
            return ""


# ─────────────────────────────────────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────────────────────────────────────

class _Symbol:
    __slots__ = ("kind", "name", "sig", "doc", "indent")

    def __init__(self, kind, name, sig, doc, indent):
        self.kind   = kind
        self.name   = name
        self.sig    = sig
        self.doc    = doc
        self.indent = indent

    def format(self) -> str:
        pad  = "  " * self.indent
        line = f"{pad}{self.sig}"
        if self.doc:
            # Truncate and clean up the docstring to one line
            clean = self.doc.replace("\n", " ").strip()
            line += f'  # "{clean}"'
        return line


class _FileEntry:
    __slots__ = ("rel_path", "symbols")

    def __init__(self, rel_path: str):
        self.rel_path = rel_path
        self.symbols: list[_Symbol] = []

    def add(self, symbol: _Symbol):
        self.symbols.append(symbol)

    def format(self) -> str:
        lines = [f"\n{self.rel_path}"]
        for sym in self.symbols:
            lines.append(sym.format())
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _format_args(node: ast.FunctionDef) -> str:
    """
    Format function arguments into a compact signature string.
    Includes type annotations where present, omits defaults for brevity.
    """
    args      = node.args
    parts     = []
    all_args  = args.args or []

    # *args
    vararg_name = args.vararg.arg if args.vararg else None
    # **kwargs
    kwarg_name  = args.kwarg.arg  if args.kwarg  else None

    for arg in all_args:
        if arg.annotation:
            try:
                ann = ast.unparse(arg.annotation)
                parts.append(f"{arg.arg}: {ann}")
            except Exception:
                parts.append(arg.arg)
        else:
            parts.append(arg.arg)

    if vararg_name:
        parts.append(f"*{vararg_name}")

    if args.kwonlyargs:
        for arg in args.kwonlyargs:
            parts.append(arg.arg)

    if kwarg_name:
        parts.append(f"**{kwarg_name}")

    return ", ".join(parts)