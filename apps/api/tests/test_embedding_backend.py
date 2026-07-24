"""Unit tests for HTTP embedding backend (no network / no torch)."""

from unittest.mock import MagicMock, patch

import httpx
import pytest
from newscrawl_api.config import get_settings
from newscrawl_api.services.embedding_backend import (
    HttpEmbeddingBackend,
    get_embedding_backend,
    set_embedding_backend,
)


class TestHttpEmbeddingBackend:
    def test_encode_posts_texts(self) -> None:
        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.json.return_value = {
            "vectors": [[0.1, 0.2], [0.3, 0.4]],
            "model": "BAAI/bge-m3",
            "dimension": 2,
        }
        backend = HttpEmbeddingBackend("http://embed:8081", "BAAI/bge-m3", 2)
        with patch("newscrawl_api.services.embedding_backend.httpx.post", return_value=response) as post:
            vectors = backend.encode(["a", "b"])
        assert vectors == [[0.1, 0.2], [0.3, 0.4]]
        post.assert_called_once()
        assert post.call_args.args[0] == "http://embed:8081/v1/encode"
        assert post.call_args.kwargs["json"] == {"texts": ["a", "b"]}

    def test_encode_raises_on_http_error(self) -> None:
        backend = HttpEmbeddingBackend("http://embed:8081", "BAAI/bge-m3", 1024)
        with patch(
            "newscrawl_api.services.embedding_backend.httpx.post",
            side_effect=httpx.ConnectError("down"),
        ):
            with pytest.raises(RuntimeError, match="embedding service error"):
                backend.encode(["q"])


def test_get_embedding_backend_prefers_http(monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    set_embedding_backend(None)
    monkeypatch.setenv("EMBEDDING_SERVICE_URL", "http://processor-embedding:8081")
    get_settings.cache_clear()
    try:
        backend = get_embedding_backend()
        assert isinstance(backend, HttpEmbeddingBackend)
    finally:
        set_embedding_backend(None)
        get_settings.cache_clear()
        monkeypatch.delenv("EMBEDDING_SERVICE_URL", raising=False)
