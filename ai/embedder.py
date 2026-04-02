"""
ai/embedder.py

Embedding router for QuillAI.

Backend selection:
    llama  → sentence-transformers (local, in-process, always works)
    openai → OpenAI text-embedding-3-small
    claude → OpenAI text-embedding-3-small (Anthropic has no embedding API)
             falls back to sentence-transformers if no OpenAI key is set

The sentence-transformers model is loaded lazily on first use and cached
for the lifetime of the process. All embedding calls are synchronous —
callers must run them in a background thread.
"""

import os
import threading
from typing import Optional

MODEL_NAME = "all-MiniLM-L6-v2"
OPENAI_EMBED_MODEL = "text-embedding-3-small"

# If QuillAI is installed via Nix the model is bundled here.
# Falls back to the default HuggingFace cache if not set.
_BUNDLED_MODEL_DIR = os.environ.get("QUILLAI_MODELS_DIR", "")


class Embedder:
    """
    Thread-safe embedding router.
    One instance shared across the whole app — use Embedder.instance().
    """

    _instance: Optional["Embedder"] = None
    _lock = threading.Lock()

    @classmethod
    def instance(cls) -> "Embedder":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def __init__(self):
        self._st_model = None
        self._st_lock  = threading.Lock()
        self._settings = None   # injected by main after SettingsManager exists

    def set_settings(self, settings_manager):
        self._settings = settings_manager

    # ─────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────

    def embed(self, texts: list[str]) -> list[list[float]]:
        """
        Embed a list of strings. Returns a list of float vectors.
        Raises EmbeddingUnavailable if no backend is configured.
        Callers must run this in a background thread.
        """
        if not texts:
            return []

        backend = self._backend()

        if backend == "openai":
            key = self._openai_key()
            if key:
                try:
                    return self._embed_openai(texts, key)
                except Exception as e:
                    print(f"[embedder] OpenAI embedding failed: {e}, falling back to local")

        # local fallback (also the primary path for llama backend)
        return self._embed_local(texts)

    def embed_one(self, text: str) -> list[float]:
        """Convenience wrapper for a single string."""
        results = self.embed([text])
        return results[0] if results else []

    def is_available(self) -> bool:
        """Returns True if at least one embedding backend is usable."""
        try:
            self._get_st_model()
            return True
        except Exception:
            return False

    # ─────────────────────────────────────────────────────────────
    # Backends
    # ─────────────────────────────────────────────────────────────

    def _embed_local(self, texts: list[str]) -> list[list[float]]:
        model = self._get_st_model()
        embeddings = model.encode(
            texts,
            convert_to_numpy=True,
            show_progress_bar=False,
            normalize_embeddings=True,
        )
        return [e.tolist() for e in embeddings]

    def _embed_openai(self, texts: list[str], api_key: str) -> list[list[float]]:
        import urllib.request
        import json

        # Batch in groups of 100 (OpenAI limit is 2048 but we stay conservative)
        results = []
        for i in range(0, len(texts), 100):
            batch = texts[i:i + 100]
            payload = json.dumps({
                "model": OPENAI_EMBED_MODEL,
                "input": batch,
            }).encode("utf-8")
            req = urllib.request.Request(
                "https://api.openai.com/v1/embeddings",
                data=payload,
                headers={
                    "Content-Type":  "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
            # data["data"] is sorted by index
            for item in sorted(data["data"], key=lambda x: x["index"]):
                results.append(item["embedding"])
        return results

    # ─────────────────────────────────────────────────────────────
    # sentence-transformers model loader
    # ─────────────────────────────────────────────────────────────

    def _get_st_model(self):
        if self._st_model is not None:
            return self._st_model
        with self._st_lock:
            if self._st_model is not None:
                return self._st_model
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError:
                raise EmbeddingUnavailable(
                    "sentence-transformers is not installed."
                )
            cache = os.path.join(
                os.path.expanduser("~"),
                ".cache", "huggingface", "hub"
            )
            model_cached = any(
                "all-MiniLM-L6-v2" in d
                for d in os.listdir(cache)
                if os.path.isdir(os.path.join(cache, d))
            ) if os.path.isdir(cache) else False
    
            if not model_cached:
                print(
                    "[embedder] Downloading all-MiniLM-L6-v2 (~90MB) "
                    "to ~/.cache/huggingface/ — one-time download"
                )
            self._st_model = SentenceTransformer(MODEL_NAME)
        return self._st_model

    # ─────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────

    def _backend(self) -> str:
        if self._settings:
            return self._settings.get_backend() or "llama"
        return "llama"

    def _openai_key(self) -> str:
        if self._settings:
            return self._settings.get_api_key() or ""
        return ""


class EmbeddingUnavailable(Exception):
    pass