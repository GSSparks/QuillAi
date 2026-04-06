"""
wiki_manager.py — Orchestrates QuillAI's Markdown wiki knowledge base.

Responsibilities
----------------
- Maintain `~/.config/quillai/wiki/<project>/` directory tree (one .md per .py source file)
- Track file hashes in `~/.config/quillai/wiki/<project>/meta.json` to detect stale pages
- Rebuild stale pages via WikiGenerator on demand or on trigger
- Fill in `Dependents` sections after a full rebuild
- Expose context retrieval for AI completions (replaces ChromaDB)

Typical usage
-------------
    from pathlib import Path
    from core.wiki_manager import WikiManager

    wm = WikiManager(repo_root=Path("/path/to/project"))
    wm.update()                          # incremental — only stale files
    ctx = wm.context_for(Path("ui/editor.py"))  # returns wiki text for AI prompt
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from pathlib import Path
from typing import Optional

from core.wiki_generator import WikiGenerator


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CONFIG_BASE = Path.home() / ".config" / "quillai"
_INDEX_PAGE = "index.md"
_IGNORE_DIRS = {
    ".git", "__pycache__", ".quillai", "venv", ".venv",
    "node_modules", "dist", "build", ".mypy_cache", ".ruff_cache",
}
_DEPENDENTS_PLACEHOLDER = "<!-- dependents: auto-filled by WikiManager -->"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_git_root(path: Path) -> Optional[Path]:
    """Walk up from *path* to find the nearest .git directory.
    Returns the repo root Path, or None if not inside a git repo."""
    current = path.resolve()
    for parent in [current, *current.parents]:
        if (parent / ".git").exists():
            return parent
    return None


def _file_hash(path: Path) -> str:
    """SHA-256 of a file's contents (hex string)."""
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _wiki_path_for(wiki_dir: Path, source_rel: Path) -> Path:
    """Map `ui/editor.py` → `<wiki_dir>/ui/editor.md`."""
    md_rel = source_rel.with_suffix(".md")
    return wiki_dir / md_rel


# Extensions to explicitly skip even if they match a known type
_WIKI_IGNORE_PATTERNS = {
    "package-lock.json", "yarn.lock", "poetry.lock", "Pipfile.lock",
    "*.min.js", "*.min.css", "*.map",
}

# All file extensions the wiki will document
_WIKI_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx",
    ".html", ".htm", ".css", ".scss", ".sass", ".less",
    ".json", ".toml", ".xml", ".yml", ".yaml",
    ".tf", ".tfvars", ".hcl", ".nix",
    ".sh", ".bash", ".zsh", ".fish",
    ".pl", ".pm", ".lua", ".rb", ".php",
    ".rs", ".go", ".c", ".h", ".cpp", ".hpp",
    ".java", ".kt", ".swift",
    ".md", ".rst", ".txt", ".tex",
    ".sql",
}

# Max files to wiki in a single repo — prevents runaway on monorepos
_WIKI_MAX_FILES = 500

def _collect_source_files(repo_root: Path) -> list[Path]:
    """Return all wiki-able source files in the repo, ignoring noise dirs."""
    _ignore_names = {
        "package-lock.json", "yarn.lock", "poetry.lock", "Pipfile.lock",
    }
    result: list[Path] = []
    for root, dirs, files in os.walk(repo_root):
        root_path = Path(root)
        dirs[:] = [d for d in dirs if d not in _IGNORE_DIRS]
        for f in files:
            p = Path(f)
            if p.name in _ignore_names:
                continue
            if p.name.endswith((".min.js", ".min.css", ".map")):
                continue
            if p.suffix.lower() in _WIKI_EXTENSIONS:
                result.append((root_path / f).resolve())
            if len(result) >= _WIKI_MAX_FILES:
                return sorted(result)
    return sorted(result)


def _parse_dependents_from_dep_sections(
    pages: dict[str, str]
) -> dict[str, list[str]]:
    """
    Build a reverse-dependency map.

    For each wiki page, parse its Dependencies section and record
    that the listed modules depend on this one.

    Returns {module_rel_path: [list of modules that import it]}.
    """
    reverse: dict[str, list[str]] = {}
    dep_re = re.compile(r"## Dependencies\n(.*?)(?=\n##|\Z)", re.DOTALL)
    bullet_re = re.compile(r"`([^`]+\.[a-z]+)`")

    for module_path, wiki_text in pages.items():
        m = dep_re.search(wiki_text)
        if not m:
            continue
        for dep in bullet_re.findall(m.group(1)):
            reverse.setdefault(dep, []).append(module_path)

    return reverse


