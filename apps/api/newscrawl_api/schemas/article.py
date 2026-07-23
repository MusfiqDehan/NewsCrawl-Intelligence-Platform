"""Article API schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ArticleSummary(BaseModel):
    """List-view projection (no body)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_id: uuid.UUID
    canonical_url: str
    title: str
    subtitle: str | None
    author: str | None
    category: str | None
    language: str
    published_at: datetime | None
    summary: str | None
    word_count: int
    sentiment: str | None
    event_type: str | None
    political_category: str | None
    duplicate_of: uuid.UUID | None
    current_version: int
    created_at: datetime


class ArticleDetail(ArticleSummary):
    body: str
    image_urls: list[str]
    tags: list[str]
    content_hash: str
    extraction_confidence: float
    updated_at_source: datetime | None


class ArticleListResponse(BaseModel):
    items: list[ArticleSummary]
    total: int
    page: int
    page_size: int


class ScoredArticleResponse(BaseModel):
    article: ArticleSummary
    similarity: float


class SemanticSearchResponse(BaseModel):
    query: str
    results: list[ScoredArticleResponse]
