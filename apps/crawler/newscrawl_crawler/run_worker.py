"""Crawl worker: a long-running process that repeatedly runs frontier-driven
spider passes for enabled sources.

Run with:  python -m newscrawl_crawler.run_worker [--source SLUG] [--once]

Flow per pass:
  1. reap expired leases (crash recovery)
  2. load enabled sources (fresh config snapshot each pass)
  3. run one spider pass per source (spider claims URLs until none are due)
  4. sleep, repeat

Scrapy's Twisted reactor runs on top of the asyncio loop, so asyncpg/redis
and Scrapy crawls coexist in a single event loop.
"""

import argparse
import asyncio
import os
import sys
from typing import TYPE_CHECKING, Any, cast

from newscrawl_api.config import get_settings

if TYPE_CHECKING:
    from newscrawl_contracts import SourceConfig
from newscrawl_api.observability import configure_logging, get_logger

# Make the settings module discoverable regardless of the working directory.
os.environ.setdefault("SCRAPY_SETTINGS_MODULE", "newscrawl_crawler.settings")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="NewsCrawl crawl worker")
    parser.add_argument("--source", help="only crawl this source slug", default=None)
    parser.add_argument("--job", help="run this crawl job id to completion", default=None)
    parser.add_argument("--once", action="store_true", help="run a single pass and exit")
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--interval", type=float, default=15.0, help="seconds between passes")
    parser.add_argument(
        "--max-pages",
        type=int,
        # Cap each source pass so one fat frontier (e.g. Prothom Alo) cannot
        # monopolize the only crawler forever. 0 = unlimited (ops override).
        default=25,
        help="cap fetched pages per spider pass (0 = unlimited)",
    )
    return parser.parse_args(argv)


async def _fair_source_order(sources: list[Any]) -> list[Any]:
    """Prefer starved sources (few articles, pending discovery hubs) first."""
    from newscrawl_api.db import session_scope
    from newscrawl_api.models import Article, CrawlUrl
    from newscrawl_contracts.enums import UrlStatus, UrlType
    from sqlalchemy import func, select

    if len(sources) <= 1:
        return sources

    ids = [s.id for s in sources]
    async with session_scope() as db:
        art_rows = (
            await db.execute(
                select(Article.source_id, func.count())
                .where(Article.source_id.in_(ids))
                .group_by(Article.source_id)
            )
        ).all()
        art_counts = {row[0]: int(row[1]) for row in art_rows}

        hub_types = (
            UrlType.HOMEPAGE,
            UrlType.SECTION,
            UrlType.RSS,
            UrlType.SITEMAP,
        )
        hub_rows = (
            await db.execute(
                select(CrawlUrl.source_id, func.count())
                .where(
                    CrawlUrl.source_id.in_(ids),
                    CrawlUrl.status.in_([UrlStatus.QUEUED, UrlStatus.RETRY_PENDING]),
                    CrawlUrl.url_type.in_(hub_types),
                )
                .group_by(CrawlUrl.source_id)
            )
        ).all()
        hub_pending = {row[0]: int(row[1]) for row in hub_rows}

        due_rows = (
            await db.execute(
                select(CrawlUrl.source_id, func.count())
                .where(
                    CrawlUrl.source_id.in_(ids),
                    CrawlUrl.status.in_([UrlStatus.QUEUED, UrlStatus.RETRY_PENDING]),
                )
                .group_by(CrawlUrl.source_id)
            )
        ).all()
        due_counts = {row[0]: int(row[1]) for row in due_rows}

    def sort_key(source: Any) -> tuple[int, int, int, str]:
        # Lower tuple sorts first: fewest articles, then hubs waiting, then due work.
        articles = art_counts.get(source.id, 0)
        hubs = hub_pending.get(source.id, 0)
        due = due_counts.get(source.id, 0)
        return (articles, -hubs, -due, source.slug)

    return sorted(sources, key=sort_key)


async def _load_sources(slug: str | None) -> list[SourceConfig]:
    from newscrawl_api.db import session_scope
    from newscrawl_api.models import Source
    from newscrawl_contracts import SourceConfig
    from sqlalchemy import select

    async with session_scope() as db:
        query = select(Source).where(Source.enabled.is_(True), Source.crawl_enabled.is_(True))
        if slug:
            query = select(Source).where(Source.slug == slug)
        sources = (await db.scalars(query)).all()
        return [SourceConfig.model_validate(s) for s in sources]


async def _reap_leases() -> int:
    from newscrawl_api.db import session_scope
    from newscrawl_api.services.frontier import Frontier

    async with session_scope() as db:
        return await Frontier().reap_expired_leases(db)


async def _load_job(job_id: str) -> tuple[SourceConfig, str]:
    """Load a crawl job, mark it running, and return its source snapshot."""
    import uuid

    from newscrawl_api.db import session_scope
    from newscrawl_api.models import CrawlJob, Source
    from newscrawl_api.services.crawl_jobs import CrawlJobService
    from newscrawl_contracts import SourceConfig
    from newscrawl_contracts.enums import CrawlJobStatus

    async with session_scope() as db:
        job = await db.get(CrawlJob, uuid.UUID(job_id))
        if job is None:
            raise SystemExit(f"crawl job {job_id} not found")
        if job.status not in (CrawlJobStatus.QUEUED, CrawlJobStatus.RUNNING):
            raise SystemExit(f"crawl job {job_id} is '{job.status}', expected queued/running")
        source = await db.get(Source, job.source_id)
        assert source is not None
        if job.status == CrawlJobStatus.QUEUED:
            await CrawlJobService().transition(db, job, CrawlJobStatus.RUNNING)
        return SourceConfig.model_validate(source), str(job.id)


