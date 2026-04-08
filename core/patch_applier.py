"""
core/patch_applier.py

Applies AI-suggested code changes to files on disk.

Modes
-----
function : Replace a single named function or class using AST.
           Stores the original for one-level undo.
full     : Show DiffApplyDialog then write the whole file.

Called from ChatRenderer.handle_chat_link when an apply: URL is clicked.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path
from typing import Optional


# One-level undo stack: {abs_path: original_source}
_undo_stack: dict[str, str] = {}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def apply_function(file_path: str, new_source: str,
                   parent_widget=None) -> tuple[bool, str]:
    """
    Replace the first function or class in *new_source* that exists in
    *file_path*, using AST to locate the exact line range.

    Stores original in undo stack.
    Returns (success, message).
    """
    path = Path(file_path)
    if not path.exists():
        return False, f"File not found: {file_path}"

    try:
        original = path.read_text(encoding="utf-8")
    except Exception as e:
        return False, f"Could not read {file_path}: {e}"

    # Find the name of the top-level symbol in new_source
    sym_name = _top_level_name(new_source)
    if not sym_name:
        return False, "Could not identify a function or class in the provided code."

    # Locate that symbol in the original file
    try:
        orig_tree = ast.parse(original)
    except SyntaxError as e:
        return False, f"Could not parse {path.name}: {e}"

    orig_lines = original.splitlines(keepends=True)
    target_node = None

    for node in ast.walk(orig_tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name == sym_name:
                target_node = node
                break

    if target_node is None:
        return False, f"Could not find '{sym_name}' in {path.name}."

    # Validate new_source parses cleanly
    try:
        ast.parse(new_source)
    except SyntaxError as e:
        return False, f"New code has a syntax error: {e}"

    # Detect indentation of original symbol and match it
    start_line = target_node.lineno - 1   # 0-indexed
    end_line   = getattr(target_node, "end_lineno", start_line + 1)  # inclusive

    # Preserve leading indentation from original
    original_indent = _leading_indent(orig_lines[start_line])
    new_lines = _reindent(new_source, original_indent)

    # Rebuild file
    before = orig_lines[:start_line]
    after  = orig_lines[end_line:]   # end_lineno is inclusive so skip it

    # Ensure new_lines ends with newline
    if new_lines and not new_lines[-1].endswith("\n"):
        new_lines[-1] += "\n"

    updated = "".join(before) + "".join(new_lines) + "".join(after)

    # Final syntax check
    try:
        ast.parse(updated)
    except SyntaxError as e:
        return False, f"Updated file has a syntax error: {e}"

    # Save to undo stack and write
    _undo_stack[str(path.resolve())] = original
    try:
        path.write_text(updated, encoding="utf-8")
    except Exception as e:
        return False, f"Could not write {file_path}: {e}"

    return True, f"Applied '{sym_name}' to {path.name}."


def apply_full(file_path: str, new_source: str,
               parent_widget=None) -> tuple[bool, str]:
    """
    Show DiffApplyDialog for *file_path* vs *new_source*.
    Writes the file if accepted.
    Returns (success, message).
    """
    from ui.diff_apply_dialog import DiffApplyDialog

    path = Path(file_path)
    if not path.exists():
        # New file — write directly without diff
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(new_source, encoding="utf-8")
            return True, f"Created {path.name}."
        except Exception as e:
            return False, f"Could not create {file_path}: {e}"

    try:
        original = path.read_text(encoding="utf-8")
    except Exception as e:
        return False, f"Could not read {file_path}: {e}"

    dlg = DiffApplyDialog(original, new_source, parent_widget)
    if dlg.exec() and dlg.accepted_code is not None:
        _undo_stack[str(path.resolve())] = original
        try:
            path.write_text(dlg.accepted_code, encoding="utf-8")
            return True, f"Applied full rewrite to {path.name}."
        except Exception as e:
            return False, f"Could not write {file_path}: {e}"
    return False, "Cancelled."


def undo_last(file_path: str) -> tuple[bool, str]:
    """
    Restore the previous version of *file_path* from the undo stack.
    Returns (success, message).
    """
    abs_path = str(Path(file_path).resolve())
    if abs_path not in _undo_stack:
        return False, f"No undo available for {os.path.basename(file_path)}."

    original = _undo_stack.pop(abs_path)
    try:
        Path(abs_path).write_text(original, encoding="utf-8")
        return True, f"Undid changes to {os.path.basename(file_path)}."
    except Exception as e:
        return False, f"Could not restore {file_path}: {e}"


def has_undo(file_path: str) -> bool:
    return str(Path(file_path).resolve()) in _undo_stack


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _top_level_name(source: str) -> Optional[str]:
    """Return the name of the first top-level function or class in source."""
    try:
        tree = ast.parse(source)
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                 ast.ClassDef)):
                return node.name
    except Exception:
        pass
    return None


def _leading_indent(line: str) -> str:
    """Return the leading whitespace of a line."""
    return line[: len(line) - len(line.lstrip())]


def _reindent(source: str, target_indent: str) -> list[str]:
    """
    Reindent *source* so its top-level lines use *target_indent*.
    Returns a list of lines with newlines.
    """
    lines = source.splitlines(keepends=True)
    if not lines:
        return lines

    # Detect current base indent (indent of first non-empty line)
    base = ""
    for line in lines:
        stripped = line.lstrip()
        if stripped:
            base = line[: len(line) - len(stripped)]
            break

    if base == target_indent:
        return lines

    result = []
    for line in lines:
        if line.strip() == "":
            result.append(line)
            continue
        if base and line.startswith(base):
            result.append(target_indent + line[len(base):])
        else:
            result.append(line)
    return result


# ---------------------------------------------------------------------------
# Perl subroutine replacement
# ---------------------------------------------------------------------------

import re as _re

_RE_PERL_SUB = _re.compile(
    r'^(sub\s+(\w+)\s*(?:\([^)]*\)\s*)?)\{',
    _re.MULTILINE
)


def _find_perl_sub_range(source: str, sub_name: str) -> tuple[int, int] | None:
    """
    Find the line range (start, end) inclusive of the named Perl sub
    using brace counting. Returns None if not found.
    """
    lines = source.splitlines(keepends=True)
    # Find the line where sub_name begins
    start_line = None
    for i, line in enumerate(lines):
        if _re.match(rf'^\s*sub\s+{_re.escape(sub_name)}\s*(?:\([^)]*\)\s*)?\{{', line):
            start_line = i
            break
        # Multi-line signature: sub name \n {
        if _re.match(rf'^\s*sub\s+{_re.escape(sub_name)}\s*$', line.rstrip()):
            # Look ahead for opening brace
            for j in range(i, min(i + 5, len(lines))):
                if '{' in lines[j]:
                    start_line = i
                    break
            if start_line is not None:
                break

    if start_line is None:
        return None

    # Count braces from start_line until depth hits 0
    depth = 0
    for i in range(start_line, len(lines)):
        depth += lines[i].count('{') - lines[i].count('}')
        if depth == 0 and i > start_line:
            return start_line, i

    return None


def _perl_sub_name(source: str) -> str | None:
    """Return the name of the first sub in source."""
    m = _RE_PERL_SUB.search(source)
    return m.group(2) if m else None


def apply_perl_function(file_path: str, new_source: str,
                        parent_widget=None) -> tuple[bool, str]:
    """
    Replace the first Perl subroutine in *new_source* that exists in
    *file_path*, using brace counting to locate the exact line range.

    Stores original in undo stack.
    Returns (success, message).
    """
    path = Path(file_path)
    if not path.exists():
        return False, f"File not found: {file_path}"

    try:
        original = path.read_text(encoding="utf-8")
    except Exception as e:
        return False, f"Could not read {file_path}: {e}"

    sub_name = _perl_sub_name(new_source)
    if not sub_name:
        # Fall back to full file replace
        return apply_full(file_path, new_source, parent_widget)

    result = _find_perl_sub_range(original, sub_name)
    if result is None:
        return False, f"Could not find sub '{sub_name}' in {path.name}."

    start_line, end_line = result
    orig_lines = original.splitlines(keepends=True)

    # Preserve leading indentation
    orig_indent = _leading_indent(orig_lines[start_line])
    new_lines   = _reindent(new_source.strip() + "\n", orig_indent)
    if new_lines and not new_lines[-1].endswith("\n"):
        new_lines[-1] += "\n"

    updated = (
        "".join(orig_lines[:start_line])
        + "".join(new_lines)
        + "".join(orig_lines[end_line + 1:])
    )

    _undo_stack[str(path.resolve())] = original
    try:
        path.write_text(updated, encoding="utf-8")
    except Exception as e:
        return False, f"Could not write {file_path}: {e}"

    return True, f"Applied sub '{sub_name}' to {path.name}."