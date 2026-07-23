"""LLM extraction worker: processing:llm consumer.

Run with:  python -m newscrawl_processor.run_llm_worker [--once] [--batch-size N]
"""

import argparse
import asyncio
import os
import socket
import time
import uuid

from newscrawl_api.config import get_settings
from newscrawl_api.coordination import GracefulShutdown, Heartbeat, StreamQueue
from newscrawl_api.coordination.queues import QueueMessage
from newscrawl_api.db import dispose_engine, session_scope
from newscrawl_api.models import Article
from newscrawl_api.observability import configure_logging, get_logger
from newscrawl_contracts.enums import WorkerType
from newscrawl_contracts.messages import LlmExtractionMessage
from newscrawl_contracts.streams import GROUP_PROCESSORS, STREAM_LLM
from redis.asyncio import Redis

from newscrawl_processor.llm import ExtractionFailedError, LlmExtractor, build_provider_chain
from newscrawl_processor.llm.extractor import LlmUsage
from newscrawl_processor.llm.persist import apply_analysis, record_failure
from newscrawl_processor.metrics import (
    LLM_COST,
    LLM_TOKENS,
    MESSAGES,
    start_metrics_server,
    track_duration,
)

log = get_logger()


class LlmWorker:
    def __init__(self, queue: StreamQueue, extractor: LlmExtractor, batch_size: int = 4) -> None:
        self.queue = queue
        self.extractor = extractor
        self.batch_size = batch_size

    async def process_batch(self) -> int:
        await self.queue.pump_delayed()
        messages = await self.queue.claim_stale(STREAM_LLM, count=self.batch_size)
        messages += await self.queue.consume(
            STREAM_LLM, count=self.batch_size - len(messages) or 1, block_ms=2000
        )
        for message in messages:
            await self.process_message(message)
        return len(messages)

    async def process_message(self, message: QueueMessage) -> None:
        try:
            payload = LlmExtractionMessage.model_validate(message.payload)
        except ValueError as exc:
            MESSAGES.labels(worker="llm", outcome="malformed").inc()
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

        started = time.monotonic()
        with track_duration("llm"):
            async with session_scope() as db:
                article = await db.get(Article, payload.article_id)
                if article is None:
                    log.warning("llm_article_missing", article_id=str(payload.article_id))
                    MESSAGES.labels(worker="llm", outcome="missing").inc()
                    await self.queue.ack(message)
                    return

                try:
                    analysis, usage = await self.extractor.analyze(
                        title=article.title, body=article.body, language=payload.language
                    )
                except ExtractionFailedError as exc:
                    latency_ms = int((time.monotonic() - started) * 1000)
                    await record_failure(
                        db, article, exc.usage, error=str(exc), latency_ms=latency_ms
                    )
                    MESSAGES.labels(worker="llm", outcome="failed").inc()
                    self._track_usage(exc.usage)
                    await self.queue.retry(message, error=str(exc))
                    return

                latency_ms = int((time.monotonic() - started) * 1000)
                await apply_analysis(db, article, analysis, usage, latency_ms=latency_ms)

        MESSAGES.labels(worker="llm", outcome="analyzed").inc()
        self._track_usage(usage)
        await self.queue.ack(message)

        log.info(
            "article_analyzed",
            article_id=str(payload.article_id),
            provider=usage.provider,
            tokens=usage.total_tokens,
            cost_usd=round(usage.cost_usd, 6),
            latency_ms=latency_ms,
        )

    @staticmethod
    def _track_usage(usage: LlmUsage) -> None:
        provider = usage.provider or "unknown"
        LLM_TOKENS.labels(provider=provider, kind="prompt").inc(usage.prompt_tokens)
        LLM_TOKENS.labels(provider=provider, kind="completion").inc(usage.completion_tokens)
        LLM_COST.labels(provider=provider).inc(usage.cost_usd)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="NewsCrawl LLM extraction worker")
    parser.add_argument("--once", action="store_true", help="drain once, then exit")
    parser.add_argument("--batch-size", type=int, default=4)
    return parser.parse_args()


async def run(once: bool, batch_size: int) -> None:
    settings = get_settings()
    worker_id = f"processor-llm-{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:6]}"
    redis: Redis = Redis.from_url(settings.redis_url, decode_responses=True)

    queue = StreamQueue(redis, group=GROUP_PROCESSORS, consumer=worker_id)
    await queue.ensure_group(STREAM_LLM)

    providers = build_provider_chain(settings)
    extractor = LlmExtractor(providers, max_retries=settings.llm_max_retries)

    shutdown = GracefulShutdown()
    shutdown.install()
    heartbeat = Heartbeat(redis, worker_id=worker_id, worker_type=WorkerType.PROCESSOR)
    await heartbeat.start()

    worker = LlmWorker(queue, extractor, batch_size=batch_size)
    metrics_port = start_metrics_server("llm")
    log.info(
        "llm_worker_started",
        worker_id=worker_id,
        providers=[p.name for p in providers],
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
        for provider in providers:
            await provider.aclose()
        await redis.aclose()
        await dispose_engine()
        log.info("llm_worker_stopped", worker_id=worker_id)


def main() -> None:
    settings = get_settings()
    configure_logging("processor-llm", settings.log_level)
    args = parse_args()
    asyncio.run(run(once=args.once, batch_size=args.batch_size))


if __name__ == "__main__":
    main()