async def _finish_job(job_id: str) -> None:
    """Mark a job completed once its frontier slice is exhausted."""
    import uuid

    from newscrawl_api.db import session_scope
    from newscrawl_api.models import CrawlJob
    from newscrawl_api.services.crawl_jobs import CrawlJobService, InvalidTransitionError
    from newscrawl_contracts.enums import CrawlJobStatus

    async with session_scope() as db:
        job = await db.get(CrawlJob, uuid.UUID(job_id))
        if job is None:
            return
        try:
            await CrawlJobService().transition(db, job, CrawlJobStatus.COMPLETED)
        except InvalidTransitionError:
            pass  # paused/cancelled while we were crawling — leave as-is


async def orchestrate(args: argparse.Namespace) -> None:
    from newscrawl_api.coordination import (
        ControlAction,
        ControlListener,
        ControlSignal,
        GracefulShutdown,
        Heartbeat,
    )
    from newscrawl_contracts.enums import WorkerType
    from redis.asyncio import Redis
    from scrapy.crawler import CrawlerRunner
    from scrapy.utils.project import get_project_settings
    from twisted.internet import reactor

    from newscrawl_crawler.registry import spider_for

    log = get_logger("crawl_worker")
    loop = asyncio.get_running_loop()

    redis = Redis.from_url(get_settings().redis_url, decode_responses=True)
    heartbeat = Heartbeat(redis, worker_type=WorkerType.CRAWLER)
    shutdown = GracefulShutdown()
    shutdown.install()

    paused_sources: set[str] = set()

    async def on_control(signal: ControlSignal) -> None:
        if signal.action == ControlAction.SHUTDOWN and signal.worker_id in (
            None,
            heartbeat.worker_id,
        ):
            shutdown.trigger()
        elif signal.action == ControlAction.PAUSE and signal.source_id:
            paused_sources.add(str(signal.source_id))
            log.info("source_paused", source_id=str(signal.source_id))
        elif signal.action in (ControlAction.RESUME, ControlAction.CANCEL) and signal.source_id:
            paused_sources.discard(str(signal.source_id))

    control = ControlListener(redis, on_control)

    async def run_spider_pass(source: Any, crawl_job_id: str | None) -> bool:
        try:
            spider_cls = spider_for(source.slug)
        except KeyError:
            log.warning("no_spider_for_source", slug=source.slug)
            return False

        settings = get_project_settings().copy()
        settings.set("DOWNLOAD_DELAY", source.rate_limit_delay_seconds, priority="cmdline")
        settings.set("CONCURRENT_REQUESTS_PER_DOMAIN", source.max_concurrency, priority="cmdline")
        settings.set("ROBOTSTXT_OBEY", source.robots_policy == "obey", priority="cmdline")
        if args.max_pages:
            settings.set("CLOSESPIDER_PAGECOUNT", args.max_pages, priority="cmdline")
        runner = CrawlerRunner(settings)
        log.info("spider_pass_started", source=source.slug, job=crawl_job_id)
        deferred = runner.crawl(
            spider_cls,
            source_config=source.model_dump_json(),
            batch_size=args.batch_size,
            crawl_job_id=crawl_job_id,
            max_pages=args.max_pages,
        )
        await deferred.asFuture(loop)
        log.info("spider_pass_finished", source=source.slug, job=crawl_job_id)
        return True

    try:
        await heartbeat.start()
        await control.start()

        if args.job:
            # Job mode: run one job's frontier slice to exhaustion, then finish it.
            source, job_id = await _load_job(args.job)
            heartbeat.meta["job_id"] = job_id
            await run_spider_pass(source, job_id)
            await _finish_job(job_id)
            return

        while not shutdown.should_stop:
            reaped = await _reap_leases()
            if reaped:
                log.info("leases_reaped", count=reaped)

            sources = await _load_sources(args.source)
            if not sources:
                log.warning("no_enabled_sources", source_filter=args.source)
            else:
                sources = await _fair_source_order(sources)
                log.info(
                    "pass_source_order",
                    sources=[s.slug for s in sources],
                    max_pages=args.max_pages or None,
                )

            for source in sources:
                # (method call, not the property — mypy narrows properties)
                if await shutdown.wait(timeout=0):
                    break
                if str(source.id) in paused_sources:
                    log.info("skipping_paused_source", source=source.slug)
                    continue
                heartbeat.meta["current_source"] = source.slug
                await run_spider_pass(source, None)

            if args.once:
                break
            # Sleep, but wake immediately on shutdown
            await shutdown.wait(timeout=args.interval)
    finally:
        from newscrawl_api.db import dispose_engine

        await control.stop()
        await heartbeat.stop()
        await redis.aclose()
        await dispose_engine()
        # The reactor module masquerades as an instance; mypy sees unbound methods.
        _reactor = cast(Any, reactor)
        if _reactor.running:
            _reactor.stop()


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    settings = get_settings()
    configure_logging("crawler", settings.log_level)
    log = get_logger("crawl_worker")

    # Install the asyncio reactor on a fresh loop before anything imports
    # twisted.internet.reactor.
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    from twisted.internet import asyncioreactor

    asyncioreactor.install(loop)  # type: ignore[no-untyped-call]
    from twisted.internet import reactor

    def start() -> None:
        task = loop.create_task(orchestrate(args))

        def on_done(t: asyncio.Task[None]) -> None:
            if t.cancelled():
                return
            exc = t.exception()
            if exc is not None:
                log.error("worker_crashed", error=repr(exc))
                sys.exit(1)

        task.add_done_callback(on_done)

    _reactor = cast(Any, reactor)
    _reactor.callWhenRunning(start)
    log.info("crawl_worker_started", once=args.once, source=args.source)
    _reactor.run()


if __name__ == "__main__":
    main()
