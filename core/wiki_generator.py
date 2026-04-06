"""
wiki_generator.py — LLM-backed Markdown wiki page generator for QuillAI.

Generates structured .md documentation for a single Python source file
using the project's API-backed model. Designed to be called by WikiManager.
"""

import ast
import json
import os
import re
import requests
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

_MODULE_PROMPT = """\
You are a technical documentation assistant. Analyze the following {language} source \
file and produce a structured Markdown wiki page for it.

The wiki page MUST follow this exact format (do not add extra sections):

# {module_path}

## Summary
One or two sentences describing what this file does and its role in the application.

## Key Symbols
A table with columns: | Symbol | Kind | Description |
List every public class, function, variable, rule, key, or other important definition. Keep descriptions to one line.

## Dependencies
List only intra-project imports or includes (same repo). Format as a bullet list of relative paths, e.g. `core/lsp_manager.py`.
If the file type does not have imports (e.g. JSON, YAML, plain text), write `_N/A._`

## Dependents
Leave this section as the exact placeholder text: `<!-- dependents: auto-filled by WikiManager -->`

## Notes
Any notable patterns, non-obvious design decisions, or warnings. \
If there is nothing noteworthy, write `_None._`

---
SOURCE FILE: {module_path} ({language})
```
{source}
```
"""

_INDEX_PROMPT = """\
You are a technical documentation assistant. Given the following list of wiki \
pages (module paths and their one-line summaries), produce a repo-level \
`index.md` file.

The index MUST follow this exact format:

# {project_name} — Codebase Wiki

## Overview
Two or three sentences describing the overall project architecture.

## Module Index
A table with columns: | Module | Summary |
One row per module from the list below.

## Architecture Notes
Key cross-cutting patterns worth knowing (theme system, LSP routing, etc). \
Keep it to bullet points, maximum 8.

---
MODULES:
{module_list}
"""


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------

