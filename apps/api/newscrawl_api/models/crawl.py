"""Crawl plane tables: jobs, workers, the URL frontier, attempts, and events.

`crawl_attempts` and `crawl_events` are declaratively range-partitioned by
timestamp — they are append-only and high-volume, so old partitions can be
detached/dropped cheaply.
"""

import uuid
from datetime import datetime
from typing import Any

from newscrawl_contracts.enums import (
    AttemptOutcome,
    CrawlJobStatus,
    CrawlJobType,
    FailureCategory,
    FetchMethod,
    UrlStatus,
    UrlType,
    WorkerStatus,
    WorkerType,
)
from sqlalchemy import BigInteger, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from newscrawl_api.models.base import Base, TimestampMixin, str_enum, uuid_pk


class CrawlJob(Base, TimestampMixin):
    __tablename__ = "crawl_jobs"

    id: Mapped[uuid.UUID] = uuid_pk()
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sources.id"), index=True)
    job_type: Mapped[CrawlJobType] = mapped_column(str_enum(CrawlJobType))
    status: Mapped[CrawlJobStatus] = mapped_column(
        str_enum(CrawlJobStatus), default=CrawlJobStatus.CREATED, index=True
    )
    priority: Mapped[int] = mapped_column(default=0)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), default=None)
    # Job-type specific parameters (section urls, explicit url list, backfill range, ...)
    params: Mapped[dict[str, Any]] = mapped_column(default=dict)

    started_at: Mapped[datetime | None] = mapped_column(default=None)
    completed_at: Mapped[datetime | None] = mapped_column(default=None)

    # Progress counters (incremented atomically by workers)
    pages_discovered: Mapped[int] = mapped_column(default=0)
    pages_requested: Mapped[int] = mapped_column(default=0)
    pages_successful: Mapped[int] = mapped_column(default=0)
    pages_failed: Mapped[int] = mapped_column(default=0)
    pages_skipped: Mapped[int] = mapped_column(default=0)
    pages_changed: Mapped[int] = mapped_column(default=0)
    pages_unchanged: Mapped[int] = mapped_column(default=0)
    error_count: Mapped[int] = mapped_column(default=0)
    last_error: Mapped[str | None] = mapped_column(Text, default=None)

    __table_args__ = (Index("ix_crawl_jobs_source_status", "source_id", "status"),)


class CrawlWorker(Base):
    __tablename__ = "crawl_workers"

    # Worker-generated stable id, e.g. "crawler-hostname-pid-uuid"
    id: Mapped[str] = mapped_column(String(200), primary_key=True)
    worker_type: Mapped[WorkerType] = mapped_column(str_enum(WorkerType))
    status: Mapped[WorkerStatus] = mapped_column(
        str_enum(WorkerStatus), default=WorkerStatus.STARTING
    )
    hostname: Mapped[str] = mapped_column(String(200))
    pid: Mapped[int]
    started_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    last_heartbeat_at: Mapped[datetime] = mapped_column(server_default=text("now()"), index=True)
    current_job_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    meta: Mapped[dict[str, Any]] = mapped_column(default=dict)


