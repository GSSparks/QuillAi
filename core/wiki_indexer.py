"""
wiki_indexer.py — Background wiki page generator for QuillAI.

Crawls the repo continuously, processing one stale file at a time until
the wiki is fully up to date. Runs on a plain daemon thread — no Qt
threading, no signals, no chaining hacks.

Design
------
- One thread, one file at a time, simple loop
- Sleeps briefly between files to avoid hammering the API
- Priority queue — files opened in the editor jump to the front
- Stops when the queue is empty, restarts when new stale files appear
- Completely independent of WikiWatcher (which handles git commits)

Usage
-----
    indexer = WikiIndexer(wiki_manager)
    indexer.start()                        # begin background crawl
    indexer.prioritize(Path("ui/editor.py"))  # jump a file to front
    indexer.stop()                         # clean shutdown
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Optional, Callable


class WikiIndexer:
    """
    Background thread that keeps the wiki fully indexed.

    Parameters
    ----------
    wiki_manager : WikiManager
        The active WikiManager instance.
    on_file_done : callable, optional
        Called on the main thread after each file is processed.
        Signature: (rel_path: str, success: bool) -> None
        Note: called from the background thread — use Qt signals or
        QMetaObject.invokeMethod if you need to update UI.
    sleep_between : float
        Seconds to sleep between API calls. Prevents hammering local models.
    """

    def __init__(
        self,
        wiki_manager,
        on_file_done: Optional[Callable[[str, bool], None]] = None,
        sleep_between: float = 0.5,
        memory_manager=None,
        faq_manager=None,
    ) -> None:
        self._wm = wiki_manager
        self._mm          = memory_manager
        self._faq_manager = faq_manager   # optional — for fact staleness review
        self._on_file_done = on_file_done
        self._sleep_between = sleep_between

        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._priority: list[Path] = []   # files to process first
        self._lock = threading.Lock()
        self._running = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the background indexer thread."""
        if self._running:
            return
        if not self._wm.enabled:
            return
        self._stop_event.clear()
        self._running = True
        self._thread = threading.Thread(
            target=self._run,
            name="WikiIndexer",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """Signal the indexer to stop and wait for the thread to exit."""
        self._stop_event.set()
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self._thread = None

    def restart(self) -> None:
        """Stop and restart — useful after a project switch."""
        self.stop()
        with self._lock:
            self._priority.clear()
        self.start()

    def prioritize(self, source_path: Path) -> None:
        """
        Jump a file to the front of the processing queue.
        Call this from open_file_in_tab() for on-demand generation.
        No-op if the file is already up to date.
        """
        if not self._wm.enabled:
            return
        src = Path(source_path).resolve()
        if not self._wm.is_stale(src):
            return
        with self._lock:
            # Avoid duplicates
            if src not in self._priority:
                self._priority.insert(0, src)
        # Wake the thread if it's sleeping between files
        if not self._running:
            self.start()

    @property
    def is_running(self) -> bool:
        return self._running and bool(self._thread and self._thread.is_alive())

    # ------------------------------------------------------------------
    # Internal loop
    # ------------------------------------------------------------------

    def _run(self) -> None:
        """Main loop — runs on the background thread."""

        while not self._stop_event.is_set():
            src = self._next_file()

            if src is None:
                # Nothing stale — idle until something changes
                # Poll every 30s in case files changed outside the editor
                self._stop_event.wait(30)
                continue

            rel = str(src.relative_to(self._wm.repo_root))
            success = False
            try:
                was_updated = self._wm.update_file(src)
                success = was_updated
                if was_updated:
                    # Review facts tagged to this file against the new wiki page
                    if self._mm:
                        try:
                            wiki_page = self._wm._read_page(rel)
                            if wiki_page:
                                self._mm.review_facts_for_file(rel, wiki_page)
                        except Exception as e:
                            print(f"[WikiIndexer] fact review failed for {rel}: {e}")
                else:
                    print(f"[WikiIndexer] – {rel} (already current)")
            except Exception as exc:
                print(f"[WikiIndexer] ✗ {rel}: {exc}")

            if self._on_file_done:
                try:
                    self._on_file_done(rel, success)
                except Exception:
                    pass

            # Brief pause between API calls
            if not self._stop_event.is_set():
                self._stop_event.wait(self._sleep_between)

        self._running = False
        print("[WikiIndexer] stopped")

    def _next_file(self) -> Optional[Path]:
        """
        Return the next file to process:
        1. Priority queue first (files opened in editor)
        2. Then any stale file from the full repo scan
        """
        # Check priority queue first
        with self._lock:
            while self._priority:
                src = self._priority.pop(0)
                if src.exists() and self._wm.is_stale(src):
                    return src

        # Fall back to full stale scan
        stale = self._wm.stale_files()
        if not stale:
            return None

        # Return the first stale file as an absolute path
        return (self._wm.repo_root / stale[0]).resolve()