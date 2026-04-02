"""
ui/startup_progress.py

Tracks background startup tasks and shows a single animated status bar
message while they're in flight. Clears automatically once all tasks
report complete.

Usage:
    progress = StartupProgress(status_bar)
    progress.register("LSP")
    progress.register("Repo Map")
    progress.register("Vector Index")

    # When each system is ready:
    progress.complete("LSP")
    progress.complete("Repo Map")
    progress.complete("Vector Index")   # ← clears the indicator
"""

from PyQt6.QtCore import QObject, QTimer


class StartupProgress(QObject):
    """
    Manages a set of named startup tasks and shows animated progress
    in the status bar until all tasks complete.
    """

    _FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    _INTERVAL_MS = 80

    def __init__(self, status_bar, parent=None):
        super().__init__(parent)
        self._status_bar = status_bar
        self._pending: set[str] = set()
        self._done:    set[str] = set()
        self._frame    = 0

        self._timer = QTimer(self)
        self._timer.setInterval(self._INTERVAL_MS)
        self._timer.timeout.connect(self._tick)

    # ─────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────

    def register(self, name: str):
        """Register a task that must complete before startup is done."""
        self._pending.add(name)
        if not self._timer.isActive():
            self._timer.start()
        self._render()

    def complete(self, name: str):
        """Mark a task as complete. Clears the indicator when all are done."""
        self._pending.discard(name)
        self._done.add(name)
        if not self._pending:
            self._finish()
        else:
            self._render()

    def is_finished(self) -> bool:
        return not self._pending

    # ─────────────────────────────────────────────────────────────
    # Internal
    # ─────────────────────────────────────────────────────────────

    def _tick(self):
        self._frame = (self._frame + 1) % len(self._FRAMES)
        self._render()

    def _render(self):
        if not self._pending:
            return
        spinner  = self._FRAMES[self._frame]
        n_done   = len(self._done)
        n_total  = n_done + len(self._pending)
        # Show the first pending task name as current activity
        current  = sorted(self._pending)[0]
        msg = (
            f"{spinner}  Starting up — {current}"
            + (f"  ({n_done}/{n_total} ready)" if n_total > 1 else "")
        )
        self._status_bar.showMessage(msg)

    def _finish(self):
        self._timer.stop()
        n = len(self._done)
        self._status_bar.showMessage(
            f"✓  Ready  ({n} system{'s' if n != 1 else ''} loaded)", 4000
        )