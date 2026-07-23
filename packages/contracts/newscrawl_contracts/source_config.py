"""Source configuration snapshot passed from the control plane to crawl workers.

The crawler never queries the sources table directly during a crawl — it
receives an immutable snapshot when the spider is scheduled, so a mid-crawl
config change can never produce a half-old/half-new crawl.
"""

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SourceConfig(BaseModel):
    model_config = ConfigDict(frozen=True, from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    base_url: str
    language: str
    country: str
    allowed_domains: list[str] = Field(default_factory=list)
    article_url_patterns: list[str] = Field(default_factory=list)
    section_urls: list[str] = Field(default_factory=list)
    sitemap_urls: list[str] = Field(default_factory=list)
    rss_urls: list[str] = Field(default_factory=list)
    crawl_frequency_minutes: int = 60
    rate_limit_delay_seconds: float = 2.0
    max_concurrency: int = 2
    requires_browser: bool = False
    extraction_strategy: str = "selectors"
    robots_policy: str = "obey"
    source_weight: float = 1.0
    url_normalization: dict[str, Any] = Field(default_factory=dict)
