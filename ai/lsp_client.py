"""
ai/lsp_client.py

Generic JSON-RPC 2.0 LSP client.
Language-server-specific config lives in lsp_manager.py — this class
knows nothing about which server it's talking to.

Usage:
    client = LSPClient(
        project_root = "/path/to/project",
        cmd          = "pylsp",
        args         = [],
        lang_id      = "python",
    )
    client.start()
    client.initialized.connect(lambda: ...)
    client.hover(file_path, line, col, callback=lambda r: ...)
"""

import json
import os
import re

from PyQt6.QtCore import QObject, QProcess, pyqtSignal


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def path_to_uri(path: str) -> str:
    import urllib.parse
    return "file://" + urllib.parse.quote(path, safe="/:")


def uri_to_path(uri: str) -> str:
    import urllib.parse
    return urllib.parse.unquote(uri.replace("file://", ""))


# ─────────────────────────────────────────────────────────────────────────────
# LSPClient
# ─────────────────────────────────────────────────────────────────────────────

class LSPClient(QObject):
    """
    Generic LSP client. One instance per language server process.
    All language-specific configuration is passed in at construction time.

    Signals:
        initialized  — handshake complete, safe to open files
        diagnostics  — (file_path, [diagnostic_dicts])
        error        — human-readable error string
        stopped      — process has exited (cleanly or otherwise)
    """

    initialized = pyqtSignal()
    diagnostics = pyqtSignal(str, list)
    error       = pyqtSignal(str)
    stopped     = pyqtSignal()

    def __init__(self, project_root: str, cmd: str, args: list,
                 lang_id: str, init_options: dict = None, parent=None):
        """
        project_root  — workspace root passed to LSP initialize
        cmd           — server binary name (must be on PATH)
        args          — command line arguments for the server
        lang_id       — LSP languageId string (e.g. "python", "yaml")
        init_options  — optional initializationOptions dict for the server
        """
        super().__init__(parent)
        self.project_root  = project_root
        self.cmd           = cmd
        self.args          = args
        self.lang_id       = lang_id
        self.init_options  = init_options or {}

        self._process    = None
        self._next_id    = 1
        self._pending    = {}     # id → callback
        self._buffer     = b""
        self._ready      = False
        self._open_files = {}    # uri → version

    # ─────────────────────────────────────────────────────────────
    # Lifecycle
    # ─────────────────────────────────────────────────────────────

    def start(self):
        """Launch the server process and perform the LSP handshake."""
        self._process = QProcess(self)
        self._process.setProgram(self.cmd)
        self._process.setArguments(self.args)
        self._process.readyReadStandardOutput.connect(self._on_stdout)
        self._process.readyReadStandardError.connect(self._on_stderr)
        self._process.errorOccurred.connect(self._on_process_error)
        self._process.finished.connect(self._on_process_finished)
        self._process.start()

        if not self._process.waitForStarted(3000):
            self.error.emit(
                f"{self.cmd!r} failed to start. "
                f"Make sure it is installed and on PATH."
            )
            return

        self._send_request("initialize", {
            "processId":    None,
            "rootUri":      path_to_uri(self.project_root),
            "capabilities": {
                "textDocument": {
                    "hover": {
                        "contentFormat":      ["markdown", "plaintext"],
                        "dynamicRegistration": False,
                    },
                    "definition": {
                        "dynamicRegistration": False,
                    },
                    "completion": {
                        "completionItem": {
                            "snippetSupport":        False,
                            "documentationFormat":   ["markdown", "plaintext"],
                        },
                        "dynamicRegistration": False,
                    },
                    "documentSymbol": {
                        "hierarchicalDocumentSymbolSupport": True,
                        "dynamicRegistration": False,
                    },
                    "publishDiagnostics": {
                        "relatedInformation": True,
                    },
                    "synchronization": {
                        "didOpen":             True,
                        "didChange":           True,
                        "didClose":            True,
                        "dynamicRegistration": False,
                    },
                },
                "workspace": {
                    "didChangeConfiguration": {},
                    "configuration":          True,
                },
            },
            "initializationOptions": self.init_options,
        }, callback=self._on_initialize_response)

    def stop(self):
        """Graceful shutdown — sends LSP shutdown/exit then kills."""
        if not self._process:
            return
        if self._process.state() == QProcess.ProcessState.NotRunning:
            return
        self._send_request(
            "shutdown", {},
            callback=lambda _: self._send_notify("exit", {})
        )
        self._process.waitForFinished(2000)
        self._process.kill()
        self._ready = False

    @property
    def is_ready(self) -> bool:
        return self._ready

    # ─────────────────────────────────────────────────────────────
    # Document sync
    # ─────────────────────────────────────────────────────────────

    def open_file(self, file_path: str, text: str):
        if not self._ready:
            return
        uri = path_to_uri(file_path)
        self._open_files[uri] = 1
        self._send_notify("textDocument/didOpen", {
            "textDocument": {
                "uri":        uri,
                "languageId": self.lang_id,
                "version":    1,
                "text":       text,
            }
        })

    def change_file(self, file_path: str, text: str):
        if not self._ready:
            return
        uri     = path_to_uri(file_path)
        version = self._open_files.get(uri, 0) + 1
        self._open_files[uri] = version
        self._send_notify("textDocument/didChange", {
            "textDocument":   {"uri": uri, "version": version},
            "contentChanges": [{"text": text}],
        })

    def close_file(self, file_path: str):
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
        if not self._ready:
            callback(None)
            return
        self._send_request("textDocument/hover", {
            "textDocument": {"uri": path_to_uri(file_path)},
            "position":     {"line": line, "character": col},
        }, callback=callback)

    def definition(self, file_path: str, line: int, col: int, callback):
        if not self._ready:
            callback(None)
            return
        self._send_request("textDocument/definition", {
            "textDocument": {"uri": path_to_uri(file_path)},
            "position":     {"line": line, "character": col},
        }, callback=callback)

    def document_symbols(self, file_path: str, callback):
        if not self._ready:
            callback([])
            return
        self._send_request("textDocument/documentSymbol", {
            "textDocument": {"uri": path_to_uri(file_path)},
        }, callback=lambda result: callback(
            result if isinstance(result, list) else []
        ))

    # ─────────────────────────────────────────────────────────────
    # JSON-RPC transport
    # ─────────────────────────────────────────────────────────────

    def _next_request_id(self) -> int:
        rid = self._next_id
        self._next_id += 1
        return rid

    def _send_request(self, method: str, params: dict, callback=None):
        rid = self._next_request_id()
        if callback:
            self._pending[rid] = callback
        self._write({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})

    def _send_notify(self, method: str, params: dict):
        self._write({"jsonrpc": "2.0", "method": method, "params": params})

    def _write(self, payload: dict):
        if not self._process:
            return
        body   = json.dumps(payload).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("utf-8")
        self._process.write(header + body)

    def _on_stdout(self):
        self._buffer += bytes(self._process.readAllStandardOutput())
        self._parse_messages()

    def _parse_messages(self):
        while True:
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
                break
            body         = self._buffer[body_start: body_start + length]
            self._buffer = self._buffer[body_start + length:]
            try:
                msg = json.loads(body.decode("utf-8"))
            except json.JSONDecodeError:
                continue
            self._dispatch(msg)

    def _dispatch(self, msg: dict):
        # ── Responses to our requests ─────────────────────────────────────
        if "id" in msg and "method" not in msg:
            callback = self._pending.pop(msg["id"], None)
            if callback:
                callback(msg.get("result"))
            return

        method = msg.get("method", "")

        # ── workspace/configuration — servers request their own settings ──
        # Must respond or servers like perlnavigator stall indefinitely.
        if method == "workspace/configuration":
            req_id = msg.get("id")
            items  = msg.get("params", {}).get("items", [])
            # Return empty config object for each requested section
            self._write({
                "jsonrpc": "2.0",
                "id":      req_id,
                "result":  [{}] * len(items),
            })
            return

        # ── workspace/applyEdit — acknowledge silently ────────────────────
        if method == "workspace/applyEdit":
            req_id = msg.get("id")
            if req_id is not None:
                self._write({
                    "jsonrpc": "2.0",
                    "id":      req_id,
                    "result":  {"applied": False},
                })
            return

        # ── window/showMessageRequest — dismiss silently ──────────────────
        if method == "window/showMessageRequest":
            req_id = msg.get("id")
            if req_id is not None:
                self._write({
                    "jsonrpc": "2.0",
                    "id":      req_id,
                    "result":  None,
                })
            return

        # ── Informational notifications ───────────────────────────────────
        if method == "window/logMessage":
            params = msg.get("params", {})
            return

        if method == "window/showMessage":
            params = msg.get("params", {})
            return

        if method == "$/progress":
            return   # ignore progress notifications

        if method == "telemetry/event":
            return   # ignore telemetry

        # ── Diagnostics ───────────────────────────────────────────────────
        if method == "textDocument/publishDiagnostics":
            params    = msg.get("params", {})
            file_path = uri_to_path(params.get("uri", ""))
            diags     = params.get("diagnostics", [])
            self.diagnostics.emit(file_path, diags)
            return

        # ── Catch-all for unhandled server→client requests ────────────────
        if "id" in msg:
            # Server sent a request we don't handle — send error response
            self._write({
                "jsonrpc": "2.0",
                "id":      msg["id"],
                "error": {
                    "code":    -32601,
                    "message": f"Method not supported: {method}",
                },
            })

    def _on_initialize_response(self, result):
        self._send_notify("initialized", {})
        self._ready = True
        self.initialized.emit()

    def _on_stderr(self):
        data = bytes(self._process.readAllStandardError()).decode(
            "utf-8", errors="replace"
        )

    def _on_process_error(self, error):
        labels = {
            QProcess.ProcessError.FailedToStart: (
                f"{self.cmd!r} failed to start — is it installed?"
            ),
            QProcess.ProcessError.Crashed: f"{self.cmd!r} crashed.",
        }
        self.error.emit(labels.get(error, f"{self.cmd!r} process error: {error}"))
        self._ready = False

    def _on_process_finished(self):
        self._ready = False
        self.stopped.emit()