"""Crawl job lifecycle: creation (frontier seeding), state machine, counters.

A crawl job is the operator-facing unit of work: "crawl this source now,
this way". Creating a job seeds the frontier with the job's entry URLs;
workers then claim those URLs and roll progress counters up to the job row.

State machine:

    created ──> queued ──> running ──> completed
       │           │          │  │
       │           │          │  └───> failed
       └───────────┴──────────┴─────> cancelled
                   │          │
                   └── paused ┘  (paused <──> queued/running)
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from newscrawl_contracts.enums import CrawlJobStatus, CrawlJobType, UrlType
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from newscrawl_api.models import CrawlJob, Source
from newscrawl_api.services.frontier import DiscoveredUrl, Frontier

VALID_TRANSITIONS: dict[CrawlJobStatus, frozenset[CrawlJobStatus]] = {
    CrawlJobStatus.CREATED: frozenset({CrawlJobStatus.QUEUED, CrawlJobStatus.CANCELLED}),
    CrawlJobStatus.QUEUED: frozenset(
        {CrawlJobStatus.RUNNING, CrawlJobStatus.PAUSED, CrawlJobStatus.CANCELLED}
    ),
    CrawlJobStatus.RUNNING: frozenset(
        {
            CrawlJobStatus.PAUSED,
            CrawlJobStatus.COMPLETED,
            CrawlJobStatus.FAILED,
            CrawlJobStatus.CANCELLED,
        }
    ),
    CrawlJobStatus.PAUSED: frozenset(
        {CrawlJobStatus.QUEUED, CrawlJobStatus.RUNNING, CrawlJobStatus.CANCELLED}
    ),
    CrawlJobStatus.COMPLETED: frozenset(),
    CrawlJobStatus.FAILED: frozenset(),
    CrawlJobStatus.CANCELLED: frozenset(),
}

TERMINAL_STATUSES: frozenset[CrawlJobStatus] = frozenset(
    {CrawlJobStatus.COMPLETED, CrawlJobStatus.FAILED, CrawlJobStatus.CANCELLED}
)


class InvalidTransitionError(Exception):
    def __init__(self, current: CrawlJobStatus, target: CrawlJobStatus) -> None:
        self.current = current
        self.target = target
        super().__init__(f"Cannot transition crawl job from '{current}' to '{target}'")


class JobParamsError(Exception):
    """Raised when job params are missing or invalid for the job type."""


def entry_urls_for_job(
    source: Source, job_type: CrawlJobType, params: dict[str, Any]
) -> list[DiscoveredUrl]:
    """The frontier seed set for a job, derived from its type and params."""
    if job_type == CrawlJobType.FULL_CRAWL:
        return [
            DiscoveredUrl(url=source.base_url, url_type=UrlType.HOMEPAGE),
            *[DiscoveredUrl(url=u, url_type=UrlType.SITEMAP) for u in source.sitemap_urls],
            *[DiscoveredUrl(url=u, url_type=UrlType.RSS) for u in source.rss_urls],
            *[DiscoveredUrl(url=u, url_type=UrlType.SECTION) for u in source.section_urls],
        ]
    if job_type == CrawlJobType.INCREMENTAL_CRAWL:
        # Hubs only: fresh links surface on the homepage, feeds, and sections.
        return [
            DiscoveredUrl(url=source.base_url, url_type=UrlType.HOMEPAGE),
            *[DiscoveredUrl(url=u, url_type=UrlType.RSS) for u in source.rss_urls],
            *[DiscoveredUrl(url=u, url_type=UrlType.SECTION) for u in source.section_urls],
        ]
    if job_type == CrawlJobType.SECTION_CRAWL:
        sections = params.get("section_urls") or source.section_urls
        if not sections:
            raise JobParamsError("section_crawl requires params.section_urls (or source sections)")
        return [DiscoveredUrl(url=u, url_type=UrlType.SECTION) for u in sections]
    if job_type == CrawlJobType.URL_CRAWL:
        urls = params.get("urls")
        if not urls:
            raise JobParamsError("url_crawl requires params.urls")
        return [DiscoveredUrl(url=u, url_type=UrlType.ARTICLE) for u in urls]
    if job_type == CrawlJobType.BACKFILL:
        sitemaps = params.get("sitemap_urls") or source.sitemap_urls
        if not sitemaps:
            raise JobParamsError("backfill requires params.sitemap_urls (or source sitemaps)")
        return [DiscoveredUrl(url=u, url_type=UrlType.SITEMAP) for u in sitemaps]
    # RETRY_FAILED has no entry URLs — it requeues existing failed rows.
    return []


class CrawlJobService:
    def __init__(self, frontier: Frontier | None = None) -> None:
        self.frontier = frontier or Frontier()

    async def create_job(
        self,
        db: AsyncSession,
        source: Source,
        *,
        job_type: CrawlJobType,
        params: dict[str, Any] | None = None,
        priority: int = 0,
        created_by: uuid.UUID | None = None,
    ) -> CrawlJob:
        """Create a job and seed the frontier with its entry URLs."""
        params = params or {}
        entry = entry_urls_for_job(source, job_type, params)  # validates params early

        job = CrawlJob(
            source_id=source.id,
            job_type=job_type,
            params=params,
            priority=priority,
            created_by=created_by,
        )
        db.add(job)
        await db.flush()  # assign job.id before seeding

        if job_type == CrawlJobType.RETRY_FAILED:
            seeded = await self.frontier.requeue_failed(
                db, source_id=source.id, crawl_job_id=job.id
            )
        else:
            seeded = await self.frontier.add_urls(
                db, source, entry, crawl_job_id=job.id, requeue_existing=True
            )

        job.pages_discovered = seeded
        job.status = CrawlJobStatus.QUEUED
        return job

    # ── State machine ────────────────────────────────────────────────────────

    async def transition(self, db: AsyncSession, job: CrawlJob, target: CrawlJobStatus) -> CrawlJob:
        if target not in VALID_TRANSITIONS[job.status]:
            raise InvalidTransitionError(job.status, target)
        now = datetime.now(UTC)
        job.status = target
        if target == CrawlJobStatus.RUNNING and job.started_at is None:
            job.started_at = now
        if target in TERMINAL_STATUSES:
            job.completed_at = now
        await db.flush()
        return job

    async def pause(self, db: AsyncSession, job: CrawlJob) -> CrawlJob:
        return await self.transition(db, job, CrawlJobStatus.PAUSED)

    async def resume(self, db: AsyncSession, job: CrawlJob) -> CrawlJob:
        target = CrawlJobStatus.RUNNING if job.started_at else CrawlJobStatus.QUEUED
        return await self.transition(db, job, target)

    async def cancel(self, db: AsyncSession, job: CrawlJob) -> CrawlJob:
        return await self.transition(db, job, CrawlJobStatus.CANCELLED)

    # ── Counters (atomic; called concurrently by workers) ────────────────────

    @staticmethod
    async def increment_counters(db: AsyncSession, job_id: uuid.UUID, **counters: int) -> None:
        """Atomically add to progress counters, e.g. pages_successful=1."""
        valid = {
            "pages_discovered",
            "pages_requested",
            "pages_successful",
            "pages_failed",
            "pages_skipped",
            "pages_changed",
            "pages_unchanged",
            "error_count",
        }
        unknown = set(counters) - valid
        if unknown:
            raise ValueError(f"Unknown crawl job counters: {sorted(unknown)}")
        values = {
            name: getattr(CrawlJob, name) + delta for name, delta in counters.items() if delta
        }
        if not values:
            return
        await db.execute(update(CrawlJob).where(CrawlJob.id == job_id).values(**values))

    @staticmethod
    async def record_error(db: AsyncSession, job_id: uuid.UUID, error: str) -> None:
        await db.execute(
            update(CrawlJob)
            .where(CrawlJob.id == job_id)
            .values(error_count=CrawlJob.error_count + 1, last_error=error[:2000])
        )