def _extract_imports(source: str, repo_root: Path, file_path: Path) -> list[str]:
    """Return intra-project import paths found in *source*."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    results: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            # Relative import: resolve against file location
            if node.level and node.level > 0:
                base = file_path.parent
                for _ in range(node.level - 1):
                    base = base.parent
                parts = node.module.split(".")
                candidate = base.joinpath(*parts).with_suffix(".py")
                try:
                    rel = candidate.relative_to(repo_root)
                    if rel.exists() or (repo_root / rel).exists():
                        results.append(str(rel))
                except ValueError:
                    pass
            else:
                # Absolute import — check if it resolves inside repo
                parts = node.module.split(".")
                candidate = repo_root.joinpath(*parts).with_suffix(".py")
                if candidate.exists():
                    try:
                        results.append(str(candidate.relative_to(repo_root)))
                    except ValueError:
                        pass
                # Also try as package __init__
                pkg = repo_root.joinpath(*parts, "__init__.py")
                if pkg.exists():
                    try:
                        results.append(str(pkg.relative_to(repo_root)))
                    except ValueError:
                        pass
    return sorted(set(results))


def _extract_summary(wiki_text: str) -> str:
    """Pull the Summary section text out of a generated wiki page."""
    m = re.search(r"## Summary\n+(.*?)(?=\n##|\Z)", wiki_text, re.DOTALL)
    if m:
        return m.group(1).strip().split("\n")[0]
    return ""


# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------

_EXT_TO_LANGUAGE = {
    ".py": "Python", ".js": "JavaScript", ".jsx": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript",
    ".html": "HTML", ".htm": "HTML", ".css": "CSS",
    ".scss": "SCSS", ".sass": "Sass", ".less": "Less",
    ".json": "JSON", ".toml": "TOML", ".xml": "XML",
    ".yml": "YAML", ".yaml": "YAML",
    ".tf": "Terraform", ".tfvars": "Terraform", ".hcl": "HCL", ".nix": "Nix",
    ".sh": "Bash", ".bash": "Bash", ".zsh": "Zsh", ".fish": "Fish",
    ".pl": "Perl", ".pm": "Perl", ".lua": "Lua", ".rb": "Ruby", ".php": "PHP",
    ".rs": "Rust", ".go": "Go", ".c": "C", ".h": "C",
    ".cpp": "C++", ".hpp": "C++", ".java": "Java",
    ".kt": "Kotlin", ".swift": "Swift",
    ".md": "Markdown", ".rst": "reStructuredText",
    ".txt": "Text", ".tex": "LaTeX", ".sql": "SQL",
}

def _language_for(path: Path) -> str:
    """Return a human-readable language name for a source file."""
    return _EXT_TO_LANGUAGE.get(path.suffix.lower(), path.suffix.lstrip(".").upper() or "text")



# ---------------------------------------------------------------------------
# WikiGenerator
# ---------------------------------------------------------------------------

class WikiGenerator:
    """
    Generates and updates Markdown wiki pages for individual Python modules
    and the repo-level index using the configured API endpoint.

    Parameters
    ----------
    repo_root : Path
        Absolute path to the root of the repository being documented.
    model : str
        Model identifier (e.g. gpt-4o, claude-sonnet-4-20250514).
    max_tokens : int
        Maximum tokens for a single generation call.
    """

    def __init__(
        self,
        repo_root: Path,
        model: str = "",
        max_tokens: int = 2048,
        api_url: str = "",
        api_key: str = "",
        backend: str = "openai",
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.model = model
        self.max_tokens = max_tokens
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.backend = backend.lower()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_page(self, source_path: Path) -> str:
        """
        Generate a wiki Markdown page for *source_path*.

        Returns the full Markdown string. Does NOT write to disk —
        that is WikiManager's responsibility.

        Parameters
        ----------
        source_path : Path
            Absolute or repo-relative path to the .py source file.
        """
        source_path = self._resolve(source_path)
        rel = source_path.relative_to(self.repo_root)
        source = source_path.read_text(encoding="utf-8", errors="replace")

        # Trim large files — local models need smaller context to stay fast.
        # Keep first 300 lines or 8000 chars, whichever is smaller.
        lines = source.splitlines()
        if len(lines) > 300:
            source = "\n".join(lines[:300]) + "\n# ... (truncated)"
        if len(source) > 8000:
            source = source[:8000] + "\n# ... (truncated)"

        language = _language_for(source_path)
        prompt = _MODULE_PROMPT.format(
            module_path=str(rel),
            language=language,
            source=source,
        )
        markdown = self._call_api(prompt)
        markdown = self._inject_dependencies(markdown, source, source_path)
        return markdown

    def generate_index(self, page_summaries: dict[str, str]) -> str:
        """
        Generate the repo-level index.md from a dict of
        {relative_module_path: one_line_summary}.

        Returns the full Markdown string.
        """
        module_list = "\n".join(
            f"- {path}: {summary}" for path, summary in sorted(page_summaries.items())
        )
        project_name = self.repo_root.name
        prompt = _INDEX_PROMPT.format(module_list=module_list, project_name=project_name)
        return self._call_api(prompt)

    def extract_summary(self, wiki_text: str) -> str:
        """Return the one-line summary from an already-generated wiki page."""
        return _extract_summary(wiki_text)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _call_api(self, prompt: str) -> str:
        """Send *prompt* via the configured API endpoint and return the text response."""
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "QuillAI-IDE/1.0",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key.strip()}"

        payload = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
        }

        # Local models are slower per token — give them more time
        timeout = 300 if self.backend == "llama" else 120
        response = requests.post(
            self.api_url,
            json=payload,
            headers=headers,
            timeout=timeout,
        )
        response.raise_for_status()
        data = response.json()

        # OpenAI-compatible response shape
        choices = data.get("choices", [])
        if choices:
            return choices[0].get("message", {}).get("content", "")

        # Anthropic native shape (content array)
        content = data.get("content", [])
        if content:
            return content[0].get("text", "")

        return ""

    def _inject_dependencies(
        self, markdown: str, source: str, source_path: Path
    ) -> str:
        """
        For Python files: replace Dependencies section with AST-derived imports.
        For all other file types: leave the LLM-generated section as-is.
        """
        if source_path.suffix.lower() != ".py":
            return markdown

        deps = _extract_imports(source, self.repo_root, source_path)
        if deps:
            dep_block = "\n".join(f"- `{d}`" for d in deps)
        else:
            dep_block = "_None._"

        new_section = f"## Dependencies\n{dep_block}"
        markdown = re.sub(
            r"## Dependencies\n.*?(?=\n##|\Z)",
            new_section + "\n",
            markdown,
            flags=re.DOTALL,
        )
        return markdown

    def _resolve(self, path: Path) -> Path:
        path = Path(path)
        if not path.is_absolute():
            path = self.repo_root / path
        return path.resolve()