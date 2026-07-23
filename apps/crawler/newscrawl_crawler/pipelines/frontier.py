"""Frontier + queue updates for every fetched page.

Responsibilities (in order):
  1. feed newly discovered links back into the frontier
  2. record the crawl attempt (append-only audit log)
  3. mark the URL outcome (success / not-modified) with incremental-crawl state
  4. enqueue changed articles onto the processing:cleaning stream
"""

from typing import Any

from newscrawl_api.config import get_settings
from newscrawl_api.db import session_scope
from newscrawl_api.models import CrawlAttempt
from newscrawl_api.services.crawl_jobs import CrawlJobService
from newscrawl_api.services.frontier import Frontier
from newscrawl_contracts import RawPageMessage
from newscrawl_contracts.enums import AttemptOutcome, FetchMethod, UrlType
from newscrawl_contracts.streams import STREAM_CLEANING
from newscrawl_crawler_utils import content_hash
from redis.asyncio import Redis
from scrapy import Spider
from scrapy.exceptions import DropItem

from newscrawl_crawler.items import PageItem
from newscrawl_crawler.spiders.base import NewsSpiderBase, frontier_discoveries


class FrontierUpdatePipeline:
    def __init__(self) -> None:
        self.frontier = Frontier()
        self.redis: Redis | None = None

    def open_spider(self, spider: Spider) -> None:
        settings = get_settings()
        self.frontier = Frontier(
            lease_seconds=settings.frontier_lease_seconds,
            max_retries=settings.frontier_max_retries,
        )
        self.redis = Redis.from_url(settings.redis_url, decode_responses=True)

    async def close_spider(self, spider: Spider) -> None:
        if self.redis is not None:
            await self.redis.aclose()

    async def process_item(self, item: PageItem, spider: Spider) -> PageItem:
        if not isinstance(spider, NewsSpiderBase):
            return item

        stats = spider.crawler.stats
        assert stats is not None  # always set once the crawler is running

        async with session_scope() as db:
            # 1. Discovered links → frontier
            if item.discovered:
                added = await self.frontier.add_urls(
                    db,
                    spider.source,
                    frontier_discoveries(item.discovered, item.normalized_url),
                    crawl_job_id=item.crawl_job_id,
                )
                stats.inc_value("newscrawl/urls_discovered", added)

            # 2. Attempt audit row
            db.add(
                CrawlAttempt(
                    url_id=item.url_id,
                    crawl_job_id=item.crawl_job_id,
                    worker_id=spider.worker_id,
                    fetch_method=FetchMethod(item.fetch_method),
                    outcome=(
                        AttemptOutcome.NOT_MODIFIED if item.not_modified else AttemptOutcome.SUCCESS
                    ),
                    http_status=item.http_status,
                    duration_ms=item.duration_ms,
                    bytes_downloaded=len(item.raw_html) if item.raw_html else None,
                )
            )

            # 3. URL outcome
            if item.not_modified:
                await self.frontier.mark_not_modified(db, item.url_id)
                stats.inc_value("newscrawl/pages_unchanged")
                item.content_changed = False
                if item.crawl_job_id:
                    await CrawlJobService.increment_counters(
                        db,
                        item.crawl_job_id,
                        pages_requested=1,
                        pages_successful=1,
                        pages_unchanged=1,
                    )
                return item

            digest: str | None = None
            extracted: dict[str, Any] | None = item.extracted
            if item.url_type == UrlType.ARTICLE and extracted:
                digest = content_hash(
                    title=extracted.get("title"),
                    author=extracted.get("author"),
                    published_at=extracted.get("published_at"),
                    body=extracted.get("body"),
                )
            changed = await self.frontier.mark_success(
                db,
                item.url_id,
                http_status=item.http_status,
                content_hash=digest,
                etag=item.etag,
                last_modified=item.last_modified,
                canonical_url=item.canonical_url,
            )
            item.content_hash = digest
            item.content_changed = changed

            if item.crawl_job_id:
                await CrawlJobService.increment_counters(
                    db,
                    item.crawl_job_id,
                    pages_requested=1,
                    pages_successful=1,
                    pages_changed=1 if changed else 0,
                    pages_unchanged=0 if changed else 1,
                )

        # 4. Enqueue changed, extractable articles for processing
        if item.url_type == UrlType.ARTICLE:
            if not extracted or not extracted.get("title") or not extracted.get("body"):
                stats.inc_value("newscrawl/extraction_failed")
                raise DropItem(f"No extractable article content: {item.normalized_url}")
            if not changed:
                stats.inc_value("newscrawl/pages_unchanged")
                return item
            if not item.raw_html_location:
                raise DropItem(f"Article missing raw_html_location: {item.normalized_url}")

            message = RawPageMessage(
                url_id=item.url_id,
                source_id=item.source_id,
                source_slug=item.source_slug,
                crawl_job_id=item.crawl_job_id,
                normalized_url=item.normalized_url,
                canonical_url=item.canonical_url,
                raw_html_location=item.raw_html_location,
                http_status=item.http_status,
                fetched_at=item.fetched_at,
                extracted=extracted,
            )
            assert self.redis is not None
            await self.redis.xadd(STREAM_CLEANING, {"payload": message.model_dump_json()})
            stats.inc_value("newscrawl/articles_enqueued")

        return item
