"""Article retention scheduler.

Deletes articles older than ARTICLE_RETENTION_HOURS (default 24) on a fixed
interval of ARTICLE_RETENTION_INTERVAL_MINUTES (default 5).

Run with:  python -m newscrawl_processor.run_retention_worker [--once]
"""

from __future__ import annotations

import argparse
import asyncio
import os
import socket
import uuid

from newscrawl_api.config import get_settings
from newscrawl_api.coordination import GracefulShutdown, Heartbeat
from newscrawl_api.db import dispose_engine, session_scope
from newscrawl_api.observability import configure_logging, get_logger
from newscrawl_contracts.enums import WorkerType

from newscrawl_processor.metrics import MESSAGES, start_metrics_server
from newscrawl_processor.retention import purge_expired_articles

log = get_logger()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="NewsCrawl article retention worker")
    parser.add_argument(
        "--once",
        action="store_true",
        help="run a single purge cycle, then exit",
    )
    return parser.parse_args()


async def run_cycle() -> int:
    settings = get_settings()
    async with session_scope() as db:
        deleted = await purge_expired_articles(db, settings)
    MESSAGES.labels(worker="retention", outcome="deleted" if deleted else "noop").inc()
    log.info(
        "retention_cycle_complete",
        deleted=deleted,
        retention_hours=settings.article_retention_hours,
    )
    return deleted


def _interval_seconds(settings) -> int:
    if settings.article_retention_interval_minutes > 0:
        return max(60, int(settings.article_retention_interval_minutes * 60))
    return max(60, int(settings.article_retention_interval_hours * 3600))


async def run(*, once: bool) -> None:
    settings = get_settings()
    worker_id = f"processor-retention-{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:6]}"
    from redis.asyncio import Redis

    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    shutdown = GracefulShutdown()
    shutdown.install()
    heartbeat = Heartbeat(redis, worker_id=worker_id, worker_type=WorkerType.PROCESSOR)
    await heartbeat.start()

    metrics_port = start_metrics_server("retention")
    interval_seconds = _interval_seconds(settings)
    log.info(
        "retention_worker_started",
        worker_id=worker_id,
        retention_hours=settings.article_retention_hours,
        interval_seconds=interval_seconds,
        once=once,
        metrics_port=metrics_port,
    )

    try:
        while not await shutdown.wait(timeout=0):
            try:
                deleted = await run_cycle()
            except Exception:
                log.exception("retention_cycle_failed")
                MESSAGES.labels(worker="retention", outcome="error").inc()
                deleted = 0
            if once:
                break
            # Keep draining until the window is clean, then rest.
            if deleted > 0:
                continue
            remaining = float(interval_seconds)
            while remaining > 0 and not await shutdown.wait(timeout=min(30.0, remaining)):
                remaining -= 30.0
            if await shutdown.wait(timeout=0):
                break
    finally:
        await heartbeat.stop()
        await redis.aclose()
        await dispose_engine()
        log.info("retention_worker_stopped", worker_id=worker_id)


def main() -> None:
    settings = get_settings()
    configure_logging("processor-retention", settings.log_level)
    args = parse_args()
    asyncio.run(run(once=args.once))


if __name__ == "__main__":
    main()
