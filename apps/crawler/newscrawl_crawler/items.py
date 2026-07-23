"""Items flowing through the crawler pipelines."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from newscrawl_contracts.enums import UrlType


@dataclass
class DiscoveredLink:
    url: str
    url_type: UrlType
    published_at: datetime | None = None


@dataclass
class PageItem:
    """One successfully fetched page (of any type)."""

    url_id: int
    source_id: UUID
    source_slug: str
    url_type: UrlType
    normalized_url: str
    http_status: int
    fetched_at: datetime
    crawl_job_id: UUID | None = None
    not_modified: bool = False
    fetch_method: str = "http"
    duration_ms: int | None = None
    etag: str | None = None
    last_modified: str | None = None
    canonical_url: str | None = None
    content_hash: str | None = None
    raw_html: bytes | None = None
    raw_html_location: str | None = None
    extracted: dict[str, Any] | None = None
    discovered: list[DiscoveredLink] = field(default_factory=list)
    # Set by pipelines for downstream decisions
    content_changed: bool = True
