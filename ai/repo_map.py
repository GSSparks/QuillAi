"""
ai/repo_map.py

Builds a compact structural map of a project for LLM context.
Supports Python (.py) and Ansible (.yml/.yaml) files.

Python entries:   file → class/function signatures + docstrings
Ansible entries:  file → task names + modules + import graph

Usage:
    repo_map = RepoMap(project_root)
    repo_map.build()                    # non-blocking background build
    repo_map.invalidate(file_path)      # call on file save
    ctx = repo_map.get_context(query)   # call per chat message
"""

import ast
import os
import threading

# PyYAML is optional — Ansible support degrades gracefully without it
try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


# Hard cap so the map never crowds out active code context
MAX_MAP_TOKENS  = 4000
CHARS_PER_TOKEN = 4

# Directories never descended into
SKIP_DIRS = {
    "__pycache__", ".git", "node_modules",
    "venv", ".venv", "dist", "build",
    ".mypy_cache", ".pytest_cache", ".ruff_cache",
}

# Ansible keywords that import/include other files
ANSIBLE_IMPORT_KEYS = {
    "import_tasks", "include_tasks",
    "import_role",  "include_role",
    "import_playbook",
}

# Ansible directories that are always relevant to map
ANSIBLE_DIRS = {"playbooks", "roles", "group_vars", "host_vars", "tasks", "handlers"}

# ── Query tokenisation (CamelCase + snake_case aware) ─────────────────────────
import re as _re
_RE_CAMEL = _re.compile(r'(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])')
_RE_SPLIT = _re.compile(r'[\s_\-/\\.]+')

def _tokenise(text: str) -> set:
    """Split CamelCase and snake_case into lowercase tokens, filter short ones."""
    text = _RE_CAMEL.sub(' ', text)
    return {t for t in _RE_SPLIT.split(text.lower()) if len(t) > 2}


