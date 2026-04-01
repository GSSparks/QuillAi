"""
ai/lsp_manager.py

Owns the language server registry and manages one LSPClient per server.
One server may handle multiple file extensions (e.g. yaml/yml both go
to ansible-language-server).

Adding a new language server:
    Add one entry to LSP_REGISTRY. That's it.

Usage:
    manager = LSPManager(project_root)
    manager.start()                              # starts available servers
    manager.client_for(file_path)               # → LSPClient | None
    manager.open_file(file_path, text)           # route to right client
    manager.change_file(file_path, text)
    manager.close_file(file_path)
    manager.hover(file_path, line, col, cb)
    manager.definition(file_path, line, col, cb)
    manager.stop()
"""

import os
import shutil

from PyQt6.QtCore import QObject, pyqtSignal

from ai.lsp_client import LSPClient


# ─────────────────────────────────────────────────────────────────────────────
# Registry
# To add a new language server: add an entry here. Nothing else to change.
# ─────────────────────────────────────────────────────────────────────────────

LSP_REGISTRY = [
    {
        "name":       "pylsp",
        "cmd":        "pylsp",
        "args":       [],
        "extensions": {".py"},
        "lang_id":    "python",
        "init_options": {},
    },
    {
        "name":       "yaml-language-server",
        "cmd":        "yaml-language-server",
        "args":       ["--stdio"],
        "extensions": {".yml", ".yaml"},
        "lang_id":    "yaml",
        "init_options": {
            "yaml": {
                "validate": True,
                "hover":    True,
                "completion": True,
                "schemas": {
                    # Ansible schemas from SchemaStore
                    "https://raw.githubusercontent.com/ansible/schemas/main/f/ansible-playbook.json": [
                        "**/playbooks/*.yml",
                        "**/playbooks/*.yaml",
                        "site.yml",
                        "site.yaml",
                    ],
                    "https://raw.githubusercontent.com/ansible/schemas/main/f/ansible-tasks.json": [
                        "**/tasks/*.yml",
                        "**/tasks/*.yaml",
                        "**/handlers/*.yml",
                        "**/handlers/*.yaml",
                    ],
                },
            }
        },
    },
    {
        "name":       "typescript-language-server",
        "cmd":        "typescript-language-server",
        "args":       ["--stdio"],
        "extensions": {".js", ".jsx", ".ts", ".tsx"},
        "lang_id":    "typescript",
        "init_options": {},
    },
    {
        "name":       "bash-language-server",
        "cmd":        "bash-language-server",
        "args":       ["start"],
        "extensions": {".sh", ".bash"},
        "lang_id":    "shellscript",
        "init_options": {},
    },
    {
        "name":       "nil (Nix)",
        "cmd":        "nil",
        "args":       [],
        "extensions": {".nix"},
        "lang_id":    "nix",
        "init_options": {},
    },
    {
        "name":       "lua-language-server",
        "cmd":        "lua-language-server",
        "args":       [],
        "extensions": {".lua"},
        "lang_id":    "lua",
        "init_options": {},
    },
    {
        "name":       "vscode-html-language-server",
        "cmd":        "vscode-html-language-server",
        "args":       ["--stdio"],
        "extensions": {".html", ".htm"},
        "lang_id":    "html",
        "init_options": {},
    },
    {
        "name":       "vscode-css-language-server",
        "cmd":        "vscode-css-language-server",
        "args":       ["--stdio"],
        "extensions": {".css", ".scss", ".less"},
        "lang_id":    "css",
        "init_options": {},
    },
    {
        "name":       "vscode-json-language-server",
        "cmd":        "vscode-json-language-server",
        "args":       ["--stdio"],
        "extensions": {".json", ".jsonc"},
        "lang_id":    "json",
        "init_options": {
            "provideFormatter": True,
            # SchemaStore catalogue — gives the JSON server schema awareness
            # for common files like package.json, tsconfig.json, etc.
            "schemas": [
                {
                    "uri":       "https://json.schemastore.org/package.json",
                    "fileMatch": ["package.json"],
                },
                {
                    "uri":       "https://json.schemastore.org/tsconfig.json",
                    "fileMatch": ["tsconfig.json", "tsconfig.*.json"],
                },
                {
                    "uri":       "https://json.schemastore.org/eslintrc.json",
                    "fileMatch": [".eslintrc", ".eslintrc.json"],
                },
                {
                    "uri":       "https://json.schemastore.org/prettierrc.json",
                    "fileMatch": [".prettierrc", ".prettierrc.json"],
                },
            ],
        },
    },
    {
        "name":       "vscode-markdown-language-server",
        "cmd":        "vscode-markdown-language-server",
        "args":       ["--stdio"],
        "extensions": {".md", ".markdown"},
        "lang_id":    "markdown",
        "init_options": {},
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# LSPManager
# ─────────────────────────────────────────────────────────────────────────────

class LSPManager(QObject):
    """
    Manages one LSPClient per language server.
    Routes all LSP calls to the correct client based on file extension.

    Signals:
        server_ready(name)   — a server finished its handshake
        server_error(name, msg) — a server reported an error
    """

    server_ready = pyqtSignal(str)          # server name
    server_error = pyqtSignal(str, str)     # server name, message

    def __init__(self, project_root: str, parent=None):
        super().__init__(parent)
        self.project_root = project_root

        # ext → LSPClient (built in start())
        self._ext_map: dict[str, LSPClient] = {}

        # name → LSPClient (for lifecycle management)
        self._clients: dict[str, LSPClient] = {}

    # ─────────────────────────────────────────────────────────────
    # Lifecycle
    # ─────────────────────────────────────────────────────────────

    def start(self):
        """
        Start every server whose binary is available on PATH.
        Servers not installed are silently skipped.
        """
        available = self._available_servers()
        if not available:
            return

        for cfg in available:
            self._start_server(cfg)

    def restart(self, project_root: str):
        """Stop all servers and restart for a new project root."""
        self.stop()
        self.project_root = project_root
        self._ext_map.clear()
        self._clients.clear()
        self.start()

    def stop(self):
        """Stop all running servers."""
        for client in list(self._clients.values()):
            client.stop()
        self._clients.clear()
        self._ext_map.clear()

    # ─────────────────────────────────────────────────────────────
    # Routing
    # ─────────────────────────────────────────────────────────────

    def client_for(self, file_path: str) -> "LSPClient | None":
        """Return the LSPClient responsible for this file, or None."""
        ext = os.path.splitext(file_path)[1].lower()
        return self._ext_map.get(ext)

    def is_supported(self, file_path: str) -> bool:
        client = self.client_for(file_path)
        return client is not None and client.is_ready

    # ─────────────────────────────────────────────────────────────
    # LSP operations — all routed by file extension
    # ─────────────────────────────────────────────────────────────

    def open_file(self, file_path: str, text: str):
        client = self.client_for(file_path)
        if client and client.is_ready:
            client.open_file(file_path, text)

    def change_file(self, file_path: str, text: str):
        client = self.client_for(file_path)
        if client and client.is_ready:
            client.change_file(file_path, text)

    def close_file(self, file_path: str):
        client = self.client_for(file_path)
        if client and client.is_ready:
            client.close_file(file_path)

    def hover(self, file_path: str, line: int, col: int, callback):
        client = self.client_for(file_path)
        if client and client.is_ready:
            client.hover(file_path, line, col, callback)
        else:
            callback(None)

    def definition(self, file_path: str, line: int, col: int, callback):
        client = self.client_for(file_path)
        if client and client.is_ready:
            client.definition(file_path, line, col, callback)
        else:
            callback(None)

    # ─────────────────────────────────────────────────────────────
    # Introspection
    # ─────────────────────────────────────────────────────────────

    def available_server_names(self) -> list[str]:
        """Names of servers that were found on PATH and started."""
        return list(self._clients.keys())

    def supported_extensions(self) -> set[str]:
        """All file extensions with an active LSP client."""
        return set(self._ext_map.keys())

    # ─────────────────────────────────────────────────────────────
    # Internal
    # ─────────────────────────────────────────────────────────────

    def _available_servers(self) -> list[dict]:
        """Filter registry to servers whose binary exists on PATH."""
        return [cfg for cfg in LSP_REGISTRY if shutil.which(cfg["cmd"])]

    def _start_server(self, cfg: dict):
        name = cfg["name"]

        client = LSPClient(
            project_root  = self.project_root,
            cmd           = cfg["cmd"],
            args          = cfg["args"],
            lang_id       = cfg["lang_id"],
            init_options  = cfg.get("init_options", {}),
            parent        = self,
        )

        # Wire signals
        client.initialized.connect(
            lambda n=name: self._on_server_ready(n)
        )
        client.error.connect(
            lambda msg, n=name: self.server_error.emit(n, msg)
        )
        client.stopped.connect(
            lambda n=name: self._on_server_stopped(n)
        )

        client.start()

        # Register under every extension this server handles
        for ext in cfg["extensions"]:
            self._ext_map[ext] = client

        self._clients[name] = client

    def _on_server_ready(self, name: str):
        self.server_ready.emit(name)

    def _on_server_stopped(self, name: str):
        # Clean up extension map entries pointing to this client
        client = self._clients.pop(name, None)
        if client:
            dead_exts = [ext for ext, c in self._ext_map.items() if c is client]
            for ext in dead_exts:
                del self._ext_map[ext]