class CrawlUrl(Base):
    """The URL frontier. One row per unique normalized URL, ever.

    Lease-based claiming: workers claim batches with FOR UPDATE SKIP LOCKED,
    set lease_owner/lease_expires_at, and a reaper requeues expired leases.
    """

    __tablename__ = "crawl_urls"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    url: Mapped[str] = mapped_column(Text)
    canonical_url: Mapped[str | None] = mapped_column(Text, default=None)
    normalized_url: Mapped[str] = mapped_column(Text)
    # sha256 hex of normalized_url — THE dedup key
    url_hash: Mapped[str] = mapped_column(String(64), unique=True)
    domain: Mapped[str] = mapped_column(String(255))
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sources.id"))
    discovered_from: Mapped[str | None] = mapped_column(Text, default=None)
    depth: Mapped[int] = mapped_column(default=0)
    priority: Mapped[float] = mapped_column(default=0.0)
    url_type: Mapped[UrlType] = mapped_column(str_enum(UrlType), default=UrlType.OTHER)
    status: Mapped[UrlStatus] = mapped_column(str_enum(UrlStatus), default=UrlStatus.DISCOVERED)

    first_seen_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    last_seen_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    last_crawled_at: Mapped[datetime | None] = mapped_column(default=None)
    next_crawl_at: Mapped[datetime | None] = mapped_column(server_default=text("now()"))

    retry_count: Mapped[int] = mapped_column(default=0)
    last_http_status: Mapped[int | None] = mapped_column(default=None)
    last_error: Mapped[str | None] = mapped_column(Text, default=None)
    failure_category: Mapped[FailureCategory | None] = mapped_column(
        str_enum(FailureCategory), default=None
    )

    # Incremental crawling state
    content_hash: Mapped[str | None] = mapped_column(String(64), default=None)
    etag: Mapped[str | None] = mapped_column(String(500), default=None)
    last_modified: Mapped[str | None] = mapped_column(String(100), default=None)

    # Lease management
    lease_owner: Mapped[str | None] = mapped_column(String(200), default=None)
    lease_expires_at: Mapped[datetime | None] = mapped_column(default=None)
    crawl_job_id: Mapped[uuid.UUID | None] = mapped_column(default=None)

    __table_args__ = (
        Index("ix_crawl_urls_source_status", "source_id", "status"),
        # Claim query: queued URLs due for crawling, best priority first
        Index(
            "ix_crawl_urls_claim",
            "source_id",
            "next_crawl_at",
            postgresql_where=text("status IN ('queued', 'retry_pending')"),
        ),
        Index("ix_crawl_urls_domain_next", "domain", "next_crawl_at"),
        # Reaper: find expired leases cheaply
        Index(
            "ix_crawl_urls_lease_expiry",
            "lease_expires_at",
            postgresql_where=text("status IN ('leased', 'crawling')"),
        ),
        Index("ix_crawl_urls_content_hash", "content_hash"),
    )


class CrawlAttempt(Base):
    """Append-only fetch log, range-partitioned by month on attempted_at."""

    __tablename__ = "crawl_attempts"

    id: Mapped[int] = mapped_column(BigInteger, autoincrement=True, primary_key=True)
    attempted_at: Mapped[datetime] = mapped_column(server_default=text("now()"), primary_key=True)
    url_id: Mapped[int] = mapped_column(BigInteger, index=True)
    crawl_job_id: Mapped[uuid.UUID | None] = mapped_column(default=None, index=True)
    worker_id: Mapped[str | None] = mapped_column(String(200), default=None)
    fetch_method: Mapped[FetchMethod] = mapped_column(str_enum(FetchMethod))
    outcome: Mapped[AttemptOutcome] = mapped_column(str_enum(AttemptOutcome))
    http_status: Mapped[int | None] = mapped_column(default=None)
    duration_ms: Mapped[int | None] = mapped_column(default=None)
    bytes_downloaded: Mapped[int | None] = mapped_column(BigInteger, default=None)
    failure_category: Mapped[FailureCategory | None] = mapped_column(
        str_enum(FailureCategory), default=None
    )
    error_message: Mapped[str | None] = mapped_column(Text, default=None)

    __table_args__ = {"postgresql_partition_by": "RANGE (attempted_at)"}  # noqa: RUF012


class CrawlEvent(Base):
    """Structured audit/event log, range-partitioned by month on created_at."""

    __tablename__ = "crawl_events"

    id: Mapped[int] = mapped_column(BigInteger, autoincrement=True, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(100), index=True)
    crawl_job_id: Mapped[uuid.UUID | None] = mapped_column(default=None, index=True)
    source_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    url_id: Mapped[int | None] = mapped_column(BigInteger, default=None)
    worker_id: Mapped[str | None] = mapped_column(String(200), default=None)
    payload: Mapped[dict[str, Any]] = mapped_column(default=dict)

    __table_args__ = {"postgresql_partition_by": "RANGE (created_at)"}  # noqa: RUF012
