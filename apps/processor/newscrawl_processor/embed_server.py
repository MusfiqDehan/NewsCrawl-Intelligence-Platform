"""Lightweight HTTP encode server for the embedding worker.

The API image does not ship torch/sentence-transformers (too heavy for the
control plane). Query-time semantic search encodes via this internal endpoint
so the already-loaded BGE-M3 singleton is reused — one model copy on the host.
"""

from __future__ import annotations

import asyncio
from typing import Any

from newscrawl_api.observability import get_logger
from newscrawl_api.services.embedding_backend import EmbeddingBackend
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

log = get_logger()


def build_embed_app(backend: EmbeddingBackend) -> Starlette:
    """Starlette app exposing /healthz and POST /v1/encode."""

    async def healthz(_request: Request) -> JSONResponse:
        return JSONResponse(
            {
                "status": "ok",
                "model": backend.model_name,
                "dimension": backend.dimension,
            }
        )

    async def encode(request: Request) -> JSONResponse:
        try:
            payload: dict[str, Any] = await request.json()
        except Exception:
            return JSONResponse({"detail": "invalid JSON body"}, status_code=400)
        texts = payload.get("texts")
        if not isinstance(texts, list) or not texts or not all(isinstance(t, str) for t in texts):
            return JSONResponse(
                {"detail": "body.texts must be a non-empty list of strings"},
                status_code=400,
            )
        # Prefer query latency: do not serialize behind the stream worker's
        # long article encodes (CPU hosts still share the model weights).
        vectors = await asyncio.to_thread(backend.encode, texts)
        return JSONResponse(
            {
                "vectors": vectors,
                "model": backend.model_name,
                "dimension": backend.dimension,
            }
        )

    return Starlette(
        routes=[
            Route("/healthz", healthz),
            Route("/v1/encode", encode, methods=["POST"]),
        ]
    )


async def start_embed_server(
    backend: EmbeddingBackend,
    *,
    host: str = "0.0.0.0",
    port: int = 8081,
) -> asyncio.Task[None]:
    """Serve encode HTTP in-process; returns the background uvicorn task."""
    import uvicorn

    app = build_embed_app(backend)
    config = uvicorn.Config(app, host=host, port=port, log_level="warning", access_log=False)
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve(), name="embed-encode-server")
    # Give the bind a moment; failures surface via the task.
    await asyncio.sleep(0.2)
    if task.done() and (exc := task.exception()):
        raise RuntimeError(f"embed encode server failed to start: {exc}") from exc
    log.info("embed_encode_server_started", host=host, port=port, model=backend.model_name)
    return task
