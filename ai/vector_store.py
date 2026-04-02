"""
ai/vector_store.py

ChromaDB wrapper providing per-project, per-collection persistent storage.

Collections:
    code          — project functions/classes (chunked by AST symbol)
    conversations — past chat exchanges
    completions   — accepted ghost text + surrounding context
    edit_patterns — co-edited file pairs

All collections are namespaced by a project hash so switching projects
never mixes data. Storage lives at ~/.config/quillai/vector/.
"""

import hashlib
import os
import threading
from typing import Optional


VECTOR_DIR = os.path.join(os.path.expanduser("~"), ".config", "quillai", "vector")

COLLECTIONS = ("code", "conversations", "completions", "edit_patterns")

# Maximum results returned per collection per query
DEFAULT_TOP_K = 5


class VectorStore:
    """
    Per-project ChromaDB wrapper.
    One instance per project — create a new one when the project changes.
    Thread-safe for reads; writes should be called from background threads.
    """

    def __init__(self, project_path: str):
        self.project_path = project_path
        self._project_id  = self._make_project_id(project_path)
        self._client      = None
        self._colls       = {}
        self._lock        = threading.Lock()
        self._ready       = False

    # ─────────────────────────────────────────────────────────────
    # Lifecycle
    # ─────────────────────────────────────────────────────────────

    def open(self):
        """
        Open (or create) the ChromaDB store for this project.
        Safe to call multiple times — idempotent.
        Call from a background thread on project open.
        """
        with self._lock:
            if self._ready:
                return
            try:
                import chromadb
            except ImportError:
                print("[vector_store] chromadb not installed — vector index disabled")
                return

            os.makedirs(VECTOR_DIR, exist_ok=True)
            db_path = os.path.join(VECTOR_DIR, self._project_id)

            self._client = chromadb.PersistentClient(path=db_path)

            for name in COLLECTIONS:
                self._colls[name] = self._client.get_or_create_collection(
                    name=name,
                    metadata={"hnsw:space": "cosine"},
                )

            self._ready = True

    def close(self):
        with self._lock:
            self._ready  = False
            self._colls  = {}
            self._client = None

    @property
    def is_ready(self) -> bool:
        return self._ready

    # ─────────────────────────────────────────────────────────────
    # Write
    # ─────────────────────────────────────────────────────────────

    def upsert(self, collection: str, doc_id: str,
               embedding: list[float], text: str, metadata: dict = None):
        """
        Insert or update a single document.
        doc_id should be stable and unique within the collection
        (e.g. "file.py::ClassName.method_name" for code chunks).
        """
        if not self._ready:
            return
        coll = self._colls.get(collection)
        if not coll:
            return
        coll.upsert(
            ids        = [doc_id],
            embeddings = [embedding],
            documents  = [text],
            metadatas  = [metadata or {}],
        )

    def upsert_batch(self, collection: str,
                     items: list[dict]):
        """
        Batch upsert. Each item: {id, embedding, text, metadata}.
        More efficient than calling upsert() in a loop.
        """
        if not self._ready or not items:
            return
        coll = self._colls.get(collection)
        if not coll:
            return
        coll.upsert(
            ids        = [i["id"]        for i in items],
            embeddings = [i["embedding"] for i in items],
            documents  = [i["text"]      for i in items],
            metadatas  = [i.get("metadata", {}) for i in items],
        )

    def delete(self, collection: str, doc_id: str):
        if not self._ready:
            return
        coll = self._colls.get(collection)
        if coll:
            try:
                coll.delete(ids=[doc_id])
            except Exception:
                pass

    # ─────────────────────────────────────────────────────────────
    # Query
    # ─────────────────────────────────────────────────────────────

    def query(self, collection: str, embedding: list[float],
              top_k: int = DEFAULT_TOP_K,
              where: dict = None) -> list[dict]:
        """
        Find the top_k most similar documents to the query embedding.
        Returns list of {text, metadata, distance, id}.
        Lower distance = more similar (cosine distance).
        """
        if not self._ready:
            return []
        coll = self._colls.get(collection)
        if not coll:
            return []
        try:
            kwargs = {
                "query_embeddings": [embedding],
                "n_results":        min(top_k, coll.count() or 1),
                "include":          ["documents", "metadatas", "distances"],
            }
            if where:
                kwargs["where"] = where

            results = coll.query(**kwargs)

            output = []
            for i, doc in enumerate(results["documents"][0]):
                output.append({
                    "text":     doc,
                    "metadata": results["metadatas"][0][i],
                    "distance": results["distances"][0][i],
                    "id":       results["ids"][0][i],
                })
            return output
        except Exception as e:
            print(f"[vector_store] query error: {e}")
            return []

    def query_multi(self, embedding: list[float],
                    top_k: int = DEFAULT_TOP_K) -> dict[str, list[dict]]:
        """Query all collections at once. Returns {collection: [results]}."""
        return {
            name: self.query(name, embedding, top_k)
            for name in COLLECTIONS
            if self._colls.get(name)
        }

    def count(self, collection: str) -> int:
        if not self._ready:
            return 0
        coll = self._colls.get(collection)
        return coll.count() if coll else 0

    # ─────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────

    @staticmethod
    def _make_project_id(project_path: str) -> str:
        name = os.path.basename(project_path.rstrip("/\\"))
        h    = hashlib.md5(project_path.encode()).hexdigest()[:12]
        return f"{name}_{h}"