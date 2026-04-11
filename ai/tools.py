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
  <tool_call name="patch_file" path="..." old="..." new="...">Replace exact text in a file</tool_call>
  <tool_call name="write_file" path="..." content="...">Write entire file content</tool_call>
  <tool_call name="shell_write" command="...">Run a write shell command (sed -i, mv, etc)</tool_call>

Rules:
- Use read tools freely to investigate before proposing changes
- Emit ALL write tool calls at the end, after investigation is complete
- Never emit write tools mid-investigation
- After all tool calls, provide your final answer/explanation
- Use <agent_done/> when you have finished all tool calls and given your answer
"""


# ── Tool execution ────────────────────────────────────────────────────────────

def run_tool(name: str, attrs: dict, project_root: str) -> tuple[bool, str]:
    """
    Execute a tool and return (success, output).
    Write tools return (True, "queued") without executing.
    """
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
        elif name in ("patch_file", "write_file", "shell_write"):
            return True, "queued"
        else:
            return False, f"Unknown tool: {name}"
    except Exception as e:
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

def _tool_grep(attrs: dict, root: str) -> tuple[bool, str]:
    pattern = attrs.get("pattern", "")
    path    = attrs.get("path", ".")
    flags   = attrs.get("flags", "-rn")

    if not pattern:
        return False, "grep: pattern is required"

    # Safety: only allow relative paths
    abs_path = os.path.normpath(os.path.join(root, path))
    if not abs_path.startswith(os.path.normpath(root)):
        return False, "grep: path must be within project root"

    # Build safe args — no shell injection
    skip_dirs = ["__pycache__", ".git", "node_modules", ".venv", "venv"]
    exclude_args = []
    for d in skip_dirs:
        exclude_args += [f"--exclude-dir={d}"]

    args = ["grep"] + flags.split() + exclude_args + [pattern, abs_path]

    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=10,
            cwd=root,
        )
        output = result.stdout.strip()
        if not output:
            return True, "(no matches)"
        # Trim long output
        lines = output.splitlines()
        if len(lines) > 50:
            output = "\n".join(lines[:50]) + f"\n... ({len(lines)-50} more lines)"
        # Make paths relative
        output = output.replace(root + "/", "").replace(root + os.sep, "")
        return True, output
    except subprocess.TimeoutExpired:
        return False, "grep: timed out"
    except FileNotFoundError:
        return False, "grep: not available"


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

        # Cap at 200 lines per read
        if end - start > 200:
            end = start + 200

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
        "wc ", "cat ", "head ", "tail ", "ls ", "find ",
        "python3 -c", "python -c",
    ]
    if not any(command.strip().startswith(p) for p in safe_prefixes):
        return False, (
            f"run_shell: '{command}' not in safe read-only commands. "
            "Use shell_write for write operations."
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
            # Use content as the primary value for relevant attrs
            if name == "grep":
                attrs.setdefault("pattern", content)
            elif name in ("read_file", "find_files", "find_symbol",
                          "write_file", "patch_file"):
                if "content" not in attrs and name == "write_file":
                    attrs["content"] = content
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