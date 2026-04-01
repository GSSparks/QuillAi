"""
ai/lsp_client.py

JSON-RPC 2.0 client for python-lsp-server (pylsp).
Uses QProcess for non-blocking stdio on the Qt event loop — no extra threads.

Usage:
    client = LSPClient(project_root="/path/to/project")
    client.start()
    client.initialized.connect(lambda: print("LSP ready"))
    client.hover(file_uri, line, col, callback=lambda result: ...)
"""

import json
import re

from PyQt6.QtCore import QObject, QProcess, pyqtSignal


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def path_to_uri(path: str) -> str:
    """Convert an absolute filesystem path to a file:// URI."""
    import urllib.parse
    return "file://" + urllib.parse.quote(path, safe="/:")


def uri_to_path(uri: str) -> str:
    """Convert a file:// URI back to a filesystem path."""
    import urllib.parse
    return urllib.parse.unquote(uri.replace("file://", ""))


# ─────────────────────────────────────────────────────────────────────────────
# LSPClient
# ─────────────────────────────────────────────────────────────────────────────

class LSPClient(QObject):
    """
    Manages a pylsp subprocess and speaks JSON-RPC 2.0 over its stdio.

    Signals:
        initialized   — emitted once the server handshake is complete
        diagnostics   — emitted with (file_path, [diagnostic_dicts])
        error         — emitted with a human-readable error string
    """

    initialized  = pyqtSignal()
    diagnostics  = pyqtSignal(str, list)   # (file_path, diagnostics)
    error        = pyqtSignal(str)

    def __init__(self, project_root: str, parent=None):
        super().__init__(parent)
        self.project_root  = project_root
        self._process      = None
        self._next_id      = 1
        self._pending      = {}      # id → callback
        self._buffer       = b""    # raw bytes from stdout
        self._ready        = False
        self._open_files   = {}     # uri → version counter

    # ─────────────────────────────────────────────────────────────
    # Lifecycle
    # ─────────────────────────────────────────────────────────────

    def start(self):
        """Launch pylsp and perform the LSP initialize handshake."""
        self._process = QProcess(self)
        self._process.setProgram("pylsp")
        self._process.setArguments([])
        self._process.readyReadStandardOutput.connect(self._on_stdout)
        self._process.readyReadStandardError.connect(self._on_stderr)
        self._process.errorOccurred.connect(self._on_process_error)
        self._process.start()

        if not self._process.waitForStarted(3000):
            self.error.emit(
                "pylsp not found. Install it with: pip install python-lsp-server"
            )
            return

        self._send_request("initialize", {
            "processId":    None,
            "rootUri":      path_to_uri(self.project_root),
            "capabilities": {
                "textDocument": {
                    "hover":       {"contentFormat": ["plaintext", "markdown"]},
                    "definition":  {},
                    "publishDiagnostics": {},
                    "synchronization": {
                        "didOpen":   True,
                        "didChange": True,
                        "didClose":  True,
                    },
                }
            },
            "initializationOptions": {},
        }, callback=self._on_initialize_response)

    def stop(self):
        """Send shutdown/exit and kill the process."""
        if self._process and self._process.state() != QProcess.ProcessState.NotRunning:
            self._send_request("shutdown", {}, callback=lambda _: self._send_notify("exit", {}))
            self._process.waitForFinished(2000)
            self._process.kill()
        self._ready = False

    @property
    def is_ready(self) -> bool:
        return self._ready

    # ─────────────────────────────────────────────────────────────
    # Document sync  (call these from the editor)
    # ─────────────────────────────────────────────────────────────

    def open_file(self, file_path: str, text: str, language_id: str = "python"):
        """Notify LSP that a file has been opened."""
        if not self._ready:
            return
        uri = path_to_uri(file_path)
        self._open_files[uri] = 1
        self._send_notify("textDocument/didOpen", {
            "textDocument": {
                "uri":        uri,
                "languageId": language_id,
                "version":    1,
                "text":       text,
            }
        })

    def change_file(self, file_path: str, text: str):
        """Notify LSP of a full-text document change."""
        if not self._ready:
            return
        uri = path_to_uri(file_path)
        version = self._open_files.get(uri, 0) + 1
        self._open_files[uri] = version
        self._send_notify("textDocument/didChange", {
            "textDocument":   {"uri": uri, "version": version},
            "contentChanges": [{"text": text}],
        })

    def close_file(self, file_path: str):
        """Notify LSP that a file has been closed."""
        if not self._ready:
            return
        uri = path_to_uri(file_path)
        self._open_files.pop(uri, None)
        self._send_notify("textDocument/didClose", {
            "textDocument": {"uri": uri}
        })

    # ─────────────────────────────────────────────────────────────
    # LSP requests
    # ─────────────────────────────────────────────────────────────

    def hover(self, file_path: str, line: int, col: int, callback):
        """
        Request hover info (signature + docstring) at (line, col).
        callback(result_dict | None)
        LSP lines/cols are 0-indexed.
        """
        if not self._ready:
            callback(None)
            return
        self._send_request("textDocument/hover", {
            "textDocument": {"uri": path_to_uri(file_path)},
            "position":     {"line": line, "character": col},
        }, callback=callback)

    def definition(self, file_path: str, line: int, col: int, callback):
        """
        Request go-to-definition location(s) at (line, col).
        callback([{"uri": ..., "range": {...}}, ...] | None)
        """
        if not self._ready:
            callback(None)
            return
        self._send_request("textDocument/definition", {
            "textDocument": {"uri": path_to_uri(file_path)},
            "position":     {"line": line, "character": col},
        }, callback=callback)

    # ─────────────────────────────────────────────────────────────
    # Internal — JSON-RPC transport
    # ─────────────────────────────────────────────────────────────

    def _next_request_id(self) -> int:
        rid = self._next_id
        self._next_id += 1
        return rid

    def _send_request(self, method: str, params: dict, callback=None):
        rid = self._next_request_id()
        if callback:
            self._pending[rid] = callback
        self._write({
            "jsonrpc": "2.0",
            "id":      rid,
            "method":  method,
            "params":  params,
        })

    def _send_notify(self, method: str, params: dict):
        self._write({
            "jsonrpc": "2.0",
            "method":  method,
            "params":  params,
        })

    def _write(self, payload: dict):
        if not self._process:
            return
        body    = json.dumps(payload).encode("utf-8")
        header  = f"Content-Length: {len(body)}\r\n\r\n".encode("utf-8")
        self._process.write(header + body)

    # ─────────────────────────────────────────────────────────────
    # Internal — stdout parsing
    # ─────────────────────────────────────────────────────────────

    def _on_stdout(self):
        self._buffer += bytes(self._process.readAllStandardOutput())
        self._parse_messages()

    def _parse_messages(self):
        """
        Parse as many complete LSP messages as possible from the buffer.
        LSP framing: "Content-Length: N\\r\\n\\r\\n" + N bytes of JSON.
        """
        while True:
            # Look for the header/body separator
            sep = self._buffer.find(b"\r\n\r\n")
            if sep == -1:
                break

            header = self._buffer[:sep].decode("utf-8", errors="replace")
            match  = re.search(r"Content-Length:\s*(\d+)", header)
            if not match:
                self._buffer = self._buffer[sep + 4:]
                continue

            length     = int(match.group(1))
            body_start = sep + 4

            if len(self._buffer) < body_start + length:
                break   # wait for more data

            body          = self._buffer[body_start: body_start + length]
            self._buffer  = self._buffer[body_start + length:]

            try:
                msg = json.loads(body.decode("utf-8"))
            except json.JSONDecodeError:
                continue

            self._dispatch(msg)

    def _dispatch(self, msg: dict):
        """Route an incoming JSON-RPC message to the right handler."""

        # Response to one of our requests
        if "id" in msg:
            rid      = msg["id"]
            callback = self._pending.pop(rid, None)
            if callback:
                callback(msg.get("result"))
            return

        # Server-initiated notification
        method = msg.get("method", "")

        if method == "textDocument/publishDiagnostics":
            params    = msg.get("params", {})
            uri       = params.get("uri", "")
            file_path = uri_to_path(uri)
            self.diagnostics.emit(file_path, params.get("diagnostics", []))

        # Could handle window/showMessage, window/logMessage etc. here later

    # ─────────────────────────────────────────────────────────────
    # Internal — process events
    # ─────────────────────────────────────────────────────────────

    def _on_initialize_response(self, result):
        """Complete the handshake after initialize response."""
        self._send_notify("initialized", {})
        self._ready = True
        self.initialized.emit()

    def _on_stderr(self):
        data = bytes(self._process.readAllStandardError()).decode("utf-8", errors="replace")
        if data.strip():
            print(f"[pylsp stderr] {data.strip()}")

    def _on_process_error(self, error):
        messages = {
            QProcess.ProcessError.FailedToStart: (
                "pylsp failed to start. Install with: pip install python-lsp-server"
            ),
            QProcess.ProcessError.Crashed: "pylsp crashed.",
        }
        self.error.emit(messages.get(error, f"pylsp process error: {error}"))
        self._ready = False