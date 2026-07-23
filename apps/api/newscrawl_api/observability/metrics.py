"""Prometheus metrics for the API plane.

Exposes:
- HTTP request counters/latency via ASGI middleware (labelled by route template
  so cardinality stays bounded).
- Platform gauges (queue depths, frontier status counts, live workers) that a
  background task refreshes periodically; /metrics then serves point-in-time
  values without doing I/O per scrape.
"""

import asyncio
import time
from typing import TYPE_CHECKING

from prometheus_client import Counter, Gauge, Histogram
from sqlalchemy import func, select
from starlette.types import ASGIApp, Message, Receive, Scope, Send

if TYPE_CHECKING:
    from redis.asyncio import Redis

HTTP_REQUESTS = Counter(
    "newscrawl_http_requests_total",
    "HTTP requests handled by the API",
    ["method", "path", "status"],
)
HTTP_DURATION = Histogram(
    "newscrawl_http_request_duration_seconds",
    "HTTP request latency",
    ["method", "path"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

QUEUE_DEPTH = Gauge(
    "newscrawl_queue_depth", "Redis Stream backlog per processing stage", ["stream"]
)
DELAYED_JOBS = Gauge("newscrawl_delayed_jobs", "Jobs waiting in the delayed/retry sorted set")
DEAD_LETTER = Gauge("newscrawl_dead_letter_messages", "Messages parked in the dead-letter stream")
FRONTIER_URLS = Gauge("newscrawl_frontier_urls", "URL frontier rows grouped by status", ["status"])
WORKERS_ALIVE = Gauge("newscrawl_workers_alive", "Workers with a recent heartbeat", ["worker_type"])
ARTICLES_TOTAL = Gauge("newscrawl_articles_total", "Total articles stored")


class MetricsMiddleware:
    """Pure-ASGI middleware: cheaper than BaseHTTPMiddleware, streaming-safe."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        method = scope["method"]
        started = time.perf_counter()
        status_code = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            # Route template is set by the router during dispatch; unmatched
            # paths (404 scans) all collapse into one label value.
            route = scope.get("route")
            path = getattr(route, "path", "<unmatched>")
            HTTP_REQUESTS.labels(method=method, path=path, status=str(status_code)).inc()
            HTTP_DURATION.labels(method=method, path=path).observe(time.perf_counter() - started)


async def refresh_platform_gauges(redis: Redis) -> None:
    """Refresh queue/frontier/worker gauges once. Errors bubble to the caller."""
    from newscrawl_contracts.enums import WorkerType
    from newscrawl_contracts.streams import (
        DELAYED_JOBS_KEY,
        STREAM_CLEANING,
        STREAM_DEAD_LETTER,
        STREAM_EMBEDDING,
        STREAM_LLM,
    )

    from newscrawl_api.coordination import Heartbeat
    from newscrawl_api.db import session_scope
    from newscrawl_api.models import Article, CrawlUrl

    for stream in (STREAM_CLEANING, STREAM_LLM, STREAM_EMBEDDING):
        QUEUE_DEPTH.labels(stream=stream).set(int(await redis.xlen(stream)))
    DELAYED_JOBS.set(int(await redis.zcard(DELAYED_JOBS_KEY)))
    DEAD_LETTER.set(int(await redis.xlen(STREAM_DEAD_LETTER)))

    alive_by_type = dict.fromkeys(WorkerType, 0)
    for worker in await Heartbeat.list_workers(redis):
        if worker.age_seconds < 60:
            alive_by_type[worker.worker_type] += 1
    for worker_type, count in alive_by_type.items():
        WORKERS_ALIVE.labels(worker_type=worker_type.value).set(count)

    async with session_scope() as db:
        rows = (
            await db.execute(select(CrawlUrl.status, func.count()).group_by(CrawlUrl.status))
        ).all()
        for status, count in rows:
            FRONTIER_URLS.labels(status=status.value).set(count)
        ARTICLES_TOTAL.set(await db.scalar(select(func.count(Article.id))) or 0)


async def platform_gauges_loop(redis: Redis, interval_seconds: float = 15.0) -> None:
    """Background task started from the app lifespan."""
    from newscrawl_api.observability import get_logger

    log = get_logger("metrics")
    while True:
        try:
            await refresh_platform_gauges(redis)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("gauge_refresh_failed", error=repr(exc))
        await asyncio.sleep(interval_seconds)
