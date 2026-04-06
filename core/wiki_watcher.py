"""
wiki_watcher.py — Git-commit-triggered wiki updater for QuillAI.

Watches `.git/COMMIT_EDITMSG` for modifications (written by git on every
commit) using Qt's QFileSystemWatcher so it integrates cleanly with the
existing event loop without a background thread.

On each detected commit it:
  1. Resolves which .py files changed via `git diff --name-only HEAD~1 HEAD`
  2. Calls WikiManager.update_file() for each changed file
  3. Emits signals so the UI can show progress / completion toasts

Usage
-----
    watcher = WikiWatcher(wiki_manager, repo_root, parent=main_window)
    watcher.start()          # begin watching
    watcher.stop()           # clean up

Signals
-------
    update_started(int n_files)        — fired when a commit is detected
    file_updated(str rel_path)         — fired after each page is regenerated
    update_finished(list[str] updated) — fired when the full batch is done
    update_failed(str error)           — fired if something goes wrong
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QFileSystemWatcher, QObject, QThread, QTimer, pyqtSignal
from core.wiki_manager import _WIKI_EXTENSIONS


# ---------------------------------------------------------------------------
# Background worker
# ---------------------------------------------------------------------------

class _UpdateWorker(QObject):
    """
    Runs WikiManager updates off the main thread so the editor stays responsive.
    """

    file_updated = pyqtSignal(str)
    finished = pyqtSignal(list)
    failed = pyqtSignal(str)

    def __init__(self, wiki_manager, changed_files: list[Path]) -> None:
        super().__init__()
        self._wm = wiki_manager
        self._files = changed_files

    def run(self) -> None:
        updated: list[str] = []
        try:
            for src in self._files:
                if src.suffix.lower() not in _WIKI_EXTENSIONS:
                    continue
                was_updated = self._wm.update_file(src)
                if was_updated:
                    rel = str(src.relative_to(self._wm.repo_root))
                    updated.append(rel)
                    self.file_updated.emit(rel)
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.finished.emit(updated)


# ---------------------------------------------------------------------------
# WikiWatcher
# ---------------------------------------------------------------------------

class WikiWatcher(QObject):
    """
    Monitors the repo's git activity and keeps the wiki up to date.

    Parameters
    ----------
    wiki_manager : WikiManager
        The WikiManager instance to delegate updates to.
    repo_root : Path
        Absolute path to the repository root.
    parent : QObject, optional
        Qt parent for lifetime management.
    debounce_ms : int
        Milliseconds to wait after a COMMIT_EDITMSG change before acting.
        Prevents double-fires on rapid git operations.
    """

    update_started = pyqtSignal(int)          # n_files about to be updated
    file_updated = pyqtSignal(str)            # rel path of each updated page
    update_finished = pyqtSignal(list)        # list of updated rel paths
    update_failed = pyqtSignal(str)           # error message

    def __init__(
        self,
        wiki_manager,
        repo_root: Optional[Path] = None,
        parent: Optional[QObject] = None,
        debounce_ms: int = 500,
    ) -> None:
        super().__init__(parent)
        self._wm = wiki_manager
        # Always use the wiki_manager's project root — single source of truth
        self.repo_root = wiki_manager.repo_root
        self._debounce_ms = debounce_ms

        # Deferred — created in start() once QApplication exists
        self._fs_watcher: Optional[QFileSystemWatcher] = None
        self._debounce_timer: Optional[QTimer] = None

        self._thread: Optional[QThread] = None
        self._worker: Optional[_UpdateWorker] = None
        self._busy = False

    def _ensure_qt_objects(self) -> None:
        """Create Qt objects that require a running QApplication."""
        if self._fs_watcher is None:
            self._fs_watcher = QFileSystemWatcher(self)
        if self._debounce_timer is None:
            self._debounce_timer = QTimer(self)
            self._debounce_timer.setSingleShot(True)
            self._debounce_timer.timeout.connect(self._on_commit_detected)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> bool:
        """
        Begin watching for git commits.

        Returns True if the watch target exists and watching started,
        False if the repo has no git directory yet.
        """
        self._ensure_qt_objects()
        commit_msg = self._commit_editmsg_path
        git_dir = self.repo_root / ".git"

        if not git_dir.exists():
            print("[WikiWatcher] No .git directory found — watcher not started.")
            return False

        # Watch COMMIT_EDITMSG if it exists, otherwise watch the .git dir
        # and switch to the file once it appears.
        if commit_msg.exists():
            self._watch_commit_editmsg()
        else:
            self._fs_watcher.addPath(str(git_dir))
            self._fs_watcher.directoryChanged.connect(self._on_git_dir_changed)

        return True

    def stop(self) -> None:
        """Stop watching and clean up any running worker thread."""
        if self._fs_watcher:
            paths = self._fs_watcher.files() + self._fs_watcher.directories()
            if paths:
                self._fs_watcher.removePaths(paths)
        if self._debounce_timer:
            self._debounce_timer.stop()
        self._cleanup_thread()

    def trigger_full_update(self, only_if_empty: bool = True) -> None:
        """
        Trigger an incremental wiki update for stale files.

        The stale file scan runs on a background thread to avoid blocking
        the Qt main thread on large repos.

        Parameters
        ----------
        only_if_empty : bool
            If True (default), only bootstraps when wiki has no pages yet.
            Set False to force a full rescan (e.g. after a pull).
        """
        if self._busy:
            return
        if only_if_empty:
            existing = list(self._wm._wiki_dir.rglob("*.md"))
            if existing:
                return

        import threading as _threading
        def _scan_and_dispatch():
            stale = [self.repo_root / p for p in self._wm.stale_files()]
            if stale:
                # Use QTimer to hop back onto the Qt thread before dispatching
                from PyQt6.QtCore import QTimer as _QTimer
                _QTimer.singleShot(0, lambda: self._dispatch_update(stale))

        _threading.Thread(target=_scan_and_dispatch, daemon=True).start()

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
        """Called when something appears in .git/ — look for COMMIT_EDITMSG."""
        if self._commit_editmsg_path.exists():
            # Disconnect dir watcher; switch to file watcher
            self._fs_watcher.removePath(path)
            try:
                self._fs_watcher.directoryChanged.disconnect(self._on_git_dir_changed)
            except TypeError:
                pass
            self._watch_commit_editmsg()

    def _on_file_changed(self, path: str) -> None:
        """
        QFileSystemWatcher fires this when COMMIT_EDITMSG is written.
        Some editors/git versions unlink-and-recreate the file, so we
        re-add it if it disappeared from the watch list.
        """
        if path not in self._fs_watcher.files():
            # File was replaced — re-add it
            if self._commit_editmsg_path.exists():
                self._fs_watcher.addPath(str(self._commit_editmsg_path))

        # Debounce — don't act immediately in case git writes multiple times
        self._debounce_timer.start(self._debounce_ms)

    def _on_commit_detected(self) -> None:
        """Debounce timer expired — a commit has landed. Find changed files."""
        if self._busy:
            # Queue another check after current update finishes
            self._debounce_timer.start(2000)
            return

        changed = self._changed_files_since_last_commit()
        py_files = [f for f in changed if f.suffix.lower() in _WIKI_EXTENSIONS and f.exists()]

        if not py_files:
            return

        self._dispatch_update(py_files)

    def _changed_files_since_last_commit(self) -> list[Path]:
        """
        Run `git diff --name-only HEAD~1 HEAD` to get files changed in the
        last commit. Falls back to `git diff --name-only HEAD` (staged) if
        HEAD~1 doesn't exist (initial commit).
        """
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

    # ------------------------------------------------------------------
    # Private — threading
    # ------------------------------------------------------------------

    def _dispatch_update(self, files: list[Path]) -> None:
        self._busy = True
        self.update_started.emit(len(files))

        self._thread = QThread()
        self._worker = _UpdateWorker(self._wm, files)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.file_updated.connect(self.file_updated)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.failed.connect(self._on_worker_failed)

        self._thread.start()

    def _on_worker_finished(self, updated: list) -> None:
        self._busy = False
        self.update_finished.emit(updated)
        self._cleanup_thread()

    def _on_worker_failed(self, error: str) -> None:
        self._busy = False
        self.update_failed.emit(error)
        self._cleanup_thread()

    def _cleanup_thread(self) -> None:
        if self._thread and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(3000)
        self._thread = None
        self._worker = None
