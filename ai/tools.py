"""
ai/tools.py

Tool implementations for the QuillAI agent loop.

Read tools  — silent, no confirmation required
Write tools — queued, confirmed as a batch at the end
"""

from __future__ import annotations
import os
import re
import subprocess
from pathlib import Path


# ── Tool registry ─────────────────────────────────────────────────────────────

TOOL_DEFINITIONS = """
Available tools (emit as XML tags in your response):

READ TOOLS (no confirmation needed):
  <tool_call name="grep" pattern="..." path="." flags="-rn">Search for pattern in files</tool_call>
  <tool_call name="read_file" path="..." start="1" end="50">Read lines from a file</tool_call>
  <tool_call name="find_files" pattern="*.py" path=".">Find files matching glob</tool_call>
  <tool_call name="find_symbol" name="symbol_name">Look up a symbol in the repo map</tool_call>
  <tool_call name="run_shell" command="...">Run a read-only shell command (git log, wc, etc)</tool_call>

WRITE TOOLS (batched and confirmed by user at end):
  <tool_call name="patch_file" path="..." start_line="N" end_line="M">replacement lines</tool_call>
  <tool_call name="write_file" path="...">COMPLETE FILE CONTENT HERE — every line, no placeholders</tool_call>
  <tool_call name="shell_write" command="...">Run a write shell command (sed -i, mv, etc)</tool_call>

FILE EDITING RULES — follow strictly:
- ALWAYS run: run_shell command="wc -l <file>" before reading any file
- Read the ENTIRE file before proposing any changes (use multiple read_file calls if needed)
- For files with FEWER than 150 lines: use write_file — put the ENTIRE new file content
  as the tag body. Every line. No summaries, no placeholders, no "rest of file unchanged".
- For files with 150+ lines: use patch_file with start_line/end_line from the read_file output
  - start_line and end_line are the line numbers shown in the read_file output
  - The content between the tags replaces lines start_line through end_line inclusive
  - Never guess line numbers — only use numbers from an actual read_file result
- Never use patch_file with old/new string matching
- Never reconstruct or guess file content from memory

General rules:
- Use read tools freely to investigate before proposing changes
- Emit ALL write tool calls immediately once investigation is complete
- Do NOT wait for user confirmation before emitting write tools — the review dialog handles that
- Never emit write tools mid-investigation
- After all tool calls, provide your final answer/explanation
- Use <agent_done/> when you have finished all tool calls and given your answer
"""


# ── Tool execution ────────────────────────────────────────────────────────────

# ── Write tool implementations ───────────────────────────────────────────────

def _tool_patch_file_by_line(attrs: dict, root: str) -> tuple[bool, str]:
    """
    Replace lines start_line..end_line (1-indexed, inclusive) with new content.
    The replacement text is the tag body (attrs["_body"]).
    """
    import os
    path       = attrs.get("path", "")
    start_line = attrs.get("start_line")
    end_line   = attrs.get("end_line")
    body       = attrs.get("_body", "").strip("\n")

    if not path:
        return False, "patch_file: path is required"
    if start_line is None or end_line is None:
        return False, "patch_file: start_line and end_line are required"

    try:
        start_line = int(start_line)
        end_line   = int(end_line)
    except (TypeError, ValueError):
        return False, "patch_file: start_line and end_line must be integers"

    abs_path = os.path.normpath(os.path.join(root, path))
    if not abs_path.startswith(os.path.normpath(root)):
        return False, "patch_file: path must be within project root"
    if not os.path.exists(abs_path):
        return False, f"patch_file: {path} not found"

    try:
        original_lines = open(abs_path, "r", encoding="utf-8").readlines()
        total = len(original_lines)

        if start_line < 1 or end_line > total or start_line > end_line:
            return False, (
                f"patch_file: line range {start_line}-{end_line} invalid "
                f"for file with {total} lines"
            )

        # Preserve trailing newline on replacement
        replacement = body + "\n" if body and not body.endswith("\n") else body
        new_lines = (
            original_lines[:start_line - 1] +
            [replacement] +
            original_lines[end_line:]
        )
        with open(abs_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)

        return True, (
            f"patched {path} lines {start_line}-{end_line} "
            f"({end_line - start_line + 1} lines replaced)"
        )
    except Exception as e:
        return False, f"patch_file error: {e}"


def _tool_write_file(attrs: dict, root: str) -> tuple[bool, str]:
    """Write complete file content."""
    import os
    path    = attrs.get("path", "")
    # Prefer tag body (_body) over content attribute
    # Also unescape literal \n in case agent used attribute form
    content = attrs.get("_body") or attrs.get("content", "")
    if content and "\\n" in content and "\n" not in content:
        content = content.replace("\\n", "\n").replace("\\t", "\t")
    from ai.worker import clean_code
    content = clean_code(content)

    if not path:
        return False, "write_file: path is required"

    abs_path = os.path.normpath(os.path.join(root, path))
    if not abs_path.startswith(os.path.normpath(root)):
        return False, "write_file: path must be within project root"

    try:
        from pathlib import Path as _Path
        _Path(abs_path).parent.mkdir(parents=True, exist_ok=True)
        _Path(abs_path).write_text(content, encoding="utf-8")
        return True, f"wrote {path} ({len(content)} chars)"
    except Exception as e:
        return False, f"write_file error: {e}"


