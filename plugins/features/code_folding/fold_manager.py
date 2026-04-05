"""
fold_manager.py

Detects foldable regions in a QTextDocument and manages fold state.
Supports both indent-based (Python, YAML) and brace-based (JS, C) folding.
"""

import re
from PyQt6.QtGui import QTextDocument


# ── Region detection ──────────────────────────────────────────────────────────

def _detect_regions_indent(doc: QTextDocument) -> list[tuple[int, int]]:
    """
    Find foldable regions by indent level.
    A region starts at a line that ends with ':' or is followed by a more
    indented line, and ends at the last line of that indent level.
    Returns list of (start_block, end_block) — both inclusive, 0-indexed.
    """
    regions = []
    block_count = doc.blockCount()
    lines = []
    for i in range(block_count):
        block = doc.findBlockByNumber(i)
        text = block.text()
        if text.strip():
            indent = len(text) - len(text.lstrip())
        else:
            indent = None  # blank line — inherits context
        lines.append((text, indent))

    for i in range(len(lines) - 1):
        text, indent = lines[i]
        if indent is None:
            continue

        # Look ahead for a more indented block
        next_indent = None
        for j in range(i + 1, len(lines)):
            if lines[j][1] is not None:
                next_indent = lines[j][1]
                break

        if next_indent is None or next_indent <= indent:
            continue

        # Find the last line at next_indent or deeper
        end = i
        for j in range(i + 1, len(lines)):
            ni = lines[j][1]
            if ni is None:
                continue
            if ni > indent:
                end = j
            else:
                break

        if end > i:
            regions.append((i, end))

    return regions


def _detect_regions_brace(doc: QTextDocument) -> list[tuple[int, int]]:
    """
    Find foldable regions by matching braces { }.
    Returns list of (start_block, end_block) — both inclusive, 0-indexed.
    """
    regions = []
    stack = []
    block_count = doc.blockCount()

    for i in range(block_count):
        text = doc.findBlockByNumber(i).text()
        for ch in text:
            if ch == '{':
                stack.append(i)
            elif ch == '}':
                if stack:
                    start = stack.pop()
                    if i > start:
                        regions.append((start, i))

    return regions


_INDENT_EXTS = {'.py', '.yml', '.yaml', '.nix', '.md'}
_BRACE_EXTS  = {'.js', '.jsx', '.ts', '.tsx', '.json',
                '.c', '.cpp', '.h', '.java', '.go', '.rs', '.lua'}


def detect_regions(doc: QTextDocument,
                   file_path: str) -> list[tuple[int, int]]:
    """
    Choose the right detection strategy based on file extension.
    Falls back to indent-based for unknown types.
    """
    ext = ''
    if file_path:
        import os
        ext = os.path.splitext(file_path)[1].lower()

    if ext in _BRACE_EXTS:
        regions = _detect_regions_brace(doc)
    else:
        regions = _detect_regions_indent(doc)

    # Deduplicate and sort by start line
    seen = set()
    result = []
    for r in sorted(regions):
        if r not in seen:
            seen.add(r)
            result.append(r)
    return result


# ── Fold manager ──────────────────────────────────────────────────────────────

class FoldManager:
    """
    Tracks fold state for one editor instance.
    Call refresh(doc, file_path) whenever the document changes.
    Call toggle(start_line) to fold/unfold a region.
    """

    def __init__(self):
        self._regions: list[tuple[int, int]] = []   # (start, end) pairs
        self._folded:  set[int]              = set() # folded start lines

    # ── Public ────────────────────────────────────────────────────────────

    def refresh(self, doc: QTextDocument, file_path: str):
        """Re-detect regions. Preserves fold state for regions that still exist."""
        new_regions = detect_regions(doc, file_path)
        new_starts  = {r[0] for r in new_regions}
        self._folded  = self._folded & new_starts
        self._regions = new_regions

    def toggle(self, doc: QTextDocument, start_line: int):
        """Fold or unfold the region starting at start_line."""
        region = self._region_at(start_line)
        if region is None:
            return
        start, end = region
        if start in self._folded:
            self._unfold(doc, start, end)
            self._folded.discard(start)
        else:
            self._fold(doc, start, end)
            self._folded.add(start)

    def is_folded(self, start_line: int) -> bool:
        return start_line in self._folded

    def is_fold_start(self, line: int) -> bool:
        return any(r[0] == line for r in self._regions)

    def region_for_line(self, line: int) -> tuple[int, int] | None:
        """Return the region whose start line matches, or None."""
        return self._region_at(line)

    @property
    def regions(self) -> list[tuple[int, int]]:
        return self._regions

    @property
    def folded(self) -> set[int]:
        return self._folded

    # ── Internal ──────────────────────────────────────────────────────────

    def _region_at(self, start_line: int) -> tuple[int, int] | None:
        for r in self._regions:
            if r[0] == start_line:
                return r
        return None

    def _fold(self, doc: QTextDocument, start: int, end: int):
        doc.blockSignals(True)
        for i in range(start + 1, end + 1):
            block = doc.findBlockByNumber(i)
            if block.isValid():
                block.setVisible(False)
        doc.blockSignals(False)
        doc.markContentsDirty(
            doc.findBlockByNumber(start + 1).position(),
            doc.findBlockByNumber(end).position() +
            doc.findBlockByNumber(end).length()
        )

    def _unfold(self, doc: QTextDocument, start: int, end: int):
        doc.blockSignals(True)
        for i in range(start + 1, end + 1):
            block = doc.findBlockByNumber(i)
            if block.isValid():
                block.setVisible(True)
        doc.blockSignals(False)
        doc.markContentsDirty(
            doc.findBlockByNumber(start + 1).position(),
            doc.findBlockByNumber(end).position() +
            doc.findBlockByNumber(end).length()
        )