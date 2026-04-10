"""
core/project_settings.py

Per-project settings stored at:
  ~/.config/quillai/projects/<name>_<hash>/settings.json

Keeps project-specific config (GitLab credentials, etc.) out of
the global settings and out of the repo entirely.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Optional
from core.keyring_store import (
    store_project_token, load_project_token
)


PROJECTS_DIR = os.path.join(
    os.path.expanduser("~"), ".config", "quillai", "projects"
)


class ProjectSettings:
    """
    Per-project settings with get/set/save.
    Initialized with None project_path — call set_project() when
    a project is opened.
    """

    def __init__(self, project_path: str = None):
        self._path:     Optional[str]  = None
        self._settings: dict           = {}
        self._file:     Optional[Path] = None
        if project_path:
            self.set_project(project_path)

    # ── Project lifecycle ─────────────────────────────────────────────────

    def set_project(self, project_path: str):
        self._path     = project_path
        self._file     = self._settings_file(project_path)
        self._settings = self._load()

    def _settings_file(self, project_path: str) -> Path:
        name = os.path.basename(project_path.rstrip("/\\"))
        h    = hashlib.md5(project_path.encode()).hexdigest()[:12]
        d    = Path(PROJECTS_DIR) / f"{name}_{h}"
        d.mkdir(parents=True, exist_ok=True)
        return d / "settings.json"

    def _load(self) -> dict:
        if self._file and self._file.exists():
            try:
                return json.loads(self._file.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def save(self):
        if self._file:
            try:
                self._file.write_text(
                    json.dumps(self._settings, indent=2),
                    encoding="utf-8",
                )
            except Exception as e:
                print(f"[ProjectSettings] save failed: {e}")

    # ── Generic get/set ───────────────────────────────────────────────────

    def get(self, key: str, default: Any = "") -> Any:
        return self._settings.get(key, default)

    def set(self, key: str, value: Any):
        self._settings[key] = value
        self.save()

    def has_project(self) -> bool:
        return self._path is not None

    # ── GitLab ────────────────────────────────────────────────────────────

    def get_gitlab_url(self) -> str:
        return self._settings.get("gitlab_url", "").strip()

    def get_gitlab_token(self) -> str:
        val = self._settings.get("gitlab_token", "").strip()
        if val == "__keyring__":
            return load_project_token(
                self._project_hash(), 'gitlab_token'
            )
        # Migrate plain text token to keyring on first read
        if val and val != "__keyring__":
            store_project_token(self._project_hash(),
                                'gitlab_token', val)
            self._settings["gitlab_token"] = "__keyring__"
            self.save()
            return val
        return ""

    def get_gitlab_project_id(self) -> str:
        return self._settings.get("gitlab_project_id", "").strip()

    def set_gitlab_settings(self, url: str, token: str, project_id: str):
        self._settings["gitlab_url"]        = url.strip()
        self._settings["gitlab_project_id"] = project_id.strip()
        # Store token in keyring, never in JSON
        if token.strip():
            store_project_token(self._project_hash(), 'gitlab_token',
                                token.strip())
            self._settings["gitlab_token"] = "__keyring__"
        self.save()

    def _project_hash(self) -> str:
        """Short hash identifying this project for keyring lookup."""
        import hashlib
        return hashlib.md5(
            (self._path or '').encode()
        ).hexdigest()[:12]

    def has_gitlab(self) -> bool:
        return bool(
            self.get_gitlab_url() and
            self.get_gitlab_token() and
            self.get_gitlab_project_id()
        )

    # ── Terraform / Terragrunt ────────────────────────────────────────────
    # Reserved for future use

    def get_tf_workspace(self) -> str:
        return self._settings.get("tf_workspace", "").strip()

    def set_tf_workspace(self, workspace: str):
        self._settings["tf_workspace"] = workspace.strip()
        self.save()