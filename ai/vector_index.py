"""
ai/vector_index.py

Orchestrates all four vector indexes and provides the query interface
used by ContextEngine.

Indexing:
    index_project(root)          — full project code scan (background)
    index_file(path)             — re-index one file after save (background)
    index_conversation(u, a)     — index a chat exchange (background)
    index_completion(code, ctx)  — index an accepted completion (background)
    index_edit(from_path, to_path) — record a file co-edit pair (background)

Querying:
    query(text, top_k)           — returns merged VectorContext

All public methods are non-blocking — they spawn background threads.
query() is the exception: it's synchronous but fast (<50ms typical).
Call it from inside an existing background thread (e.g. the LSP fetch
callback chain in _on_chat_message).
"""

import ast
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

from ai.embedder import Embedder, EmbeddingUnavailable
from ai.vector_store import VectorStore


# Similarity threshold — results with distance > this are discarded
# (cosine distance: 0 = identical, 2 = opposite)
MAX_DISTANCE = 0.8

# How many results to pull from each collection before merging
TOP_K_PER_COLLECTION = 5


@dataclass
class VectorResult:
    text:       str
    source:     str    # collection name
    metadata:   dict   = field(default_factory=dict)
    distance:   float  = 1.0


@dataclass
class VectorContext:
    results:    list[VectorResult] = field(default_factory=list)

    def format(self) -> str:
        """Format for injection into the LLM prompt."""
        if not self.results:
            return ""
        parts = []
        for r in self.results:
            label = {
                "code":          "Related code",
                "conversations": "Past conversation",
                "completions":   "Accepted completion",
                "edit_patterns": "Co-edited file",
            }.get(r.source, r.source)
            parts.append(f"[{label}]\n{r.text}")
        return "[Vector Context]\n" + "\n\n".join(parts)