class RepoMap:
    """
    Lazily-built, cache-invalidated structural map of a project.

    Thread safety: build() runs in a background thread. get_context()
    always returns immediately — from cache, or empty string if the
    initial build hasn't finished yet.
    """

    def __init__(self, project_root: str):
        self.project_root = project_root
        self._cache: dict[str, "_FileEntry"] = {}
        self._dirty: set[str] = set()
        self._lock     = threading.Lock()
        self._building = False

    # ─────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────

    def build(self):
        """Parse all supported files in the project. Non-blocking."""
        if self._building:
            return
        threading.Thread(target=self._build_all, daemon=True).start()

    def invalidate(self, file_path: str = None):
        """
        Mark a file (or the whole project) dirty.
        Rebuild happens lazily on the next get_context() call.
        """
        with self._lock:
            if file_path:
                rel = self._rel(file_path)
                if rel:
                    self._dirty.add(rel)
            else:
                self._dirty.update(self._cache.keys())

    def get_context(self, query: str = "", token_budget: int = MAX_MAP_TOKENS) -> str:
        """
        Return a filtered map string ready for LLM injection.
        Files are scored by symbol/task name overlap with the query.
        Always returns immediately from cache.
        """
        self._maybe_rebuild_dirty()

        with self._lock:
            entries = dict(self._cache)

        if not entries:
            return ""

        q_words = _tokenise(query) if query else set()
        scored  = self._score_entries(entries, q_words)

        if not scored:
            return ""

        lines      = []
        used_chars = 0
        char_budget = token_budget * CHARS_PER_TOKEN

        for _, rel_path, entry in scored:
            chunk = entry.format()
            if used_chars + len(chunk) > char_budget:
                break
            lines.append(chunk)
            used_chars += len(chunk)

        return ("[Repo Map]\n" + "\n".join(lines)) if lines else ""

    # ─────────────────────────────────────────────────────────────
    # Scoring
    # ─────────────────────────────────────────────────────────────

    def _score_entries(self, entries: dict, q_words: set) -> list:
        """
        Score entries by token overlap.  q_words are already tokenised by
        get_context() using _tokenise(), so CamelCase has been split.
        Each symbol name is also tokenised before matching so
        "get_context" matches query token "context", etc.
        """
        scored = []

        for rel_path, entry in entries.items():
            if q_words:
                # Path tokens — "ai/repo_map.py" → {"ai","repo","map"}
                path_tokens = _tokenise(rel_path)
                path_score  = len(q_words & path_tokens) * 2   # path match worth more

                # Symbol token overlap
                sym_score = 0
                for sym in entry.symbols:
                    sym_tokens = _tokenise(sym.name)
                    sym_score += len(q_words & sym_tokens)

                score = path_score + sym_score
                if score == 0:
                    continue
            else:
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
            for full_path, kind in self._walk_source_files():
                rel = self._rel(full_path)
                if kind == "python":
                    entry = self._parse_python(full_path, rel)
                else:
                    entry = self._parse_ansible(full_path, rel, visited=set())
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

        if len(dirty) <= 5:
            for rel in dirty:
                full  = os.path.join(self.project_root, rel)
                kind  = "ansible" if _is_ansible_file(full, rel) else "python"
                entry = (
                    self._parse_ansible(full, rel, visited=set())
                    if kind == "ansible"
                    else self._parse_python(full, rel)
                )
                with self._lock:
                    if entry:
                        self._cache[rel] = entry
                    else:
                        self._cache.pop(rel, None)
                    self._dirty.discard(rel)
        else:
            self.build()

    # ─────────────────────────────────────────────────────────────
    # Python parsing
    # ─────────────────────────────────────────────────────────────

    def _parse_python(self, full_path: str, rel_path: str):
        try:
            with open(full_path, "r", encoding="utf-8") as f:
                source = f.read()
        except Exception:
            return None

        try:
            tree = ast.parse(source)
        except Exception:
            return None

        entry = _FileEntry(rel_path, kind="python")

        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                doc = ast.get_docstring(node) or ""
                entry.add(_Symbol(
                    kind="class",
                    name=node.name,
                    sig=f"class {node.name}",
                    doc=doc[:80],
                    indent=0,
                ))
                for item in node.body:
                    if isinstance(item, ast.FunctionDef):
                        args  = _format_args(item)
                        m_doc = ast.get_docstring(item) or ""
                        entry.add(_Symbol(
                            kind="method",
                            name=item.name,
                            sig=f"def {item.name}({args})",
                            doc=m_doc[:80],
                            indent=1,
                        ))

            elif isinstance(node, ast.FunctionDef):
                args = _format_args(node)
                doc  = ast.get_docstring(node) or ""
                entry.add(_Symbol(
                    kind="function",
                    name=node.name,
                    sig=f"def {node.name}({args})",
                    doc=doc[:80],
                    indent=0,
                ))

        return entry if entry.symbols else None

    # ─────────────────────────────────────────────────────────────
    # Ansible parsing
    # ─────────────────────────────────────────────────────────────

    def _parse_ansible(self, full_path: str, rel_path: str,
                       visited: set, depth: int = 0) -> "_FileEntry | None":
        """
        Parse an Ansible YAML file and follow all import/include chains
        recursively. visited prevents cycles. No depth limit — follows
        everything as requested.
        """
        if not HAS_YAML:
            return None

        if full_path in visited:
            return None
        visited.add(full_path)

        try:
            with open(full_path, "r", encoding="utf-8") as f:
                raw = f.read()
        except Exception:
            return None

        try:
            data = yaml.safe_load(raw)
        except Exception:
            return None

        if not data:
            return None

        entry     = _FileEntry(rel_path, kind="ansible")
        base_dir  = os.path.dirname(full_path)

        # Playbooks are a list of plays; role task/handler files are a list
        # of tasks directly. Vars files are dicts. Handle all three.
        plays_or_tasks = data if isinstance(data, list) else []

        for item in plays_or_tasks:
            if not isinstance(item, dict):
                continue

            # ── Play-level (playbooks) ─────────────────────────────
            play_name = str(item.get("name", "") or "")
            hosts     = str(item.get("hosts", "") or "")
            if hosts:
                sig = f"[play] {play_name}" if play_name else f"[play] hosts={hosts}"
                entry.add(_Symbol(kind="play", name=play_name or hosts,
                                  sig=sig, doc="", indent=0))

            # ── Roles included in a play ───────────────────────────
            for role in _extract_roles(item):
                entry.add(_Symbol(kind="role", name=role,
                                  sig=f"  [role] {role}", doc="", indent=1))
                # Follow role tasks/main.yml
                role_tasks = os.path.join(
                    self.project_root, "roles", role, "tasks", "main.yml"
                )
                if os.path.exists(role_tasks) and role_tasks not in visited:
                    rel = self._rel(role_tasks)
                    child = self._parse_ansible(role_tasks, rel, visited, depth + 1)
                    if child:
                        # Inline the role's tasks under this entry
                        for sym in child.symbols:
                            sym.indent += 2
                            entry.add(sym)

            # ── Tasks (play tasks: or bare task list) ──────────────
            task_list = item.get("tasks", []) or []
            if not task_list and not hosts:
                # This item is itself a task (bare task file format)
                task_list = [item]

            for task in task_list:
                if not isinstance(task, dict):
                    continue
                self._extract_task(task, entry, base_dir, visited, depth)

            # ── Handlers ──────────────────────────────────────────
            for handler in (item.get("handlers") or []):
                if not isinstance(handler, dict):
                    continue
                hname = str(handler.get("name", "") or "")
                if hname:
                    entry.add(_Symbol(kind="handler", name=hname,
                                      sig=f"  [handler] {hname}",
                                      doc="", indent=1))

        # ── Vars files (dict at top level) ────────────────────────
        if isinstance(data, dict) and _is_vars_file(rel_path):
            for key in data:
                entry.add(_Symbol(kind="var", name=str(key),
                                  sig=f"  {key}", doc="", indent=0))

        return entry if entry.symbols else None

    def _extract_task(self, task: dict, entry: "_FileEntry",
                      base_dir: str, visited: set, depth: int):
        """
        Extract one task's name and module into entry, then follow any
        import_tasks / include_tasks / import_role / include_role keys.
        """
        task_name = str(task.get("name", "") or "")
        module    = _detect_ansible_module(task)

        if task_name or module:
            sig = f"  [{task_name}]" if task_name else "  [unnamed task]"
            if module:
                sig += f" → {module}"
            entry.add(_Symbol(
                kind="task", name=task_name or module or "task",
                sig=sig, doc="", indent=1,
            ))

        # ── Follow imports ─────────────────────────────────────────
        for key in ANSIBLE_IMPORT_KEYS:
            val = task.get(key)
            if not val:
                continue

            if key in ("import_role", "include_role"):
                role_name = val if isinstance(val, str) else (
                    val.get("name", "") if isinstance(val, dict) else ""
                )
                if role_name:
                    entry.add(_Symbol(kind="role", name=role_name,
                                      sig=f"    → role: {role_name}",
                                      doc="", indent=2))
                    role_tasks = os.path.join(
                        self.project_root, "roles", role_name, "tasks", "main.yml"
                    )
                    if os.path.exists(role_tasks) and role_tasks not in visited:
                        rel   = self._rel(role_tasks)
                        child = self._parse_ansible(role_tasks, rel, visited, depth + 1)
                        if child:
                            for sym in child.symbols:
                                sym.indent += 2
                                entry.add(sym)

            else:
                # import_tasks / include_tasks — value is a file path
                task_file = val if isinstance(val, str) else (
                    val.get("file", "") if isinstance(val, dict) else ""
                )
                if task_file:
                    # Resolve relative to base_dir first, then project root
                    for candidate in (
                        os.path.join(base_dir, task_file),
                        os.path.join(self.project_root, task_file),
                    ):
                        candidate = os.path.normpath(candidate)
                        if os.path.exists(candidate) and candidate not in visited:
                            rel   = self._rel(candidate)
                            entry.add(_Symbol(
                                kind="import", name=task_file,
                                sig=f"    → imports: {rel}",
                                doc="", indent=2,
                            ))
                            child = self._parse_ansible(
                                candidate, rel, visited, depth + 1
                            )
                            if child:
                                for sym in child.symbols:
                                    sym.indent += 2
                                    entry.add(sym)
                            break

    # ─────────────────────────────────────────────────────────────
    # File walker
    # ─────────────────────────────────────────────────────────────

    def _walk_source_files(self):
        """Yield (full_path, kind) for all Python and Ansible files."""
        for dirpath, dirnames, filenames in os.walk(self.project_root):
            dirnames[:] = [
                d for d in dirnames
                if d not in SKIP_DIRS and not d.startswith(".")
            ]
            for fname in filenames:
                full = os.path.join(dirpath, fname)
                rel  = self._rel(full)
                if fname.endswith(".py"):
                    yield full, "python"
                elif fname.endswith((".yml", ".yaml")) and HAS_YAML:
                    if _is_ansible_file(full, rel):
                        yield full, "ansible"

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
        line = f"{pad}{self.sig.strip()}"
        if self.doc:
            clean = self.doc.replace("\n", " ").strip()
            line += f'  # "{clean}"'
        return line


