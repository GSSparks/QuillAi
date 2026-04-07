"""
wiki_watcher.py — Git-commit-triggered wiki updater for QuillAI.

Watches `.git/COMMIT_EDITMSG` for modifications (written by git on every
commit) using Qt's QFileSystemWatcher. When a commit is detected, it
tells WikiIndexer to prioritize the changed files so they get processed
next — no direct API calls here.

This class has ONE job: detect git commits and flag changed files as
needing a wiki update. WikiIndexer does the actual generation.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QFileSystemWatcher, QObject, QTimer, pyqtSignal

from core.wiki_manager import _WIKI_EXTENSIONS


class WikiWatcher(QObject):
    """
    Monitors git commits and flags changed files for re-indexing.

    Parameters
    ----------
    wiki_manager : WikiManager
        The active WikiManager instance.
    indexer : WikiIndexer
        The WikiIndexer that will process flagged files.
    parent : QObject, optional
        Qt parent for lifetime management.
    debounce_ms : int
        Milliseconds to wait after COMMIT_EDITMSG changes before acting.
    """

    commit_detected = pyqtSignal(list)   # list of changed rel paths

    def __init__(
        self,
        wiki_manager,
        indexer,
        parent: Optional[QObject] = None,
        debounce_ms: int = 500,
    ) -> None:
        super().__init__(parent)
        self._wm = wiki_manager
        self._indexer = indexer
        self.repo_root = wiki_manager.repo_root
        self._debounce_ms = debounce_ms

        # Deferred until start() — requires running QApplication
        self._fs_watcher: Optional[QFileSystemWatcher] = None
        self._debounce_timer: Optional[QTimer] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> bool:
        """
        Begin watching for git commits.
        Returns True if watching started, False if no .git directory found.
        """
        self._ensure_qt_objects()

        git_dir = self.repo_root / ".git"
        if not git_dir.exists():
            print("[WikiWatcher] No .git directory found — watcher not started.")
            return False

        commit_msg = self._commit_editmsg_path
        if commit_msg.exists():
            self._watch_commit_editmsg()
        else:
            self._fs_watcher.addPath(str(git_dir))
            self._fs_watcher.directoryChanged.connect(self._on_git_dir_changed)

        return True

    def stop(self) -> None:
        """Stop watching."""
        if self._fs_watcher:
            paths = self._fs_watcher.files() + self._fs_watcher.directories()
            if paths:
                self._fs_watcher.removePaths(paths)
        if self._debounce_timer:
            self._debounce_timer.stop()

    # ------------------------------------------------------------------
    # Private — Qt setup
    # ------------------------------------------------------------------

    def _ensure_qt_objects(self) -> None:
        if self._fs_watcher is None:
            self._fs_watcher = QFileSystemWatcher(self)
        if self._debounce_timer is None:
            self._debounce_timer = QTimer(self)
            self._debounce_timer.setSingleShot(True)
            self._debounce_timer.timeout.connect(self._on_commit_detected)

    # ------------------------------------------------------------------
    # Private — git helpers
    # ------------------------------------------------------------------

    @property
    def _commit_editmsg_path(self) -> Path:
        return self.repo_root / ".git" / "COMMIT_EDITMSG"

    def _watch_commit_editmsg(self) -> None:
        path = str(self._commit_editmsg_path)
        if path not in self._fs_watcher.files():
            self._fs_watcher.addPath(path)
            self._fs_watcher.fileChanged.connect(self._on_file_changed)

    def _on_git_dir_changed(self, path: str) -> None:
        if self._commit_editmsg_path.exists():
            self._fs_watcher.removePath(path)
            try:
                self._fs_watcher.directoryChanged.disconnect(self._on_git_dir_changed)
            except TypeError:
                pass
            self._watch_commit_editmsg()

    def _on_file_changed(self, path: str) -> None:
        if path not in self._fs_watcher.files():
            if self._commit_editmsg_path.exists():
                self._fs_watcher.addPath(str(self._commit_editmsg_path))
        self._debounce_timer.start(self._debounce_ms)

    def _on_commit_detected(self) -> None:
        """A commit landed — prioritize changed files in the indexer."""
        changed = self._changed_files_since_last_commit()
        wiki_files = [
            f for f in changed
            if f.suffix.lower() in _WIKI_EXTENSIONS and f.exists()
        ]

        if not wiki_files:
            return

        print(f"[WikiWatcher] commit detected, prioritizing {len(wiki_files)} files")
        for f in wiki_files:
            self._indexer.prioritize(f)

        self.commit_detected.emit([str(f) for f in wiki_files])

    def _changed_files_since_last_commit(self) -> list[Path]:
        for cmd in (
            ["git", "diff", "--name-only", "HEAD~1", "HEAD"],
            ["git", "diff", "--name-only", "HEAD"],
        ):
            try:
                result = subprocess.run(
                    cmd,
                    cwd=self.repo_root,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if result.returncode == 0 and result.stdout.strip():
                    return [
                        (self.repo_root / line.strip()).resolve()
                        for line in result.stdout.strip().splitlines()
                        if line.strip()
                    ]
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass
        return []