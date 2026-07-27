import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class SelectorSetSchema(BaseModel):
    """CSS extraction rules for a source. Fields mirror the crawler's
    ``SelectorSet`` dataclass so a payload here round-trips unchanged into the
    ``SourceConfig`` snapshot the crawl worker receives."""

    title: list[str] = Field(default_factory=lambda: ["h1::text"])
    subtitle: list[str] = Field(default_factory=list)
    author: list[str] = Field(default_factory=list)
    published_at: list[str] = Field(default_factory=lambda: ["time::attr(datetime)"])
    category: list[str] = Field(default_factory=list)
    body: list[str] = Field(default_factory=lambda: ["article p"])
    images: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    body_probe: str | None = None


class SourceBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9-]+$")
    base_url: str
    language: str = Field(max_length=8)
    country: str = Field(max_length=8)
    enabled: bool = True
    crawl_enabled: bool = True
    allowed_domains: list[str] = Field(default_factory=list)
    article_url_patterns: list[str] = Field(default_factory=list)
    section_urls: list[str] = Field(default_factory=list)
    sitemap_urls: list[str] = Field(default_factory=list)
    rss_urls: list[str] = Field(default_factory=list)
    crawl_frequency_minutes: int = Field(default=60, ge=1)
    rate_limit_delay_seconds: float = Field(default=2.0, ge=0)
    max_concurrency: int = Field(default=2, ge=1, le=32)
    requires_browser: bool = False
    extraction_strategy: str = "selectors"
    robots_policy: str = "obey"
    source_weight: float = Field(default=1.0, ge=0)
    url_normalization: dict[str, Any] = Field(default_factory=dict)
    selectors: SelectorSetSchema | None = None

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        # SSRF guard: only public http(s) URLs can be configured as sources.
        url = HttpUrl(value)
        if url.scheme not in ("http", "https"):
            raise ValueError("base_url must be http(s)")
        return value.rstrip("/")


class SourceCreate(SourceBase):
    pass


class SourceUpdate(BaseModel):
    """PATCH payload — every field optional."""

    name: str | None = Field(default=None, max_length=200)
    base_url: str | None = None
    language: str | None = Field(default=None, max_length=8)
    country: str | None = Field(default=None, max_length=8)
    enabled: bool | None = None
    crawl_enabled: bool | None = None
    allowed_domains: list[str] | None = None
    article_url_patterns: list[str] | None = None
    section_urls: list[str] | None = None
    sitemap_urls: list[str] | None = None
    rss_urls: list[str] | None = None
    crawl_frequency_minutes: int | None = Field(default=None, ge=1)
    rate_limit_delay_seconds: float | None = Field(default=None, ge=0)
    max_concurrency: int | None = Field(default=None, ge=1, le=32)
    requires_browser: bool | None = None
    extraction_strategy: str | None = None
    robots_policy: str | None = None
    source_weight: float | None = Field(default=None, ge=0)
    url_normalization: dict[str, Any] | None = None
    selectors: SelectorSetSchema | None = None


class SourceResponse(SourceBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    last_successful_crawl_at: datetime | None
    last_error: str | None
    created_at: datetime
    updated_at: datetime
