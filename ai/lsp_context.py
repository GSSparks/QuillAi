"""
ai/lsp_context.py

Formats LSP hover results and diagnostics into context strings
for injection into ContextEngine.build().

Accepts an LSPManager so it works across all language servers.
"""

from PyQt6.QtCore import QObject


class LSPContextProvider(QObject):
    def __init__(self, lsp_manager, parent=None):
        super().__init__(parent)
        self.manager = lsp_manager
        self._diagnostics: dict[str, list] = {}

        # Subscribe to diagnostics from every server via the manager's clients
        # We connect after servers start — manager emits server_ready when ready
        self.manager.server_ready.connect(self._on_server_ready)

    def _on_server_ready(self, name: str):
        """Wire diagnostics signal from newly ready server."""
        for client in set(self.manager._ext_map.values()):
            try:
                client.diagnostics.disconnect(self._on_diagnostics)
            except (RuntimeError, TypeError):
                pass
            client.diagnostics.connect(self._on_diagnostics)

    def fetch(self, file_path: str, line: int, col: int, callback):
        """
        Async fetch of hover + diagnostics for (file_path, line, col).
        callback receives {"hover": str, "diagnostics": str}.
        """
        result  = {"hover": "", "diagnostics": ""}
        pending = [1]

        def maybe_done():
            if pending[0] == 0:
                callback(result)

        def on_hover(hover_result):
            result["hover"] = self._format_hover(hover_result)
            pending[0] -= 1
            maybe_done()

        result["diagnostics"] = self._format_diagnostics(
            file_path, line, self._diagnostics.get(file_path, [])
        )

        self.manager.hover(file_path, line, col, callback=on_hover)

    def get_diagnostics_context(self, file_path: str) -> str:
        return self._format_diagnostics(
            file_path, None, self._diagnostics.get(file_path, [])
        )

    def has_errors(self, file_path: str) -> bool:
        return any(
            d.get("severity", 4) == 1
            for d in self._diagnostics.get(file_path, [])
        )

    # ─────────────────────────────────────────────────────────────
    # Formatting
    # ─────────────────────────────────────────────────────────────

    def _format_hover(self, result) -> str:
        if not result:
            return ""
        contents = result.get("contents", "")
        if isinstance(contents, dict):
            text = contents.get("value", "")
        elif isinstance(contents, list):
            text = next(
                (c.get("value", c) if isinstance(c, dict) else c
                 for c in contents if c), ""
            )
        else:
            text = str(contents)
        text = text.strip()
        return f"[LSP Hover]\n{text}" if text else ""

    def _format_diagnostics(self, file_path: str, line, diags: list) -> str:
        if not diags:
            return ""
        severity_label = {1: "ERROR", 2: "WARN", 3: "INFO", 4: "HINT"}

        def sort_key(d):
            sev      = d.get("severity", 4)
            diag_line = d.get("range", {}).get("start", {}).get("line", 0)
            distance = abs(diag_line - line) if line is not None else 0
            return (sev, distance)

        sorted_diags = sorted(diags, key=sort_key)[:10]
        lines = []
        for d in sorted_diags:
            sev       = severity_label.get(d.get("severity", 4), "HINT")
            diag_line = d.get("range", {}).get("start", {}).get("line", 0) + 1
            msg       = d.get("message", "").replace("\n", " ")
            source    = d.get("source", "")
            src_str   = f" [{source}]" if source else ""
            lines.append(f"  {sev} line {diag_line}{src_str}: {msg}")

        return "[LSP Diagnostics]\n" + "\n".join(lines)

    def _on_diagnostics(self, file_path: str, diags: list):
        self._diagnostics[file_path] = diags