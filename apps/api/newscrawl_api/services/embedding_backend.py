"""Embedding backend abstraction (BGE-M3 by default).

Lives in the API package because both planes need it: the embedding worker
encodes articles in bulk, and the API encodes ad-hoc semantic-search queries.

Production keeps torch out of the API image: set EMBEDDING_SERVICE_URL to the
embedding worker's internal encode server. Local/dev can leave it empty and
load sentence-transformers in-process (processor image / optional API extra).
"""

import threading
from typing import Protocol

import httpx
from newscrawl_api.config import get_settings


class EmbeddingBackend(Protocol):
    model_name: str
    dimension: int

    def encode(self, texts: list[str]) -> list[list[float]]:
        """Return one normalized (unit-length) vector per input text."""
        ...


class SentenceTransformerBackend:
    """BGE-M3 (or any sentence-transformers model) on CPU/GPU."""

    def __init__(self, model_name: str, dimension: int, device: str = "cpu") -> None:
        from sentence_transformers import SentenceTransformer

        self.model_name = model_name
        self.dimension = dimension
        self._model = SentenceTransformer(model_name, device=device)

    def encode(self, texts: list[str]) -> list[list[float]]:
        vectors = self._model.encode(
            texts, normalize_embeddings=True, show_progress_bar=False
        )
        return [vector.tolist() for vector in vectors]


class HttpEmbeddingBackend:
    """Encode via the embedding worker's internal HTTP server (prod default)."""

    def __init__(self, base_url: str, model_name: str, dimension: int) -> None:
        self.model_name = model_name
        self.dimension = dimension
        self._base_url = base_url.rstrip("/")

    def encode(self, texts: list[str]) -> list[list[float]]:
        try:
            response = httpx.post(
                f"{self._base_url}/v1/encode",
                json={"texts": texts},
                # CPU hosts may be mid article-embed; wait rather than 500.
                timeout=300.0,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise RuntimeError(f"embedding service error: {exc}") from exc
        data = response.json()
        vectors = data.get("vectors")
        if not isinstance(vectors, list) or len(vectors) != len(texts):
            raise RuntimeError("embedding service returned unexpected payload")
        return vectors


_backend: EmbeddingBackend | None = None
_backend_lock = threading.Lock()


def get_embedding_backend() -> EmbeddingBackend:
    """Process-wide singleton (the model weighs ~2 GB; load it once)."""
    global _backend
    if _backend is None:
        with _backend_lock:
            if _backend is None:
                settings = get_settings()
                if settings.embedding_service_url.strip():
                    _backend = HttpEmbeddingBackend(
                        settings.embedding_service_url,
                        settings.embedding_model,
                        settings.embedding_dimension,
                    )
                else:
                    _backend = SentenceTransformerBackend(
                        settings.embedding_model,
                        settings.embedding_dimension,
                        settings.embedding_device,
                    )
    return _backend


def set_embedding_backend(backend: EmbeddingBackend | None) -> None:
    """Test hook / dependency override."""
    global _backend
    _backend = backend