def run_tool(name: str, attrs: dict, project_root: str, plugin_manager=None) -> tuple[bool, str]:
    """
    Execute a tool and return (success, output).
    Write tools return (True, "queued") without executing.
    """
    if plugin_manager:
        try:
            plugin_manager.emit(
                "tool_called",
                tool=name,
                args=attrs.copy()
            )
        except Exception:
            pass
    try:
        if name == "grep":
            return _tool_grep(attrs, project_root)
        elif name == "read_file":
            return _tool_read_file(attrs, project_root)
        elif name == "find_files":
            return _tool_find_files(attrs, project_root)
        elif name == "find_symbol":
            return _tool_find_symbol(attrs, project_root)
        elif name == "run_shell":
            return _tool_run_shell(attrs, project_root)
        elif name == "patch_file":
            if "start_line" not in attrs and "end_line" not in attrs:
                return False, (
                    "patch_file requires start_line and end_line attributes. "
                    "Use run_shell wc -l to get line count, read_file to see "
                    "line numbers, then patch_file with start_line and end_line."
                )
            return _tool_patch_file_by_line(attrs, project_root)
        elif name == "write_file":
            return _tool_write_file(attrs, project_root)
        elif name == "shell_write":
            return True, "queued"
        else:
            return False, f"Unknown tool: {name}"
        if plugin_manager:
            try:
                plugin_manager.emit(
                    "tool_result",
                    tool=name,
                    success=success,
                    result=(output[:2000] if isinstance(output, str) else str(output))
                )
            except Exception:
                pass
    
        return success, output
    except Exception as e:
        if plugin_manager:
            try:
                plugin_manager.emit(
                    "tool_result",
                    tool=name,
                    success=False,
                    result=str(e)
                )
            except Exception:
                pass
        return False, f"Tool error: {e}"


def is_write_tool(name: str) -> bool:
    return name in ("patch_file", "write_file", "shell_write")


def describe_tool_call(name: str, attrs: dict) -> str:
    """Human-readable description for the status panel."""
    if name == "grep":
        return f'grep "{attrs.get("pattern", "")}" {attrs.get("path", ".")}'
    elif name == "read_file":
        start = attrs.get("start", "")
        end   = attrs.get("end", "")
        lines = f" lines {start}-{end}" if start and end else ""
        return f'read {attrs.get("path", "")}{lines}'
    elif name == "find_files":
        return f'find {attrs.get("pattern", "*")} in {attrs.get("path", ".")}'
    elif name == "find_symbol":
        return f'find symbol "{attrs.get("name", "")}"'
    elif name == "run_shell":
        return attrs.get("command", "")[:80]
    elif name == "patch_file":
        return f'patch {attrs.get("path", "")}'
    elif name == "write_file":
        return f'write {attrs.get("path", "")}'
    elif name == "shell_write":
        return attrs.get("command", "")[:80]
    return name


# ── Read tool implementations ─────────────────────────────────────────────────

def _tool_grep(attrs: dict, root: str):
    """Run grep with the given attrs dict. Returns (success, output)."""
    import subprocess
    import os

    pattern = attrs.get("pattern", "")
    if not pattern:
        return False, "No pattern specified"
    flags = attrs.get("flags", "-rn")
    flag_list = flags.split()
    if "-E" not in flag_list:
        flag_list.append("-E")
    path = attrs.get("path", ".")
    full_path = os.path.join(root, path)
    try:
        # This supports extra args like --include/--exclude if needed in attrs
        cmd = ["grep"] + flag_list + [pattern, full_path]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.returncode == 0, result.stdout if result.stdout else result.stderr
    except Exception as e:
        return False, str(e)

def _tool_read_file(attrs: dict, root: str) -> tuple[bool, str]:
    path  = attrs.get("path", "")
    start = int(attrs.get("start", 1))
    end   = int(attrs.get("end", 0)) or None

    if not path:
        return False, "read_file: path is required"

    abs_path = os.path.normpath(os.path.join(root, path))
    if not abs_path.startswith(os.path.normpath(root)):
        return False, "read_file: path must be within project root"

    if not os.path.exists(abs_path):
        return False, f"read_file: {path} not found"

    try:
        with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        start = max(1, start)
        end   = min(len(lines), end or len(lines))

        # No hard cap — agent controls chunking via start/end
        # Soft cap at 300 lines to avoid flooding context
        if end - start > 300:
            end = start + 300

        selected = lines[start-1:end]
        numbered = "".join(f"{start+i:4d}  {l}" for i, l in enumerate(selected))
        return True, numbered
    except Exception as e:
        return False, f"read_file: {e}"


