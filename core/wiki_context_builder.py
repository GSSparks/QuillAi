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
        Default ~3 000 chars ≈ ~860 tokens — leaves plenty of room for
        the actual code context and completion.
    include_index : bool
        Whether to prepend a short excerpt from index.md for repo-level
        grounding.  Counts against the budget.
    """

    def __init__(
        self,
        wiki_manager,
        char_budget: int = 3000,
        include_index: bool = False,
    ) -> None:
        self._wm = wiki_manager
        self._budget = char_budget
        self._include_index = include_index

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

        # Optionally prepend a trimmed index overview
        if self._include_index:
            index_excerpt = self._index_excerpt(min(600, remaining // 3))
            if index_excerpt:
                parts.append(index_excerpt)
                remaining -= len(index_excerpt)

        # Split into per-page sections and add greedily
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

        If *source_path* is provided, starts with that file's wiki page.
        Additionally searches summaries for modules whose names appear in
        the prompt (e.g. "how does lsp_manager handle hover?").
        """
        parts: list[str] = []
        remaining = self._budget
        seen: set[str] = set()

        # Primary: current file
        if source_path:
            primary = self._wm.context_for(source_path, include_deps=False)
            if primary:
                trimmed = self._trim_section(primary, remaining)
                parts.append(trimmed)
                remaining -= len(trimmed)
                seen.add(str(source_path.name))

        # Secondary: scan summaries for modules mentioned in the prompt
        prompt_lower = prompt_text.lower()
        summaries = self._wm.all_summaries()
        for rel, _summary in summaries.items():
            if remaining <= 200:
                break
            module_name = Path(rel).stem.lower()
            if module_name in seen:
                continue
            if module_name in prompt_lower:
                page = self._wm._read_page(rel)
                if page:
                    trimmed = self._trim_section(page, remaining)
                    parts.append(trimmed)
                    remaining -= len(trimmed)
                    seen.add(module_name)

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
        # Walk back to last newline for a clean cut
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
        # Pull out just the Overview section
        m = re.search(r"## Overview\n(.*?)(?=\n##|\Z)", text, re.DOTALL)
        if m:
            excerpt = f"## Overview\n{m.group(1).strip()}"
            return self._trim_section(excerpt, max_chars)
        return self._trim_section(text, max_chars)