def _fill_dependents(wiki_text: str, dependents: list[str]) -> str:
    """Replace the dependents placeholder with actual data."""
    if dependents:
        block = "\n".join(f"- `{d}`" for d in sorted(dependents))
    else:
        block = "_None._"
    return wiki_text.replace(
        _DEPENDENTS_PLACEHOLDER,
        block,
    )


# ---------------------------------------------------------------------------
# WikiManager
# ---------------------------------------------------------------------------

class WikiManager:
    """
    Manages the Markdown wiki knowledge base for a QuillAI project.

    Parameters
    ----------
    repo_root : Path
        Absolute path to the repository root.
    model : str
        Anthropic model for generation (passed to WikiGenerator).
    max_tokens : int
        Max tokens per generation call.
    on_progress : callable, optional
        Called with (current: int, total: int, label: str) during rebuilds.
        Useful for driving a progress indicator in the UI.
    """

    def __init__(
        self,
        repo_root: Path,
        model: str = "",
        max_tokens: int = 2048,
        api_url: str = "",
        api_key: str = "",
        backend: str = "openai",
        on_progress=None,
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.enabled = _find_git_root(self.repo_root) is not None
        if not self.enabled:
            print(f"[WikiManager] {self.repo_root} is not a git repo — wiki disabled.")
            self._on_progress = on_progress
            self._lock = threading.Lock()
            self._meta: dict[str, str] = {}
            return

        self._generator = WikiGenerator(
            self.repo_root,
            model=model,
            max_tokens=max_tokens,
            api_url=api_url,
            api_key=api_key,
            backend=backend,
        )
        self._on_progress = on_progress
        self._lock = threading.Lock()

        self._wiki_dir.mkdir(parents=True, exist_ok=True)
        self._meta: dict[str, str] = self._load_meta()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update(self, force: bool = False) -> list[str]:
        """
        Incremental update: regenerate wiki pages for stale or missing files.

        Parameters
        ----------
        force : bool
            If True, regenerate ALL pages regardless of hash.

        Returns
        -------
        list[str]
            Relative paths of files whose wiki pages were (re)generated.
        """
        if not self.enabled:
            return []
        with self._lock:
            py_files = _collect_source_files(self.repo_root)
            stale = [
                f for f in py_files
                if force or self._is_stale(f)
            ]

            if not stale:
                return []

            updated: list[str] = []
            for i, src in enumerate(stale):
                rel = str(src.relative_to(self.repo_root))
                if self._on_progress:
                    self._on_progress(i + 1, len(stale), rel)
                try:
                    wiki_text = self._generator.generate_page(src)
                    self._write_page(src, wiki_text)
                    self._meta[rel] = _file_hash(src)
                    updated.append(rel)
                except Exception as exc:
                    print(f"[WikiManager] Failed to generate page for {rel}: {exc}")

            if updated:
                self._fill_all_dependents()
                self._rebuild_index()
                self._save_meta()

            return updated

    def rebuild_all(self) -> list[str]:
        """Force-regenerate every wiki page in the repo."""
        return self.update(force=True)

    def update_file(self, source_path: Path) -> bool:
        """
        Regenerate the wiki page for a single file if stale.

        Returns True if the page was updated.
        """
        if not self.enabled:
            return False
        with self._lock:
            src = self._resolve(source_path)
            if not src.exists() or not str(src).endswith(".py"):
                return False
            if not self._is_stale(src):
                return False
            try:
                wiki_text = self._generator.generate_page(src)
                self._write_page(src, wiki_text)
                rel = str(src.relative_to(self.repo_root))
                self._meta[rel] = _file_hash(src)
                self._fill_all_dependents()
                self._rebuild_index()
                self._save_meta()
                return True
            except Exception as exc:
                print(f"[WikiManager] Failed to update {source_path}: {exc}")
                return False

    def context_for(self, source_path: Path, include_deps: bool = True) -> str:
        """
        Return wiki context suitable for injection into an AI completion prompt.

        Includes the wiki page for *source_path* plus pages for its direct
        intra-project dependencies (one level deep).

        Parameters
        ----------
        source_path : Path
            The file currently open in the editor.
        include_deps : bool
            Whether to include dependency wiki pages.

        Returns
        -------
        str
            Concatenated Markdown wiki content, or empty string if no wiki exists.
        """
        if not self.enabled:
            return ""
        src = self._resolve(source_path)
        try:
            rel = str(src.relative_to(self.repo_root))
        except ValueError:
            return ""

        sections: list[str] = []

        # Primary page
        primary = self._read_page(rel)
        if primary:
            sections.append(f"<!-- wiki: {rel} -->\n{primary}")

        # Dependency pages
        if include_deps and primary:
            for dep_rel in self._parse_deps(primary):
                dep_text = self._read_page(dep_rel)
                if dep_text:
                    sections.append(f"<!-- wiki: {dep_rel} -->\n{dep_text}")

        return "\n\n---\n\n".join(sections)

    def page_path(self, source_rel: str) -> Path:
        """Return the wiki .md path for a given source relative path."""
        return _wiki_path_for(self._wiki_dir, Path(source_rel))

    def all_summaries(self) -> dict[str, str]:
        """Return {rel_path: one_line_summary} for all generated wiki pages."""
        result: dict[str, str] = {}
        for rel in self._meta:
            text = self._read_page(rel)
            if text:
                result[rel] = self._generator.extract_summary(text)
        return result

    def stale_files(self) -> list[str]:
        """Return relative paths of .py files whose wiki pages are out of date."""
        if not self.enabled:
            return []
        return [
            str(f.relative_to(self.repo_root))
            for f in _collect_source_files(self.repo_root)
            if self._is_stale(f)
        ]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @property
    def _wiki_dir(self) -> Path:
        """Per-project wiki dir: ~/.config/quillai/wiki/<project_name>/"""
        project_name = self.repo_root.name
        return _CONFIG_BASE / "wiki" / project_name

    @property
    def _meta_path(self) -> Path:
        """Per-project meta file: ~/.config/quillai/wiki/<project_name>/meta.json"""
        return self._wiki_dir / "meta.json"

    def _load_meta(self) -> dict[str, str]:
        if self._meta_path.exists():
            try:
                return json.loads(self._meta_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    def _save_meta(self) -> None:
        self._meta_path.parent.mkdir(parents=True, exist_ok=True)
        self._meta_path.write_text(
            json.dumps(self._meta, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _is_stale(self, src: Path) -> bool:
        rel = str(src.relative_to(self.repo_root))
        wiki = _wiki_path_for(self._wiki_dir, Path(rel))
        if not wiki.exists():
            return True
        stored_hash = self._meta.get(rel)
        if not stored_hash:
            return True
        return _file_hash(src) != stored_hash

    def _write_page(self, src: Path, wiki_text: str) -> None:
        rel = Path(src.relative_to(self.repo_root))
        out = _wiki_path_for(self._wiki_dir, rel)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(wiki_text, encoding="utf-8")

    def _read_page(self, rel: str) -> Optional[str]:
        path = _wiki_path_for(self._wiki_dir, Path(rel))
        if path.exists():
            return path.read_text(encoding="utf-8")
        return None

    def _fill_all_dependents(self) -> None:
        """
        Read all current wiki pages, build the reverse-dep map,
        and write the Dependents section into each page.
        """
        pages: dict[str, str] = {}
        for rel in self._meta:
            text = self._read_page(rel)
            if text:
                pages[rel] = text

        reverse = _parse_dependents_from_dep_sections(pages)

        for rel, text in pages.items():
            dependents = reverse.get(rel, [])
            updated = _fill_dependents(text, dependents)
            if updated != text:
                out = _wiki_path_for(self._wiki_dir, Path(rel))
                out.write_text(updated, encoding="utf-8")

    def _rebuild_index(self) -> None:
        """Regenerate the top-level index.md from current page summaries."""
        summaries = self.all_summaries()
        if not summaries:
            return
        try:
            index_text = self._generator.generate_index(summaries)
            index_path = self._wiki_dir / _INDEX_PAGE
            index_path.write_text(index_text, encoding="utf-8")
        except Exception as exc:
            print(f"[WikiManager] Failed to rebuild index: {exc}")

    def _parse_deps(self, wiki_text: str) -> list[str]:
        """Extract dependency paths from a wiki page's Dependencies section."""
        m = re.search(r"## Dependencies\n(.*?)(?=\n##|\Z)", wiki_text, re.DOTALL)
        if not m:
            return []
        return re.findall(r"`([^`]+\.py)`", m.group(1))

    def _resolve(self, path: Path) -> Path:
        path = Path(path)
        if not path.is_absolute():
            path = self.repo_root / path
        return path.resolve()
