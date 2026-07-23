"""Queue message contracts (Redis Streams payloads).

Every message crossing a plane boundary is validated against these models on
both the producer and consumer side.
"""

import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, Field

from newscrawl_contracts.enums import EmbeddingKind, ProcessingStage


class QueueMessage(BaseModel):
    message_version: int = 1
    enqueued_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RawPageMessage(QueueMessage):
    """Crawler → processing:cleaning — a fetched page ready for processing."""

    url_id: int
    source_id: uuid.UUID
    source_slug: str
    crawl_job_id: uuid.UUID | None = None
    normalized_url: str
    canonical_url: str | None = None
    raw_html_location: str
    http_status: int
    fetched_at: datetime
    # Pre-extracted by the spider (selectors run inside the crawl plane;
    # cleaning/validation happens in the processing plane).
    extracted: dict[str, object] = Field(default_factory=dict)


class LlmExtractionMessage(QueueMessage):
    """processing:cleaning → processing:llm — an article ready for LLM extraction."""

    article_id: uuid.UUID
    language: str


class EmbeddingMessage(QueueMessage):
    """→ processing:embedding — an article needing (re-)embedding."""

    article_id: uuid.UUID
    kinds: list[EmbeddingKind] = Field(
        default_factory=lambda: [EmbeddingKind.TITLE, EmbeddingKind.BODY]
    )


class DeadLetterMessage(QueueMessage):
    """Any stage → processing:dead-letter — a message that exhausted retries."""

    stage: ProcessingStage
    original_payload: dict[str, object]
    error: str
    attempts: int