def _tool_find_files(attrs: dict, root: str) -> tuple[bool, str]:
    pattern = attrs.get("pattern", "*")
    path    = attrs.get("path", ".")

    abs_path = os.path.normpath(os.path.join(root, path))
    if not abs_path.startswith(os.path.normpath(root)):
        return False, "find_files: path must be within project root"

    skip = {".git", "__pycache__", "node_modules", ".venv", "venv",
            ".mypy_cache", "dist", "build"}

    matches = []
    for dirpath, dirnames, filenames in os.walk(abs_path):
        dirnames[:] = [d for d in dirnames if d not in skip]
        for fn in filenames:
            from fnmatch import fnmatch
            if fnmatch(fn, pattern):
                full = os.path.join(dirpath, fn)
                rel  = os.path.relpath(full, root)
                matches.append(rel)

    if not matches:
        return True, "(no files found)"
    if len(matches) > 100:
        matches = matches[:100]
        matches.append(f"... ({len(matches)} total, truncated)")
    return True, "\n".join(sorted(matches))


def _tool_find_symbol(attrs: dict, root: str) -> tuple[bool, str]:
    symbol = attrs.get("name", "")
    if not symbol:
        return False, "find_symbol: name is required"

    # Use grep as fallback since RepoMap may not be accessible here
    result = subprocess.run(
        ["grep", "-rn", "--include=*.py",
         f"def {symbol}\\|class {symbol}", root],
        capture_output=True,
        text=True,
        timeout=10,
    )
    output = result.stdout.strip()
    if not output:
        # Try broader search
        result2 = subprocess.run(
            ["grep", "-rn", symbol, root,
             "--include=*.py", "--exclude-dir=__pycache__",
             "--exclude-dir=.git"],
            capture_output=True, text=True, timeout=10,
        )
        output = result2.stdout.strip()

    if not output:
        return True, f"Symbol '{symbol}' not found"

    lines = output.splitlines()[:30]
    out   = "\n".join(lines)
    out   = out.replace(root + "/", "").replace(root + os.sep, "")
    return True, out


def _tool_run_shell(attrs: dict, root: str) -> tuple[bool, str]:
    command = attrs.get("command", "")
    if not command:
        return False, "run_shell: command is required"

    # Whitelist safe read-only commands
    safe_prefixes = [
        "git log", "git status", "git diff", "git show", "git branch",
        "wc ", "cat ", "head ", "tail ", "ls", "find ",
        "python3 -c", "python -c",
    ]
    if not any(command.strip().startswith(p) for p in safe_prefixes):
        return False, (
            f"run_shell: '{command}' not in safe read-only commands. "
            "Use patch_file for file changes."
        )

    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=root,
            capture_output=True,
            text=True,
            timeout=10,
        )
        output = (result.stdout + result.stderr).strip()
        return True, output[:3000] or "(no output)"
    except subprocess.TimeoutExpired:
        return False, "run_shell: timed out"


# ── XML tag parser ────────────────────────────────────────────────────────────

_RE_TOOL_CALL = re.compile(
    r'<tool_call\s+([^>]*?)(?:/>|>(.*?)</tool_call>)',
    re.DOTALL,
)
_RE_TOOL_CALL_SELF = re.compile(
    r'<tool_call\s([^>]*?)/>',
    re.DOTALL,
)

_RE_AGENT_DONE = re.compile(r'<agent_done\s*/>', re.IGNORECASE)


def parse_tool_calls(text: str) -> list[dict]:
    """
    Extract all tool_call tags from model output.
    Returns [{"name": ..., "attrs": {...}, "content": ...}, ...]
    """
    results = []
    for m in _RE_TOOL_CALL.finditer(text):
        attr_str = m.group(1)
        content  = (m.group(2) or "").strip()
        attrs    = _parse_attrs(attr_str)
        name     = attrs.pop("name", "")
        if not name:
            continue
        # Content inside tag overrides attribute with same name
        if content:
            if name == "grep":
                attrs.setdefault("pattern", content)
            elif name == "write_file":
                # Prefer tag body over content attribute
                attrs["_body"] = content
                if "content" not in attrs:
                    attrs["content"] = content
            elif name == "patch_file":
                # Tag body is the replacement content for the line range
                attrs["_body"] = content
        results.append({"name": name, "attrs": attrs})
    return results


def has_agent_done(text: str) -> bool:
    return bool(_RE_AGENT_DONE.search(text))


def strip_tool_calls(text: str) -> str:
    """Remove tool_call tags and agent_done from model output for display."""
    text = _RE_TOOL_CALL.sub("", text)
    text = _RE_AGENT_DONE.sub("", text)
    return text.strip()


def _parse_attrs(attr_str: str) -> dict:
    """Parse XML-style attribute string into dict."""
    attrs = {}
    for m in re.finditer(r'(\w+)=["\']([^"\']*)["\']', attr_str):
        attrs[m.group(1)] = m.group(2)
    return attrs