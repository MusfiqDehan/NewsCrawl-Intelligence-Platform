"""NewsSpiderBase — frontier-driven spider shared by every source.

The spider does not decide *what* to crawl: it claims leased URLs from the
PostgreSQL frontier, fetches them politely, extracts, and reports outcomes.
Discovery pages (sitemaps, RSS, sections) yield newly discovered links back
into the frontier instead of scheduling requests directly — scheduling is
always the frontier's job, so priorities/dedup/politeness stay centralized.
"""

import json
import re
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import feedparser
import scrapy
from newscrawl_api.db import session_scope
from newscrawl_api.services.frontier import DiscoveredUrl, Frontier
from newscrawl_contracts import SourceConfig
from newscrawl_contracts.enums import FailureCategory, UrlType
from newscrawl_crawler_utils.urlnorm import (
    NormalizationConfig,
    UrlNormalizationError,
    normalize_url,
)
from scrapy import signals
from scrapy.crawler import Crawler
from scrapy.exceptions import DontCloseSpider
from scrapy.http import Response, TextResponse
from twisted.internet.error import (
    ConnectionRefusedError as TxConnectionRefused,
)
from twisted.internet.error import (
    DNSLookupError,
    TCPTimedOutError,
)
from twisted.internet.error import (
    TimeoutError as TxTimeoutError,
)
from twisted.python.failure import Failure

from newscrawl_crawler.browser import browser_request_meta
from newscrawl_crawler.extraction import extract_article
from newscrawl_crawler.items import DiscoveredLink, PageItem
from newscrawl_crawler.selectors import get_selector_set

# How many recent child sitemaps of a sitemap index to follow per pass.
SITEMAP_INDEX_LIMIT = 3


