"""News source configuration."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from newscrawl_api.models.base import Base, TimestampMixin, uuid_pk


class Source(Base, TimestampMixin):
    __tablename__ = "sources"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    base_url: Mapped[str] = mapped_column(String(500))
    language: Mapped[str] = mapped_column(String(8))
    country: Mapped[str] = mapped_column(String(8))
    enabled: Mapped[bool] = mapped_column(default=True)
    crawl_enabled: Mapped[bool] = mapped_column(default=True)

    # Discovery configuration
    allowed_domains: Mapped[list[str]] = mapped_column(default=list)
    article_url_patterns: Mapped[list[str]] = mapped_column(default=list)
    section_urls: Mapped[list[str]] = mapped_column(default=list)
    sitemap_urls: Mapped[list[str]] = mapped_column(default=list)
    rss_urls: Mapped[list[str]] = mapped_column(default=list)

    # Crawl behaviour
    crawl_frequency_minutes: Mapped[int] = mapped_column(default=60)
    rate_limit_delay_seconds: Mapped[float] = mapped_column(default=2.0)
    max_concurrency: Mapped[int] = mapped_column(default=2)
    requires_browser: Mapped[bool] = mapped_column(default=False)
    extraction_strategy: Mapped[str] = mapped_column(String(50), default="selectors")
    robots_policy: Mapped[str] = mapped_column(String(20), default="obey")
    source_weight: Mapped[float] = mapped_column(default=1.0)

    # Per-source URL normalization overrides (tracking params, kept params, ...)
    url_normalization: Mapped[dict[str, Any]] = mapped_column(default=dict)

    # Extraction rules (CSS selector set). NULL means "never explicitly set" —
    # distinct from an operator saving an empty payload — so the seed script
    # can backfill legacy rows without ever overwriting an operator's edit.
    selectors: Mapped[dict[str, Any] | None] = mapped_column(default=None)

    # Health
    last_successful_crawl_at: Mapped[datetime | None] = mapped_column(default=None)
    last_error: Mapped[str | None] = mapped_column(Text, default=None)
