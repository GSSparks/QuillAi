"""
editor/wiki_mixin.py

WikiMixin — wiki and repo map initialization.
Mixed into CodeEditor.
"""

import threading
from pathlib import Path as _Path
from PyQt6.QtCore import pyqtSlot


class WikiMixin:

    def _init_repo_map(self, project_root: str):
        """Build repo map in background thread, notify on Qt thread when done."""
        from ai.repo_map import RepoMap
        self.repo_map = RepoMap(project_root)

        def _build_and_notify():
            self.repo_map._build_all()
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(0, self._on_repo_map_ready)

        threading.Thread(target=_build_and_notify, daemon=True).start()

    @pyqtSlot()
    def _on_repo_map_ready(self):
        self._startup.complete("Repo Map")
        if (hasattr(self, "wiki_context_builder")
                and self.wiki_context_builder is not None
                and self.repo_map is not None):
            self.wiki_context_builder._repo_map = self.repo_map

    def _init_wiki(self, project_root: str) -> None:
        from core.wiki_manager import WikiManager
        from core.wiki_indexer import WikiIndexer
        from core.wiki_watcher import WikiWatcher
        from core.wiki_context_builder import WikiContextBuilder
        from PyQt6.QtCore import QMetaObject, Qt as _Qt

        # Tear down existing
        if hasattr(self, "wiki_watcher") and self.wiki_watcher:
            self.wiki_watcher.stop()
        if hasattr(self, "wiki_indexer") and self.wiki_indexer:
            self.wiki_indexer.stop()

        self.wiki_manager = WikiManager(
            repo_root=_Path(project_root),
            model   = self.settings_manager.get_active_model(),
            api_url = self.settings_manager.get_llm_url(),
            api_key = self.settings_manager.get_api_key(),
            backend = self.settings_manager.get_backend(),
        )

        if not self.wiki_manager.enabled:
            self.wiki_context_builder = None
            self.wiki_indexer         = None
            self.wiki_watcher         = None
            return

        self.wiki_context_builder = WikiContextBuilder(
            self.wiki_manager,
            char_budget = 6000,
            repo_map    = self.repo_map if hasattr(self, "repo_map") else None,
        )

        def _on_file_done(rel, success):
            if success:
                from PyQt6.QtCore import QTimer
                QTimer.singleShot(
                    0,
                    lambda r=rel: self.statusBar().showMessage(
                        f"Wiki: indexed {r}", 3000
                    )
                )

        self.wiki_indexer = WikiIndexer(
            wiki_manager = self.wiki_manager,
            on_file_done = _on_file_done,
            faq_manager  = getattr(self, "faq_manager", None),
        )
        self.wiki_indexer.start()

        self.wiki_watcher = WikiWatcher(
            wiki_manager = self.wiki_manager,
            indexer      = self.wiki_indexer,
        )
        self.wiki_watcher.start()