class VectorIndex:
    """
    Owns the VectorStore and Embedder for one project.
    Create a new instance when the project changes.
    """

    def __init__(self, project_root: str, settings_manager=None):
        self.project_root = project_root
        self._store       = VectorStore(project_root)
        self._embedder    = Embedder.instance()
        if settings_manager:
            self._embedder.set_settings(settings_manager)
        self._ready       = False

        # Start store open in background
        threading.Thread(target=self._open, daemon=True).start()

    # ─────────────────────────────────────────────────────────────
    # Lifecycle
    # ─────────────────────────────────────────────────────────────

    def _open(self):
        self._store.open()
        self._ready = self._store.is_ready

    def close(self):
        self._store.close()
        self._ready = False

    @property
    def is_ready(self) -> bool:
        return self._ready and self._store.is_ready

    # ─────────────────────────────────────────────────────────────
    # Indexing — all non-blocking
    # ─────────────────────────────────────────────────────────────

    def index_project(self, root: str = None):
        """Full project scan. Runs in background. Safe to call on open."""
        root = root or self.project_root
        threading.Thread(
            target=self._index_project_sync, args=(root,), daemon=True
        ).start()

    def index_file(self, file_path: str):
        """Re-index a single file after save."""
        threading.Thread(
            target=self._index_file_sync, args=(file_path,), daemon=True
        ).start()

    def index_conversation(self, user_text: str, ai_response: str):
        """Index a completed chat exchange."""
        threading.Thread(
            target=self._index_conversation_sync,
            args=(user_text, ai_response),
            daemon=True,
        ).start()

    def index_completion(self, accepted_text: str, context_before: str,
                         file_path: str = ""):
        """Index ghost text the user accepted."""
        threading.Thread(
            target=self._index_completion_sync,
            args=(accepted_text, context_before, file_path),
            daemon=True,
        ).start()

    def index_edit(self, from_path: str, to_path: str):
        """Record that from_path and to_path were edited in the same session."""
        threading.Thread(
            target=self._index_edit_sync,
            args=(from_path, to_path),
            daemon=True,
        ).start()

    # ─────────────────────────────────────────────────────────────
    # Query — synchronous, call from background thread
    # ─────────────────────────────────────────────────────────────

    def query(self, text: str, top_k: int = TOP_K_PER_COLLECTION) -> VectorContext:
        """
        Embed the query and search all collections.
        Returns a VectorContext with merged, deduplicated, ranked results.
        Call from a background thread — embedding takes ~10-50ms.
        """
        if not self.is_ready:
            return VectorContext()

        try:
            embedding = self._embedder.embed_one(text)
        except EmbeddingUnavailable:
            return VectorContext()
        except Exception as e:
            print(f"[vector_index] embed error: {e}")
            return VectorContext()

        raw = self._store.query_multi(embedding, top_k=top_k)

        results = []
        seen_texts = set()

        for collection, hits in raw.items():
            for hit in hits:
                if hit["distance"] > MAX_DISTANCE:
                    continue
                # Deduplicate by text content
                key = hit["text"][:100]
                if key in seen_texts:
                    continue
                seen_texts.add(key)
                results.append(VectorResult(
                    text     = hit["text"],
                    source   = collection,
                    metadata = hit["metadata"],
                    distance = hit["distance"],
                ))

        # Sort by similarity (lowest distance first), cap total results
        results.sort(key=lambda r: r.distance)
        return VectorContext(results=results[:top_k * 2])

    # ─────────────────────────────────────────────────────────────
    # Sync indexing implementations
    # ─────────────────────────────────────────────────────────────

    def _index_project_sync(self, root: str):
        """Walk project, extract code symbols, batch-embed and upsert."""
        if not self._wait_ready():
            return

        skip = {
            "__pycache__", ".git", "node_modules",
            "venv", ".venv", "dist", "build",
        }
        chunks = []

        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [
                d for d in dirnames
                if d not in skip and not d.startswith(".")
            ]
            for fname in filenames:
                if not fname.endswith(".py"):
                    continue
                full = os.path.join(dirpath, fname)
                chunks.extend(self._extract_code_chunks(full, root))

        if not chunks:
            return

        self._embed_and_upsert("code", chunks)

    def _index_file_sync(self, file_path: str):
        if not self._wait_ready():
            return
        if not file_path.endswith(".py"):
            return
        chunks = self._extract_code_chunks(file_path, self.project_root)
        if chunks:
            self._embed_and_upsert("code", chunks)

    def _index_conversation_sync(self, user_text: str, ai_response: str):
        if not self._wait_ready():
            return
        # Store user+assistant as one chunk so context is preserved
        text = f"User: {user_text}\n\nAssistant: {ai_response[:500]}"
        doc_id = f"conv_{int(time.time() * 1000)}"
        try:
            embedding = self._embedder.embed_one(text)
            self._store.upsert(
                collection = "conversations",
                doc_id     = doc_id,
                embedding  = embedding,
                text       = text,
                metadata   = {
                    "ts":        int(time.time()),
                    "user_len":  len(user_text),
                },
            )
        except Exception as e:
            print(f"[vector_index] conversation index error: {e}")

    def _index_completion_sync(self, accepted_text: str,
                               context_before: str, file_path: str):
        if not self._wait_ready():
            return
        # Store context + accepted text so we can retrieve "what did I
        # write after code that looked like this"
        context_snippet = context_before[-300:] if context_before else ""
        text = f"Context:\n{context_snippet}\n\nAccepted:\n{accepted_text}"
        doc_id = f"completion_{int(time.time() * 1000)}"
        try:
            embedding = self._embedder.embed_one(text)
            self._store.upsert(
                collection = "completions",
                doc_id     = doc_id,
                embedding  = embedding,
                text       = text,
                metadata   = {
                    "file_path": file_path,
                    "ts":        int(time.time()),
                },
            )
        except Exception as e:
            print(f"[vector_index] completion index error: {e}")

    def _index_edit_sync(self, from_path: str, to_path: str):
        if not self._wait_ready():
            return
        if not from_path or not to_path or from_path == to_path:
            return
        rel_from = os.path.relpath(from_path, self.project_root)
        rel_to   = os.path.relpath(to_path,   self.project_root)
        text     = f"Files edited together: {rel_from} and {rel_to}"
        doc_id   = f"edit_{rel_from}___{rel_to}".replace("/", "_").replace("\\", "_")
        try:
            embedding = self._embedder.embed_one(text)
            self._store.upsert(
                collection = "edit_patterns",
                doc_id     = doc_id,
                embedding  = embedding,
                text       = text,
                metadata   = {
                    "from_path": rel_from,
                    "to_path":   rel_to,
                    "ts":        int(time.time()),
                },
            )
        except Exception as e:
            print(f"[vector_index] edit pattern index error: {e}")

    # ─────────────────────────────────────────────────────────────
    # Code chunking
    # ─────────────────────────────────────────────────────────────

    def _extract_code_chunks(self, file_path: str, root: str) -> list[dict]:
        """
        Parse a Python file and return one chunk per top-level symbol.
        Each chunk contains the full source of the function/class plus
        its docstring, so embedding captures both structure and intent.
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                source = f.read()
        except Exception:
            return []

        try:
            tree = ast.parse(source)
        except Exception:
            return []

        rel_path = os.path.relpath(file_path, root)
        lines    = source.splitlines()
        chunks   = []

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                continue
            if not hasattr(node, "end_lineno"):
                continue

            # Stable ID: relative path + symbol name + line number
            doc_id = f"{rel_path}::{node.name}:{node.lineno}"

            # Full source of the symbol
            symbol_src = "\n".join(lines[node.lineno - 1 : node.end_lineno])

            # Include docstring separately for better embedding
            docstring  = ast.get_docstring(node) or ""
            kind       = "class" if isinstance(node, ast.ClassDef) else "function"

            text = (
                f"# {kind}: {node.name} in {rel_path}\n"
                + (f'"""{docstring}"""\n' if docstring else "")
                + symbol_src[:1500]   # cap chunk size
            )

            chunks.append({
                "id":       doc_id,
                "text":     text,
                "metadata": {
                    "file":    rel_path,
                    "symbol":  node.name,
                    "kind":    kind,
                    "line":    node.lineno,
                },
            })

        return chunks

    # ─────────────────────────────────────────────────────────────
    # Batch embed + upsert
    # ─────────────────────────────────────────────────────────────

    def _embed_and_upsert(self, collection: str, chunks: list[dict]):
        """Embed a batch of chunks and upsert into the given collection."""
        texts = [c["text"] for c in chunks]
        try:
            embeddings = self._embedder.embed(texts)
        except EmbeddingUnavailable:
            return
        except Exception as e:
            print(f"[vector_index] embed error: {e}")
            return

        items = [
            {
                "id":        chunks[i]["id"],
                "embedding": embeddings[i],
                "text":      chunks[i]["text"],
                "metadata":  chunks[i].get("metadata", {}),
            }
            for i in range(len(chunks))
        ]
        self._store.upsert_batch(collection, items)

    # ─────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────

    def _wait_ready(self, timeout: float = 10.0) -> bool:
        """Wait up to timeout seconds for the store to be ready."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.is_ready:
                return True
            time.sleep(0.1)
        print("[vector_index] store not ready — skipping index operation")
        return False