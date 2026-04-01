"""
ai/lsp_context.py

Formats LSP hover results and diagnostics into context strings
for injection into ContextEngine.build().

Usage:
    provider = LSPContextProvider(lsp_client)
    provider.fetch(file_path, line, col, callback=lambda ctx: ...)
    # ctx is a dict: {"hover": str, "diagnostics": str}
    # Pass to ContextEngine.build(lsp_context=ctx)
"""

from PyQt6.QtCore import QObject


class LSPContextProvider(QObject):
    """
    Wraps LSPClient and provides context-ready strings for the prompt.
    Both hover and diagnostics are fetched concurrently; the callback
    fires once both have returned (or timed out gracefully).
    """

    def __init__(self, lsp_client, parent=None):
        super().__init__(parent)
        self.client = lsp_client

        # Most recent diagnostics per file, updated by LSP push notifications
        self._diagnostics: dict[str, list] = {}
        self.client.diagnostics.connect(self._on_diagnostics)

    # ─────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────

    def fetch(self, file_path: str, line: int, col: int, callback):
        """
        Async fetch of hover + diagnostics for (file_path, line, col).
        callback receives a dict: {"hover": str, "diagnostics": str}
        Both fields may be empty strings if LSP returns nothing.
        line/col are 0-indexed (LSP convention).
        """
        result = {"hover": "", "diagnostics": ""}
        pending = [1]   # simple counter: 1 request outstanding (hover)

        def maybe_done():
            if pending[0] == 0:
                callback(result)

        def on_hover(hover_result):
            result["hover"] = self._format_hover(hover_result)
            pending[0] -= 1
            maybe_done()

        # Diagnostics are push-based (server sends them automatically on change)
        # so we read from cache rather than making a separate request
        result["diagnostics"] = self._format_diagnostics(
            file_path, line, self._diagnostics.get(file_path, [])
        )

        self.client.hover(file_path, line, col, callback=on_hover)

    def get_diagnostics_context(self, file_path: str) -> str:
        """
        Return a formatted string of all current diagnostics for a file.
        Useful for injecting the full diagnostic list regardless of cursor pos.
        """
        return self._format_diagnostics(
            file_path, line=None,
            diags=self._diagnostics.get(file_path, [])
        )

    def has_errors(self, file_path: str) -> bool:
        """True if the file currently has any LSP error-severity diagnostics."""
        return any(
            d.get("severity", 4) == 1
            for d in self._diagnostics.get(file_path, [])
        )

    # ─────────────────────────────────────────────────────────────
    # Formatting
    # ─────────────────────────────────────────────────────────────

    def _format_hover(self, result) -> str:
        """
        Extract a clean text string from a hover result.
        pylsp returns {"contents": {"kind": "markdown", "value": "..."}}
        or {"contents": "plain string"} depending on the symbol.
        """
        if not result:
            return ""

        contents = result.get("contents", "")

        if isinstance(contents, dict):
            text = contents.get("value", "")
        elif isinstance(contents, list):
            # MarkedString[] — take the first non-empty entry
            text = next(
                (c.get("value", c) if isinstance(c, dict) else c
                 for c in contents if c),
                ""
            )
        else:
            text = str(contents)

        text = text.strip()
        if not text:
            return ""

        return f"[LSP Hover]\n{text}"

    def _format_diagnostics(self, file_path: str, line, diags: list) -> str:
        """
        Format diagnostics into a compact context string.
        If line is provided, errors near the cursor are listed first.
        Severity: 1=Error, 2=Warning, 3=Information, 4=Hint
        """
        if not diags:
            return ""

        severity_label = {1: "ERROR", 2: "WARN", 3: "INFO", 4: "HINT"}

        # Sort: errors first, then by proximity to cursor line
        def sort_key(d):
            sev      = d.get("severity", 4)
            diag_line = d.get("range", {}).get("start", {}).get("line", 0)
            distance = abs(diag_line - line) if line is not None else 0
            return (sev, distance)

        sorted_diags = sorted(diags, key=sort_key)[:10]  # cap at 10

        lines = []
        for d in sorted_diags:
            sev      = severity_label.get(d.get("severity", 4), "HINT")
            diag_line = d.get("range", {}).get("start", {}).get("line", 0) + 1  # 1-indexed
            msg      = d.get("message", "").replace("\n", " ")
            source   = d.get("source", "")
            src_str  = f" [{source}]" if source else ""
            lines.append(f"  {sev} line {diag_line}{src_str}: {msg}")

        return f"[LSP Diagnostics]\n" + "\n".join(lines)

    # ─────────────────────────────────────────────────────────────
    # Diagnostics cache  (updated by LSP push)
    # ─────────────────────────────────────────────────────────────

    def _on_diagnostics(self, file_path: str, diags: list):
        self._diagnostics[file_path] = diags