class _FileEntry:
    __slots__ = ("rel_path", "kind", "symbols")

    def __init__(self, rel_path: str, kind: str = "python"):
        self.rel_path = rel_path
        self.kind     = kind
        self.symbols: list[_Symbol] = []

    def add(self, symbol: _Symbol):
        self.symbols.append(symbol)

    def format(self) -> str:
        lines = [f"\n{self.rel_path}"]
        for sym in self.symbols:
            lines.append(sym.format())
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Ansible helpers
# ─────────────────────────────────────────────────────────────────────────────

# Modules that are never useful as "the module" for a task
_ANSIBLE_META_KEYS = {
    "name", "when", "register", "notify", "tags", "vars",
    "loop", "with_items", "with_list", "with_dict", "with_fileglob",
    "become", "become_user", "ignore_errors", "failed_when",
    "changed_when", "no_log", "delegate_to", "run_once",
    "environment", "block", "rescue", "always",
} | ANSIBLE_IMPORT_KEYS


def _detect_ansible_module(task: dict) -> str:
    """
    Return the Ansible module name used by a task dict.
    Skips meta-keys and returns the first remaining key.
    """
    for key in task:
        if key not in _ANSIBLE_META_KEYS:
            return key
    return ""


def _extract_roles(play: dict) -> list:
    """Extract role names from a play's 'roles:' list."""
    roles = play.get("roles", []) or []
    result = []
    for r in roles:
        if isinstance(r, str):
            result.append(r)
        elif isinstance(r, dict):
            name = str(r.get("role") or r.get("name", "") or "")
            if name:
                result.append(name)
    return result


