"""Embedding backend abstraction (BGE-M3 by default).

Lives in the API package because both planes need it: the embedding worker
encodes articles in bulk, and the API encodes ad-hoc semantic-search queries.
The heavyweight sentence-transformers import happens lazily on first use, so
API processes that never serve semantic search never load torch.
"""

import threading
from typing import Protocol

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
        vectors = self._model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return [vector.tolist() for vector in vectors]


_backend: EmbeddingBackend | None = None
_backend_lock = threading.Lock()


def get_embedding_backend() -> EmbeddingBackend:
    """Process-wide singleton (the model weighs ~2 GB; load it once)."""
    global _backend
    if _backend is None:
        with _backend_lock:
            if _backend is None:
                settings = get_settings()
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
