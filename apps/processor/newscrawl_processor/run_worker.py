"""Cleaning worker: processing:cleaning consumer.

Consumes RawPageMessage entries produced by the crawl plane, cleans and
validates the extraction, persists articles with version tracking, and fans
out to the LLM and embedding stages for new/changed articles.

Run with:  python -m newscrawl_processor.run_worker [--once] [--batch-size N]
"""

import argparse
import asyncio
import os
import socket
from datetime import UTC, datetime

from newscrawl_api.config import get_settings
from newscrawl_api.coordination import GracefulShutdown, Heartbeat, StreamQueue
from newscrawl_api.coordination.queues import QueueMessage
from newscrawl_api.db import dispose_engine, session_scope
from newscrawl_api.models import ProcessingJob
from newscrawl_api.observability import configure_logging, get_logger
from newscrawl_contracts import RawPageMessage
from newscrawl_contracts.enums import ProcessingStage, ProcessingStatus, WorkerType
from newscrawl_contracts.messages import EmbeddingMessage, LlmExtractionMessage
from newscrawl_contracts.streams import (
    GROUP_PROCESSORS,
    STREAM_CLEANING,
    STREAM_EMBEDDING,
    STREAM_LLM,
)
from redis.asyncio import Redis

from newscrawl_processor.articles import ArticleService, PersistResult
from newscrawl_processor.cleaning import UnusableArticleError, clean_extracted
from newscrawl_processor.metrics import MESSAGES, start_metrics_server, track_duration

log = get_logger()


class CleaningWorker:
    def __init__(self, queue: StreamQueue, *, batch_size: int = 10) -> None:
        self.queue = queue
        self.batch_size = batch_size
        self.articles = ArticleService()

    async def process_batch(self) -> int:
        """Consume and process one batch; returns number of messages handled."""
        await self.queue.pump_delayed()
        messages = await self.queue.claim_stale(STREAM_CLEANING, count=self.batch_size)
        messages += await self.queue.consume(
            STREAM_CLEANING, count=self.batch_size - len(messages) or 1, block_ms=2000
        )
        for message in messages:
            await self.process_message(message)
        return len(messages)

    async def process_message(self, message: QueueMessage) -> None:
        try:
            page = RawPageMessage.model_validate(message.payload)
        except ValueError as exc:
            # Malformed payloads can never succeed — straight to dead-letter.
            log.warning("malformed_message", message_id=message.message_id, error=str(exc))
            MESSAGES.labels(worker="cleaning", outcome="malformed").inc()
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
            with track_duration("cleaning"):
                result = await self.handle_page(page, message_id=message.message_id)
        except UnusableArticleError as exc:
            # Content-quality failure — retrying won't grow the article.
            log.warning("unusable_article", url=page.normalized_url, error=str(exc))
            MESSAGES.labels(worker="cleaning", outcome="unusable").inc()
            await self._record_job(
                page, message.message_id, ProcessingStatus.FAILED, error=str(exc)
            )
            await self.queue.ack(message)
            return
        except Exception as exc:
            log.exception("cleaning_failed", url=page.normalized_url)
            retried = await self.queue.retry(message, error=f"{type(exc).__name__}: {exc}")
            MESSAGES.labels(
                worker="cleaning", outcome="retried" if retried else "dead_letter"
            ).inc()
            if not retried:
                await self._record_job(
                    page, message.message_id, ProcessingStatus.DEAD_LETTER, error=str(exc)
                )
            return

        MESSAGES.labels(worker="cleaning", outcome=result.action).inc()
        await self.queue.ack(message)
        log.info(
            "page_processed",
            url=page.normalized_url,
            action=result.action,
            article_id=str(result.article_id) if result.article_id else None,
            version=result.version,
        )

    async def handle_page(self, page: RawPageMessage, *, message_id: str) -> PersistResult:
        cleaned = clean_extracted(dict(page.extracted))
        async with session_scope() as db:
            result = await self.articles.persist(
                db,
                cleaned,
                source_id=page.source_id,
                canonical_url=page.canonical_url or page.normalized_url,
                url_id=page.url_id,
                raw_html_location=page.raw_html_location,
            )
            db.add(
                ProcessingJob(
                    stage=ProcessingStage.CLEANING,
                    status=ProcessingStatus.COMPLETED,
                    article_id=result.article_id,
                    url_id=page.url_id,
                    message_id=message_id,
                    attempts=1,
                    started_at=datetime.now(UTC),
                    completed_at=datetime.now(UTC),
                )
            )

        # Fan out only when there is new content to analyze.
        if result.action in ("created", "updated") and result.article_id is not None:
            llm_message = LlmExtractionMessage(
                article_id=result.article_id, language=cleaned.language.value
            )
            embed_message = EmbeddingMessage(article_id=result.article_id)
            await self.queue.publish(
                STREAM_LLM,
                llm_message.model_dump(mode="json"),
            )
            await self.queue.publish(
                STREAM_EMBEDDING,
                embed_message.model_dump(mode="json"),
            )
        return result

    async def _record_job(
        self,
        page: RawPageMessage,
        message_id: str,
        status: ProcessingStatus,
        *,
        error: str,
    ) -> None:
        async with session_scope() as db:
            db.add(
                ProcessingJob(
                    stage=ProcessingStage.CLEANING,
                    status=status,
                    url_id=page.url_id,
                    message_id=message_id,
                    attempts=1,
                    last_error=error[:2000],
                    completed_at=datetime.now(UTC),
                )
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="NewsCrawl cleaning worker")
    parser.add_argument("--once", action="store_true", help="drain once, then exit")
    parser.add_argument("--batch-size", type=int, default=10)
    return parser.parse_args()


async def run(once: bool, batch_size: int) -> None:
    settings = get_settings()
    worker_id = f"processor-cleaning-{socket.gethostname()}-{os.getpid()}"
    redis: Redis = Redis.from_url(settings.redis_url, decode_responses=True)

    queue = StreamQueue(redis, group=GROUP_PROCESSORS, consumer=worker_id)
    for stream in (STREAM_CLEANING, STREAM_LLM, STREAM_EMBEDDING):
        await queue.ensure_group(stream)

    shutdown = GracefulShutdown()
    shutdown.install()
    heartbeat = Heartbeat(redis, worker_id=worker_id, worker_type=WorkerType.PROCESSOR)
    await heartbeat.start()

    worker = CleaningWorker(queue, batch_size=batch_size)
    metrics_port = start_metrics_server("cleaning")
    log.info("cleaning_worker_started", worker_id=worker_id, once=once, metrics_port=metrics_port)
    try:
        while not await shutdown.wait(timeout=0):
            handled = await worker.process_batch()
            if once and handled == 0:
                break
    finally:
        await heartbeat.stop()
        await redis.aclose()
        await dispose_engine()
        log.info("cleaning_worker_stopped", worker_id=worker_id)


def main() -> None:
    settings = get_settings()
    configure_logging("processor", settings.log_level)
    args = parse_args()
    asyncio.run(run(once=args.once, batch_size=args.batch_size))


if __name__ == "__main__":
    main()