class NewsSpiderBase(scrapy.Spider):
    source_slug: str = ""

    def __init__(
        self,
        *args: Any,
        source_config: str | dict[str, Any],
        crawl_job_id: str | None = None,
        batch_size: int = 20,
        max_pages: int = 0,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        if isinstance(source_config, str):
            source_config = json.loads(source_config)
        self.source = SourceConfig.model_validate(source_config)
        self.crawl_job_id = crawl_job_id
        self.batch_size = batch_size
        # Hard per-pass budget (in addition to Scrapy's CLOSESPIDER_PAGECOUNT).
        # Stops idle-refill from claiming more work after the budget is spent.
        self.max_pages = max(0, int(max_pages or 0))
        self._pages_claimed = 0
        self.worker_id = f"spider-{self.source.slug}-{id(self)}"
        self.frontier = Frontier()
        self.selectors = get_selector_set(self.source.slug)
        self.article_patterns = [re.compile(p) for p in self.source.article_url_patterns]
        self.norm_config = NormalizationConfig.from_dict(self.source.url_normalization)
        self.allowed_domains = list(self.source.allowed_domains)
        self._exhausted = False
        self._refilling = False

    @classmethod
    def from_crawler(cls, crawler: Crawler, *args: Any, **kwargs: Any) -> NewsSpiderBase:
        spider: NewsSpiderBase = super().from_crawler(crawler, *args, **kwargs)
        crawler.signals.connect(spider._on_idle, signal=signals.spider_idle)
        return spider

    # ── Frontier claiming ────────────────────────────────────────────────────

    async def start(self) -> AsyncIterator[scrapy.Request]:
        for request in await self._claim_requests():
            yield request

    async def _claim_requests(self) -> list[scrapy.Request]:
        if self.max_pages and self._pages_claimed >= self.max_pages:
            self._exhausted = True
            self.logger.info(
                "page_budget_exhausted source=%s claimed=%d budget=%d",
                self.source.slug,
                self._pages_claimed,
                self.max_pages,
            )
            return []

        limit = self.batch_size
        if self.max_pages:
            limit = min(limit, max(self.max_pages - self._pages_claimed, 0))
            if limit <= 0:
                self._exhausted = True
                return []

        async with session_scope() as db:
            claimed = await self.frontier.claim_batch(
                db,
                worker_id=self.worker_id,
                limit=limit,
                source_id=self.source.id,
                crawl_job_id=(uuid.UUID(self.crawl_job_id) if self.crawl_job_id else None),
            )
            rows = [
                (url.id, url.normalized_url, url.url_type, url.etag, url.last_modified)
                for url in claimed
            ]
        if not rows:
            self._exhausted = True
            return []

        self._pages_claimed += len(rows)
        requests = []
        for url_id, url_str, url_type, etag, last_modified in rows:
            use_browser = self._needs_browser(url_type)
            headers: dict[str, str] = {}
            if not use_browser:
                # Conditional fetch (304) only makes sense over plain HTTP
                if etag:
                    headers["If-None-Match"] = etag
                if last_modified:
                    headers["If-Modified-Since"] = last_modified
            meta: dict[str, Any] = {
                "url_id": url_id,
                "url_type": url_type,
                "handle_httpstatus_list": [304],
                "fetch_started": datetime.now(UTC),
            }
            if use_browser:
                meta.update(browser_request_meta(self.source.slug))
            requests.append(
                scrapy.Request(
                    url_str,
                    callback=self.parse_page,
                    errback=self.on_error,
                    headers=headers,
                    meta=meta,
                    dont_filter=True,  # the frontier is the deduplicator
                )
            )
        self.logger.info(
            "claimed_batch source=%s size=%d total_claimed=%d budget=%s",
            self.source.slug,
            len(requests),
            self._pages_claimed,
            self.max_pages or "unlimited",
        )
        return requests

    def _on_idle(self, spider: scrapy.Spider) -> None:
        """Claim another batch when the scheduler runs dry; close when the
        frontier has nothing due."""
        if self._exhausted:
            return  # let the spider close naturally
        if self._refilling:
            raise DontCloseSpider

        import asyncio

        async def refill() -> None:
            try:
                requests = await self._claim_requests()
                engine = self.crawler.engine
                assert engine is not None
                for request in requests:
                    engine.crawl(request)
            finally:
                self._refilling = False

        self._refilling = True
        # The Twisted reactor runs on the asyncio loop, so DB work must be an
        # asyncio task — Deferred.fromCoroutine cannot await asyncio futures.
        asyncio.get_event_loop().create_task(refill())
        raise DontCloseSpider

    # ── Parsing ──────────────────────────────────────────────────────────────

    async def parse_page(self, response: Response) -> AsyncIterator[PageItem | scrapy.Request]:
        meta = response.meta
        url_type: UrlType = meta["url_type"]
        started: datetime = meta["fetch_started"]
        duration_ms = int((datetime.now(UTC) - started).total_seconds() * 1000)
        via_browser = bool(meta.get("playwright"))

        item = PageItem(
            url_id=meta["url_id"],
            source_id=self.source.id,
            source_slug=self.source.slug,
            url_type=url_type,
            normalized_url=response.url,
            http_status=response.status,
            fetched_at=datetime.now(UTC),
            crawl_job_id=(uuid.UUID(self.crawl_job_id) if self.crawl_job_id else None),
            fetch_method="browser" if via_browser else "http",
            duration_ms=duration_ms,
            etag=self._header(response, "ETag"),
            last_modified=self._header(response, "Last-Modified"),
        )

        if response.status == 304:
            item.not_modified = True
            yield item
            return

        if url_type == UrlType.SITEMAP:
            item.discovered = self._parse_sitemap(response)
        elif url_type == UrlType.RSS:
            item.discovered = self._parse_rss(response)
        elif url_type in (UrlType.HOMEPAGE, UrlType.SECTION):
            item.discovered = self._parse_section(response)
        elif url_type == UrlType.ARTICLE:
            item.raw_html = response.body
            extracted = extract_article(response.text, selectors=self.selectors)
            # Runtime browser-needed detection: an unusable HTTP-fetched
            # article usually means a client-side-rendered body — retry once
            # through Playwright before giving up on the URL.
            if not extracted.is_usable and not via_browser:
                retry = self._browser_retry_request(response)
                if retry is not None:
                    yield retry
                    return
            item.extracted = extracted.to_dict()
            item.canonical_url = extracted.canonical_url
            # Articles can also link to other articles
            item.discovered = self._parse_section(response)

        yield item

    def _needs_browser(self, url_type: UrlType) -> bool:
        """Sitemaps/RSS are plain XML — no browser needed even for
        browser-required sources."""
        return self.source.requires_browser and url_type not in (UrlType.SITEMAP, UrlType.RSS)

    def _browser_retry_request(self, response: Response) -> scrapy.Request | None:
        """Rebuild the request for a Playwright retry (once per URL)."""
        request = response.request
        if request is None or request.meta.get("browser_retry"):
            return None
        crawler = getattr(self, "crawler", None)
        if crawler is not None and crawler.stats is not None:
            crawler.stats.inc_value("newscrawl/browser_fallbacks")
        self.logger.info("browser_fallback url=%s", response.url)
        meta = dict(request.meta)
        meta.pop("download_slot", None)
        meta.pop("download_latency", None)
        meta["browser_retry"] = True
        meta["fetch_started"] = datetime.now(UTC)
        meta.update(browser_request_meta(self.source.slug))
        return request.replace(meta=meta, dont_filter=True)

    # ── Discovery parsers ────────────────────────────────────────────────────

    def _parse_sitemap(self, response: Response) -> list[DiscoveredLink]:
        if not isinstance(response, TextResponse):
            return []
        selector = response.selector
        selector.remove_namespaces()
        discovered: list[DiscoveredLink] = []

        # Sitemap index → follow the most recent child sitemaps
        children = []
        for sitemap in selector.xpath("//sitemapindex/sitemap"):
            loc = sitemap.xpath("./loc/text()").get()
            lastmod = sitemap.xpath("./lastmod/text()").get()
            if loc:
                children.append((lastmod or "", loc.strip()))
        if children:
            children.sort(reverse=True)
            for _, loc in children[:SITEMAP_INDEX_LIMIT]:
                discovered.append(DiscoveredLink(url=loc, url_type=UrlType.SITEMAP))
            return discovered

        # URL set → article candidates
        for url_node in selector.xpath("//urlset/url"):
            loc = url_node.xpath("./loc/text()").get()
            if not loc:
                continue
            loc = loc.strip()
            lastmod = url_node.xpath("./lastmod/text()").get()
            published = self._parse_datetime(lastmod)
            discovered.append(
                DiscoveredLink(
                    url=loc,
                    url_type=self._classify_url(loc),
                    published_at=published,
                )
            )
        return discovered

    def _parse_rss(self, response: Response) -> list[DiscoveredLink]:
        feed = feedparser.parse(response.body)
        discovered: list[DiscoveredLink] = []
        for entry in feed.entries:
            link = getattr(entry, "link", None)
            if not link:
                continue
            published = None
            parsed_time = getattr(entry, "published_parsed", None) or getattr(
                entry, "updated_parsed", None
            )
            if parsed_time:
                published = datetime(*parsed_time[:6]).replace(tzinfo=UTC)
            discovered.append(
                DiscoveredLink(url=link, url_type=UrlType.ARTICLE, published_at=published)
            )
        return discovered

    def _parse_section(self, response: Response) -> list[DiscoveredLink]:
        if not isinstance(response, TextResponse):
            return []
        discovered: list[DiscoveredLink] = []
        seen: set[str] = set()
        for href in response.css("a::attr(href)").getall():
            absolute = response.urljoin(href.strip())
            if absolute in seen:
                continue
            seen.add(absolute)
            if self._matches_article_pattern(absolute):
                discovered.append(DiscoveredLink(url=absolute, url_type=UrlType.ARTICLE))
        return discovered

    # ── Failure handling ─────────────────────────────────────────────────────

    async def on_error(self, failure: Failure) -> None:
        request: scrapy.Request = failure.request  # type: ignore[attr-defined]
        url_id = request.meta.get("url_id")
        if url_id is None:
            return
        category, message = self._classify_failure(failure)
        async with session_scope() as db:
            status = await self.frontier.mark_failed(db, url_id, category=category, error=message)
            if self.crawl_job_id:
                from newscrawl_api.services.crawl_jobs import CrawlJobService

                job_uuid = uuid.UUID(self.crawl_job_id)
                await CrawlJobService.increment_counters(
                    db, job_uuid, pages_requested=1, pages_failed=1
                )
                await CrawlJobService.record_error(db, job_uuid, f"{request.url}: {message}")
        self.logger.warning(
            "fetch_failed url=%s category=%s new_status=%s",
            request.url,
            category.value,
            status.value,
        )
        if self.crawler.stats is not None:
            self.crawler.stats.inc_value(f"newscrawl/failures/{category.value}")

    @staticmethod
    def _classify_failure(failure: Failure) -> tuple[FailureCategory, str]:
        from scrapy.exceptions import IgnoreRequest

        message = failure.getErrorMessage()[:500]
        if failure.check(IgnoreRequest):  # type: ignore[no-untyped-call]
            # RobotsTxtMiddleware raises IgnoreRequest for disallowed URLs
            return FailureCategory.ROBOTS_RESTRICTED, f"robots/ignored: {message}"
        # Playwright raises its own error types (TimeoutError, TargetClosedError,
        # Error) — anything from the playwright package is a browser failure.
        failure_module = getattr(failure.type, "__module__", "") or ""
        if failure_module.startswith("playwright"):
            return FailureCategory.BROWSER_FAILURE, f"playwright: {message}"
        if failure.check(DNSLookupError):  # type: ignore[no-untyped-call]
            return FailureCategory.DNS_FAILURE, message
        if failure.check(TxTimeoutError, TCPTimedOutError):  # type: ignore[no-untyped-call]
            return FailureCategory.CONNECTION_TIMEOUT, message
        if failure.check(TxConnectionRefused):  # type: ignore[no-untyped-call]
            return FailureCategory.CONNECTION_TIMEOUT, message
        from scrapy.spidermiddlewares.httperror import HttpError

        if failure.check(HttpError):  # type: ignore[no-untyped-call]
            response: Response = failure.value.response  # type: ignore[union-attr]
            if response.status == 403:
                return FailureCategory.HTTP_403, f"HTTP 403 {message}"
            if response.status == 429:
                return FailureCategory.HTTP_429, f"HTTP 429 {message}"
            if 500 <= response.status < 600:
                return FailureCategory.HTTP_5XX, f"HTTP {response.status} {message}"
            return FailureCategory.HTTP_OTHER, f"HTTP {response.status} {message}"
        return FailureCategory.UNKNOWN, message

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _matches_article_pattern(self, url: str) -> bool:
        # Patterns are written against the *normalized* form (the frontier's
        # dedup key), so raw hrefs with trailing slashes / tracking params
        # must be normalized before matching.
        try:
            candidate = normalize_url(url, config=self.norm_config)
        except UrlNormalizationError:
            return False
        return any(pattern.match(candidate) for pattern in self.article_patterns)

    def _classify_url(self, url: str) -> UrlType:
        if self._matches_article_pattern(url):
            return UrlType.ARTICLE
        if "sitemap" in url and url.endswith(".xml"):
            return UrlType.SITEMAP
        return UrlType.OTHER

    @staticmethod
    def _header(response: Response, name: str) -> str | None:
        value = response.headers.get(name)
        return value.decode("latin-1") if value else None

    @staticmethod
    def _parse_datetime(raw: str | None) -> datetime | None:
        if not raw:
            return None
        try:
            parsed = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed


def frontier_discoveries(links: list[DiscoveredLink], from_url: str) -> list[DiscoveredUrl]:
    """Convert spider discoveries into frontier candidates."""
    return [
        DiscoveredUrl(
            url=link.url,
            url_type=link.url_type,
            discovered_from=from_url,
            published_at=link.published_at,
        )
        for link in links
    ]
