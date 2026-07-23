"""Embedding worker: processing:embedding consumer (BGE-M3).

Run with:  python -m newscrawl_processor.run_embedding_worker [--once] [--batch-size N]
"""

import argparse
import asyncio
import os
import socket
import uuid

from newscrawl_api.config import get_settings
from newscrawl_api.coordination import GracefulShutdown, Heartbeat, StreamQueue
from newscrawl_api.coordination.queues import QueueMessage
from newscrawl_api.db import dispose_engine, session_scope
from newscrawl_api.models import Article
from newscrawl_api.observability import configure_logging, get_logger
from newscrawl_api.services.embedding_backend import get_embedding_backend
from newscrawl_contracts.enums import WorkerType
from newscrawl_contracts.messages import EmbeddingMessage
from newscrawl_contracts.streams import GROUP_PROCESSORS, STREAM_EMBEDDING
from redis.asyncio import Redis

from newscrawl_processor.embeddings import EmbeddingService
from newscrawl_processor.metrics import (
    DUPLICATES,
    EMBEDDINGS,
    MESSAGES,
    start_metrics_server,
    track_duration,
)

log = get_logger()


class EmbeddingWorker:
    def __init__(self, queue: StreamQueue, service: EmbeddingService, batch_size: int = 8) -> None:
        self.queue = queue
        self.service = service
        self.batch_size = batch_size

    async def process_batch(self) -> int:
        await self.queue.pump_delayed()
        messages = await self.queue.claim_stale(STREAM_EMBEDDING, count=self.batch_size)
        messages += await self.queue.consume(
            STREAM_EMBEDDING, count=self.batch_size - len(messages) or 1, block_ms=2000
        )
        for message in messages:
            await self.process_message(message)
        return len(messages)

    async def process_message(self, message: QueueMessage) -> None:
        try:
            payload = EmbeddingMessage.model_validate(message.payload)
        except ValueError as exc:
            MESSAGES.labels(worker="embedding", outcome="malformed").inc()
            await self.queue.retry(
                QueueMessage(
                    stream=message.stream,
                    message_id=message.message_id,
                    payload=message.payload,
                    attempt=self.queue.max_attempts,
                ),
                error=f"validation: {exc}",
            )
            return

        try:
            with track_duration("embedding"):
                async with session_scope() as db:
                    article = await db.get(Article, payload.article_id)
                    if article is None:
                        log.warning("embedding_article_missing", article_id=str(payload.article_id))
                        MESSAGES.labels(worker="embedding", outcome="missing").inc()
                        await self.queue.ack(message)
                        return
                    result = await self.service.embed_article(db, article, payload.kinds)
        except Exception as exc:
            log.exception("embedding_failed", article_id=str(payload.article_id))
            MESSAGES.labels(worker="embedding", outcome="failed").inc()
            await self.queue.retry(message, error=f"{type(exc).__name__}: {exc}")
            return

        MESSAGES.labels(worker="embedding", outcome="embedded").inc()
        for kind in result.kinds:
            EMBEDDINGS.labels(kind=kind.value).inc()
        if result.duplicate_of is not None:
            DUPLICATES.labels(method="semantic").inc()
        await self.queue.ack(message)
        log.info(
            "article_embedded",
            article_id=str(payload.article_id),
            kinds=[k.value for k in result.kinds],
            duplicate_of=str(result.duplicate_of) if result.duplicate_of else None,
            semantic_similarity=result.semantic_similarity,
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="NewsCrawl embedding worker")
    parser.add_argument("--once", action="store_true", help="drain once, then exit")
    parser.add_argument("--batch-size", type=int, default=8)
    return parser.parse_args()


async def run(once: bool, batch_size: int) -> None:
    settings = get_settings()
    worker_id = f"processor-embed-{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:6]}"
    redis: Redis = Redis.from_url(settings.redis_url, decode_responses=True)

    queue = StreamQueue(redis, group=GROUP_PROCESSORS, consumer=worker_id)
    await queue.ensure_group(STREAM_EMBEDDING)

    log.info("loading_embedding_model", model=settings.embedding_model)
    backend = get_embedding_backend()
    service = EmbeddingService(backend, version=settings.embedding_version)

    shutdown = GracefulShutdown()
    shutdown.install()
    heartbeat = Heartbeat(redis, worker_id=worker_id, worker_type=WorkerType.PROCESSOR)
    await heartbeat.start()

    worker = EmbeddingWorker(queue, service, batch_size=batch_size)
    metrics_port = start_metrics_server("embedding")
    log.info(
        "embedding_worker_started",
        worker_id=worker_id,
        model=backend.model_name,
        once=once,
        metrics_port=metrics_port,
    )
    try:
        while not await shutdown.wait(timeout=0):
            handled = await worker.process_batch()
            if once and handled == 0:
                break
    finally:
        await heartbeat.stop()
        await redis.aclose()
        await dispose_engine()
        log.info("embedding_worker_stopped", worker_id=worker_id)


def main() -> None:
    settings = get_settings()
    configure_logging("processor-embedding", settings.log_level)
    args = parse_args()
    asyncio.run(run(once=args.once, batch_size=args.batch_size))


if __name__ == "__main__":
    main()
