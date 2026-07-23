"""URL frontier: durable, lease-based, distributed URL scheduling on PostgreSQL.

Design (ADR-001):
- crawl_urls is the single source of truth for per-URL state.
- Workers claim batches atomically using FOR UPDATE SKIP LOCKED so concurrent
  workers never receive the same URL.
- Claims are leases: a worker owns a URL until lease_expires_at. If the worker
  dies, the reaper returns expired leases to the queue — no URL is ever lost.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from newscrawl_contracts.enums import FailureCategory, UrlStatus, UrlType
from newscrawl_crawler_utils import (
    NormalizationConfig,
    UrlNormalizationError,
    compute_backoff_seconds,
    normalize_url,
    url_domain,
    url_hash,
)
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from newscrawl_api.models import CrawlUrl
from newscrawl_api.services.priority import compute_priority

# Failures that will never succeed on retry — don't waste the retry budget.
PERMANENT_FAILURES: frozenset[FailureCategory] = frozenset({FailureCategory.ROBOTS_RESTRICTED})
# Failures that indicate blocking — back off much harder.
BLOCKING_FAILURES: frozenset[FailureCategory] = frozenset(
    {FailureCategory.HTTP_403, FailureCategory.HTTP_429}
)


@dataclass(frozen=True)
class DiscoveredUrl:
    url: str
    url_type: UrlType = UrlType.OTHER
    discovered_from: str | None = None
    depth: int = 0
    published_at: datetime | None = None


class SourceLike(Protocol):
    """Satisfied by both the Source ORM model and the SourceConfig snapshot."""

    @property
    def id(self) -> uuid.UUID: ...
    @property
    def base_url(self) -> str: ...
    @property
    def source_weight(self) -> float: ...
    @property
    def allowed_domains(self) -> list[str]: ...
    @property
    def url_normalization(self) -> dict[str, Any]: ...


class Frontier:
    def __init__(
        self,
        *,
        lease_seconds: int = 300,
        max_retries: int = 5,
        recrawl_article_hours: float = 24.0,
        recrawl_hub_minutes: float = 30.0,
    ) -> None:
        self.lease_seconds = lease_seconds
        self.max_retries = max_retries
        self.recrawl_article_hours = recrawl_article_hours
        self.recrawl_hub_minutes = recrawl_hub_minutes

    # ── Discovery ────────────────────────────────────────────────────────────

    async def add_urls(
        self,
        db: AsyncSession,
        source: SourceLike,
        discovered: list[DiscoveredUrl],
        *,
        crawl_job_id: uuid.UUID | None = None,
        requeue_existing: bool = False,
    ) -> int:
        """Insert newly discovered URLs; refresh last_seen_at on known ones.

        With ``requeue_existing`` (job entry seeding), already-known URLs that
        are not currently claimed are made due immediately and adopted by the
        job, so a new job always re-visits its entry points.

        Returns the number of URLs added or requeued. SSRF guard: URLs
        outside the source's allowed domains are silently dropped.
        """
        cfg = NormalizationConfig.from_dict(source.url_normalization)
        allowed = set(source.allowed_domains or ())

        rows: dict[str, dict[str, object]] = {}
        for item in discovered:
            try:
                normalized = normalize_url(item.url, base_url=source.base_url, config=cfg)
            except UrlNormalizationError:
                continue
            domain = url_domain(normalized)
            if allowed and not any(domain == d or domain.endswith("." + d) for d in allowed):
                continue
            digest = url_hash(normalized)
            priority = compute_priority(
                source_weight=source.source_weight,
                url_type=item.url_type,
                depth=item.depth,
                published_at=item.published_at,
            )
            # Deduplicate within the batch (dict keyed by hash keeps the first).
            rows.setdefault(
                digest,
                {
                    "url": item.url,
                    "normalized_url": normalized,
                    "url_hash": digest,
                    "domain": domain,
                    "source_id": source.id,
                    "discovered_from": item.discovered_from,
                    "depth": item.depth,
                    "priority": priority,
                    "url_type": item.url_type,
                    "status": UrlStatus.QUEUED,
                    "crawl_job_id": crawl_job_id,
                },
            )

        if not rows:
            return 0

        now = datetime.now(UTC)
        statement = pg_insert(CrawlUrl).values(list(rows.values()))
        if requeue_existing:
            # Adopt unclaimed known URLs into the job and make them due now.
            statement = statement.on_conflict_do_update(
                index_elements=[CrawlUrl.url_hash],
                set_={
                    "last_seen_at": now,
                    "crawl_job_id": crawl_job_id,
                    "status": UrlStatus.QUEUED,
                    "next_crawl_at": now,
                    "retry_count": 0,
                },
                where=CrawlUrl.status.notin_([UrlStatus.LEASED, UrlStatus.CRAWLING]),
            )
            result = await db.execute(statement.returning(CrawlUrl.id))
            return len(result.all())

        statement = statement.on_conflict_do_update(
            index_elements=[CrawlUrl.url_hash],
            set_={"last_seen_at": now},
        )
        result = await db.execute(
            statement.returning(CrawlUrl.id, CrawlUrl.first_seen_at, CrawlUrl.last_seen_at)
        )
        inserted = sum(1 for _, first, last in result if first == last)
        return inserted

    # ── Claiming (lease-based) ───────────────────────────────────────────────

    async def claim_batch(
        self,
        db: AsyncSession,
        *,
        worker_id: str,
        limit: int = 20,
        source_id: uuid.UUID | None = None,
        crawl_job_id: uuid.UUID | None = None,
    ) -> list[CrawlUrl]:
        """Atomically claim up to `limit` due URLs for this worker."""
        now = datetime.now(UTC)
        candidates = (
            select(CrawlUrl.id)
            .where(
                CrawlUrl.status.in_([UrlStatus.QUEUED, UrlStatus.RETRY_PENDING]),
                CrawlUrl.next_crawl_at <= now,
            )
            .order_by(CrawlUrl.priority.desc(), CrawlUrl.next_crawl_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        if source_id is not None:
            candidates = candidates.where(CrawlUrl.source_id == source_id)
        if crawl_job_id is not None:
            candidates = candidates.where(CrawlUrl.crawl_job_id == crawl_job_id)

        claimed = await db.scalars(
            update(CrawlUrl)
            .where(CrawlUrl.id.in_(candidates.scalar_subquery()))
            .values(
                status=UrlStatus.LEASED,
                lease_owner=worker_id,
                lease_expires_at=now + timedelta(seconds=self.lease_seconds),
            )
            .returning(CrawlUrl)
        )
        return list(claimed.all())

    async def extend_lease(self, db: AsyncSession, url_id: int, worker_id: str) -> bool:
        result = await db.execute(
            update(CrawlUrl)
            .where(CrawlUrl.id == url_id, CrawlUrl.lease_owner == worker_id)
            .values(lease_expires_at=datetime.now(UTC) + timedelta(seconds=self.lease_seconds))
        )
        return bool(getattr(result, "rowcount", 0))

    async def release(self, db: AsyncSession, url_id: int, worker_id: str) -> None:
        """Voluntarily return a claimed URL (graceful shutdown)."""
        await db.execute(
            update(CrawlUrl)
            .where(CrawlUrl.id == url_id, CrawlUrl.lease_owner == worker_id)
            .values(
                status=UrlStatus.QUEUED,
                lease_owner=None,
                lease_expires_at=None,
            )
        )

    # ── Outcomes ─────────────────────────────────────────────────────────────

    async def mark_success(
        self,
        db: AsyncSession,
        url_id: int,
        *,
        http_status: int,
        content_hash: str | None = None,
        etag: str | None = None,
        last_modified: str | None = None,
        canonical_url: str | None = None,
    ) -> bool:
        """Record a successful fetch. Returns True when the content hash
        differs from the previous crawl (i.e. the page actually changed)."""
        now = datetime.now(UTC)
        url = await db.get(CrawlUrl, url_id)
        if url is None:
            return False
        changed = content_hash is None or url.content_hash != content_hash
        interval = (
            timedelta(minutes=self.recrawl_hub_minutes)
            if url.url_type in (UrlType.HOMEPAGE, UrlType.SECTION, UrlType.RSS, UrlType.SITEMAP)
            else timedelta(hours=self.recrawl_article_hours)
        )
        url.status = UrlStatus.SUCCESS
        url.lease_owner = None
        url.lease_expires_at = None
        url.last_crawled_at = now
        url.next_crawl_at = now + interval
        url.retry_count = 0
        url.last_http_status = http_status
        url.last_error = None
        url.failure_category = None
        if content_hash is not None:
            url.content_hash = content_hash
        if etag is not None:
            url.etag = etag
        if last_modified is not None:
            url.last_modified = last_modified
        if canonical_url is not None:
            url.canonical_url = canonical_url
        return changed

    async def mark_not_modified(self, db: AsyncSession, url_id: int) -> None:
        """HTTP 304: content unchanged — just reschedule."""
        now = datetime.now(UTC)
        url = await db.get(CrawlUrl, url_id)
        if url is None:
            return
        url.status = UrlStatus.SUCCESS
        url.lease_owner = None
        url.lease_expires_at = None
        url.last_crawled_at = now
        url.next_crawl_at = now + timedelta(hours=self.recrawl_article_hours)
        url.retry_count = 0
        url.last_http_status = 304

    async def mark_failed(
        self,
        db: AsyncSession,
        url_id: int,
        *,
        category: FailureCategory,
        error: str,
        http_status: int | None = None,
    ) -> UrlStatus:
        """Record a failure; schedule a retry with backoff or give up."""
        now = datetime.now(UTC)
        url = await db.get(CrawlUrl, url_id)
        if url is None:
            return UrlStatus.FAILED

        url.retry_count += 1
        url.lease_owner = None
        url.lease_expires_at = None
        url.last_http_status = http_status
        url.last_error = error[:2000]
        url.failure_category = category
        url.last_crawled_at = now

        if category in PERMANENT_FAILURES:
            url.status = UrlStatus.BLOCKED
            url.next_crawl_at = None
        elif url.retry_count >= self.max_retries:
            url.status = UrlStatus.FAILED
            url.next_crawl_at = None
        else:
            backoff = compute_backoff_seconds(url.retry_count)
            if category in BLOCKING_FAILURES:
                backoff *= 4  # blocked: slow way down before retrying
            url.status = UrlStatus.RETRY_PENDING
            url.next_crawl_at = now + timedelta(seconds=backoff)
        return url.status

    async def skip(self, db: AsyncSession, url_id: int, reason: str) -> None:
        await db.execute(
            update(CrawlUrl)
            .where(CrawlUrl.id == url_id)
            .values(
                status=UrlStatus.SKIPPED,
                lease_owner=None,
                lease_expires_at=None,
                last_error=reason[:2000],
            )
        )

    # ── Failure recovery ─────────────────────────────────────────────────────

    async def reap_expired_leases(self, db: AsyncSession) -> int:
        """Return URLs whose lease expired (worker crash) to the queue."""
        result = await db.execute(
            update(CrawlUrl)
            .where(
                CrawlUrl.status.in_([UrlStatus.LEASED, UrlStatus.CRAWLING]),
                CrawlUrl.lease_expires_at < datetime.now(UTC),
            )
            .values(
                status=UrlStatus.QUEUED,
                lease_owner=None,
                lease_expires_at=None,
            )
        )
        return int(getattr(result, "rowcount", 0) or 0)

    async def requeue_failed(
        self, db: AsyncSession, *, source_id: uuid.UUID, crawl_job_id: uuid.UUID | None = None
    ) -> int:
        """Manual retry of FAILED URLs (RETRY_FAILED job type)."""
        result = await db.execute(
            update(CrawlUrl)
            .where(CrawlUrl.source_id == source_id, CrawlUrl.status == UrlStatus.FAILED)
            .values(
                status=UrlStatus.RETRY_PENDING,
                retry_count=0,
                next_crawl_at=datetime.now(UTC),
                crawl_job_id=crawl_job_id,
            )
        )
        return int(getattr(result, "rowcount", 0) or 0)
