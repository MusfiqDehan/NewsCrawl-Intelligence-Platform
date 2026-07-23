"""Crawl job API schemas."""

import uuid
from datetime import datetime
from typing import Any

from newscrawl_contracts.enums import CrawlJobStatus, CrawlJobType
from pydantic import BaseModel, ConfigDict, Field


class CrawlJobCreate(BaseModel):
    source_id: uuid.UUID
    job_type: CrawlJobType
    priority: int = Field(default=0, ge=-100, le=100)
    params: dict[str, Any] = Field(default_factory=dict)


class CrawlJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_id: uuid.UUID
    job_type: CrawlJobType
    status: CrawlJobStatus
    priority: int
    params: dict[str, Any]
    created_by: uuid.UUID | None

    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None

    pages_discovered: int
    pages_requested: int
    pages_successful: int
    pages_failed: int
    pages_skipped: int
    pages_changed: int
    pages_unchanged: int
    error_count: int
    last_error: str | None


class CrawlJobListResponse(BaseModel):
    items: list[CrawlJobResponse]
    total: int
    limit: int
    offset: int
