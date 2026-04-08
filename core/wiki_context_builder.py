"""
wiki_context_builder.py — Builds trimmed wiki context strings for AIWorker.

The caller uses this before constructing AIWorker to fetch the relevant wiki
pages and trim them to a token budget.  The resulting string is passed in as
`wiki_context=` — AIWorker stays decoupled from WikiManager entirely.

Usage
-----
    from core.wiki_context_builder import WikiContextBuilder

    builder = WikiContextBuilder(wiki_manager, char_budget=3000)
    ctx = builder.for_file(Path("ui/editor.py"))

    worker = AIWorker(..., wiki_context=ctx)
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional


# Rough chars-per-token estimate (conservative for code + prose mix)
_CHARS_PER_TOKEN = 3.5

# Separators that turn CamelCase / snake_case identifiers into word tokens
_RE_SPLIT = re.compile(r'[\s_\-/\\\.]+')
_RE_CAMEL = re.compile(r'(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])')


def _query_tokens(text: str) -> set[str]:
    """
    Break a natural-language query into a set of lowercase tokens,
    splitting on whitespace, underscores, CamelCase, and path separators.
    Filters out short stop-words.

    "How does RepoMap work with WikiContextBuilder?" →
        {'how', 'does', 'repo', 'map', 'work', 'with', 'wiki', 'context', 'builder'}
    """
    # Split CamelCase first
    text = _RE_CAMEL.sub(' ', text)
    # Then split on punctuation/whitespace/underscores
    tokens = _RE_SPLIT.split(text.lower())
    return {t for t in tokens if len(t) > 2}


def _module_tokens(rel: str) -> set[str]:
    """
    Break a relative file path into tokens the same way.

    "core/wiki_context_builder.py" →
        {'core', 'wiki', 'context', 'builder'}
    "ai/repo_map.py" →
        {'ai', 'repo', 'map'}
    """
    stem = Path(rel).stem          # "wiki_context_builder"
    parts = [Path(rel).parent.name, stem]   # ["core", "wiki_context_builder"]
    combined = ' '.join(parts)
    return _query_tokens(combined)


def _relevance_score(query_tokens: set[str], rel: str, summary: str) -> int:
    """
    Score a wiki page against the query.
    +2 per query token that appears in the module path tokens.
    +1 per query token that appears in the summary text.
    """
    mod_tokens   = _module_tokens(rel)
    summary_lower = summary.lower()
    score = 0
    for t in query_tokens:
        if t in mod_tokens:
            score += 2
        elif t in summary_lower:
            score += 1
    return score


# Patterns that indicate a symbol reference in a query
_RE_DEF       = re.compile(r'def\s+([A-Za-z_][A-Za-z0-9_]*)')
_RE_CLASS_KW  = re.compile(r'class\s+([A-Za-z_][A-Za-z0-9_]*)')
_RE_METHOD    = re.compile(r'([A-Za-z_][A-Za-z0-9_]*)\s*\(')
_RE_SNAKE     = re.compile(r'([a-z_][a-z0-9_]{3,})')
_RE_CAMEL_ID  = re.compile(r'([A-Z][a-zA-Z0-9]{2,})')


def _extract_symbol_names(text: str) -> list[str]:
    """
    Extract likely symbol names (methods, classes, functions) from a query.
    Returns them in priority order:
      1. Explicit `def foo` / `class Foo` mentions
      2. CamelCase identifiers (class names)
      3. snake_case identifiers with underscores (method names)
      4. Anything followed by `(` (function calls)

    Filters out common English words and very short tokens.
    """
    _STOPWORDS = {
        'the', 'and', 'for', 'not', 'with', 'this', 'that', 'have',
        'from', 'they', 'will', 'been', 'what', 'when', 'where', 'how',
        'does', 'did', 'can', 'could', 'should', 'would', 'like', 'just',
        'about', 'into', 'also', 'some', 'than', 'then', 'there', 'its',
        'def', 'class', 'return', 'self', 'true', 'false', 'none', 'pass',
        'print', 'open', 'list', 'dict', 'set', 'str', 'int', 'bool',
    }

    seen:    set[str]  = set()
    results: list[str] = []

    def _add(name: str):
        if name and name.lower() not in _STOPWORDS and name not in seen:
            seen.add(name)
            results.append(name)

    # Explicit keyword references — highest confidence
    for m in _RE_DEF.finditer(text):
        _add(m.group(1))
    for m in _RE_CLASS_KW.finditer(text):
        _add(m.group(1))

    # CamelCase (class names)
    for m in _RE_CAMEL_ID.finditer(text):
        _add(m.group(1))

    # snake_case names (method names) — require underscore to filter English words
    for m in _RE_SNAKE.finditer(text):
        name = m.group(1)
        if '_' in name:   # must contain underscore to avoid plain English words
            _add(name)

    # Anything followed by () — function calls
    for m in _RE_METHOD.finditer(text):
        _add(m.group(1))

    return results


class WikiContextBuilder:
    """
    Fetches wiki pages from WikiManager and trims them to fit a character
    budget before they are injected into an AIWorker prompt.

    Parameters
    ----------
    wiki_manager : WikiManager
        The active WikiManager instance for the open project.
    char_budget : int
        Maximum characters of wiki text to include across all pages.
        Default ~6 000 chars — enough for index + 2-3 relevant pages.
    include_index : bool
        Whether to prepend a short excerpt from index.md for repo-level
        grounding.  Counts against the budget.  Defaults to True for chat.
    """

    def __init__(
        self,
        wiki_manager,
        char_budget: int = 6000,
        include_index: bool = True,
        repo_map=None,
    ) -> None:
        self._wm       = wiki_manager
        self._budget   = char_budget
        self._include_index = include_index
        self._repo_map = repo_map   # optional RepoMap for symbol lookup

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def for_file(self, source_path: Path) -> str:
        """
        Return wiki context for *source_path* and its direct dependencies,
        trimmed to the char budget.

        Returns an empty string if no wiki exists yet.
        """
        raw = self._wm.context_for(source_path, include_deps=True)
        if not raw:
            return ""

        parts: list[str] = []
        remaining = self._budget

        if self._include_index:
            index_excerpt = self._index_excerpt(min(600, remaining // 4))
            if index_excerpt:
                parts.append(index_excerpt)
                remaining -= len(index_excerpt)

        sections = re.split(r"\n---\n", raw)
        for section in sections:
            trimmed = self._trim_section(section, remaining)
            if not trimmed:
                break
            parts.append(trimmed)
            remaining -= len(trimmed)
            if remaining <= 0:
                break

        return "\n\n---\n\n".join(parts) if parts else ""

    def for_prompt(self, prompt_text: str, source_path: Optional[Path] = None) -> str:
        """
        Return wiki context relevant to an arbitrary prompt string.

        Matching uses token overlap so "RepoMap" matches "repo_map.py",
        "WikiContextBuilder" matches "wiki_context_builder.py", etc.

        Strategy:
          1. Always include a trimmed index.md overview for grounding.
          2. Current file's page (if source_path given).
          3. Rank all wiki pages by token overlap with the query,
             inject highest-scoring pages until budget is exhausted.
        """
        parts: list[str] = []
        remaining = self._budget
        seen: set[str] = set()

        # 1. Index overview — always included for grounding
        index_excerpt = self._index_excerpt(min(800, remaining // 4))
        if index_excerpt:
            parts.append(index_excerpt)
            remaining -= len(index_excerpt)

        # 2. Current file
        if source_path:
            primary = self._wm.context_for(source_path, include_deps=False)
            if primary:
                trimmed = self._trim_section(primary, min(remaining // 2, 1500))
                parts.append(trimmed)
                remaining -= len(trimmed)
                seen.add(str(source_path.name))

        # 3. Symbol-aware lookup — highest priority
        # Extract method/class names from the query, resolve to source files
        # via the repo map, then fetch the EXACT implementation from disk
        # using AST. Real source beats wiki summaries for "what does X do".
        if self._repo_map:
            for sym_name in _extract_symbol_names(prompt_text):
                if remaining <= 300:
                    break
                for rel in self._repo_map.find_symbol(sym_name):
                    if remaining <= 300:
                        break
                    # Get exact source from disk via AST
                    source_block = self._repo_map.get_symbol_source(rel, sym_name)
                    if source_block:
                        trimmed = self._trim_section(source_block, min(remaining, 2000))
                        parts.append(trimmed)
                        remaining -= len(trimmed)
                    # Also inject the wiki summary for broader context
                    # but only if we haven't used this file already
                    if Path(rel).name not in seen:
                        page = self._wm._read_page(rel)
                        if page:
                            trimmed = self._trim_section(page, min(remaining, 800))
                            parts.append(trimmed)
                            remaining -= len(trimmed)
                        seen.add(Path(rel).name)

        # 4. Score all summaries against the query and pick the best ones
        query_tokens = _query_tokens(prompt_text)
        summaries    = self._wm.all_summaries()   # dict: rel → summary str

        scored: list[tuple[int, str]] = []
        for rel, summary in summaries.items():
            if Path(rel).name in seen:
                continue
            score = _relevance_score(query_tokens, rel, summary)
            if score > 0:
                scored.append((score, rel))

        # Sort descending — highest overlap first
        scored.sort(key=lambda x: x[0], reverse=True)

        for _, rel in scored:
            if remaining <= 300:
                break
            page = self._wm._read_page(rel)
            if not page:
                continue
            trimmed = self._trim_section(page, min(remaining, 1200))
            parts.append(trimmed)
            remaining -= len(trimmed)
            seen.add(Path(rel).name)

        return "\n\n---\n\n".join(parts) if parts else ""

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _trim_section(self, text: str, max_chars: int) -> str:
        """Trim *text* to *max_chars*, breaking on a line boundary."""
        if not text or max_chars <= 0:
            return ""
        if len(text) <= max_chars:
            return text
        truncated = text[:max_chars]
        last_nl = truncated.rfind("\n")
        if last_nl > max_chars // 2:
            truncated = truncated[:last_nl]
        return truncated + "\n…(truncated)"

    def _index_excerpt(self, max_chars: int) -> str:
        """Return the Overview + Module Index table from index.md, trimmed."""
        index_path = self._wm._wiki_dir / "index.md"
        if not index_path.exists():
            return ""
        text = index_path.read_text(encoding="utf-8")
        m = re.search(r"## Overview\n(.*?)(?=\n##|\Z)", text, re.DOTALL)
        if m:
            excerpt = f"## Overview\n{m.group(1).strip()}"
            return self._trim_section(excerpt, max_chars)
        return self._trim_section(text, max_chars)