def _is_ansible_file(full_path: str, rel_path: str) -> bool:
    """
    Heuristic: is this YAML file likely an Ansible file?
    Checks directory name against known Ansible dirs and
    does a quick content sniff for Ansible-specific keys.
    """
    # Directory-based detection
    parts = rel_path.replace("\\", "/").split("/")
    if any(p in ANSIBLE_DIRS for p in parts):
        return True

    # Content sniff — read first 512 bytes only
    try:
        with open(full_path, "r", encoding="utf-8") as f:
            head = f.read(512)
        ansible_markers = (
            "hosts:", "tasks:", "handlers:", "roles:",
            "ansible.builtin.", "import_tasks", "include_tasks",
            "import_role", "include_role", "become:", "register:",
        )
        return any(m in head for m in ansible_markers)
    except Exception:
        return False


def _is_vars_file(rel_path: str) -> bool:
    parts = rel_path.replace("\\", "/").split("/")
    return any(p in ("group_vars", "host_vars") for p in parts)


# ─────────────────────────────────────────────────────────────────────────────
# Python helpers
# ─────────────────────────────────────────────────────────────────────────────

def _format_args(node: ast.FunctionDef) -> str:
    args        = node.args
    parts       = []
    vararg_name = args.vararg.arg if args.vararg else None
    kwarg_name  = args.kwarg.arg  if args.kwarg  else None

    for arg in (args.args or []):
        if arg.annotation:
            try:
                parts.append(f"{arg.arg}: {ast.unparse(arg.annotation)}")
            except Exception:
                parts.append(arg.arg)
        else:
            parts.append(arg.arg)

    if vararg_name:
        parts.append(f"*{vararg_name}")
    for arg in (args.kwonlyargs or []):
        parts.append(arg.arg)
    if kwarg_name:
        parts.append(f"**{kwarg_name}")

    return ", ".join(parts)