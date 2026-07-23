"""Processing plane tables: processing jobs and LLM extraction records."""

import uuid
from datetime import datetime
from typing import Any

from newscrawl_contracts.enums import ProcessingStage, ProcessingStatus
from sqlalchemy import BigInteger, ForeignKey, Index, Numeric, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from newscrawl_api.models.base import Base, str_enum, uuid_pk


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"

    id: Mapped[uuid.UUID] = uuid_pk()
    stage: Mapped[ProcessingStage] = mapped_column(str_enum(ProcessingStage))
    status: Mapped[ProcessingStatus] = mapped_column(
        str_enum(ProcessingStatus), default=ProcessingStatus.PENDING
    )
    article_id: Mapped[uuid.UUID | None] = mapped_column(default=None, index=True)
    url_id: Mapped[int | None] = mapped_column(BigInteger, default=None)
    # Redis stream message id for traceability
    message_id: Mapped[str | None] = mapped_column(String(100), default=None)
    attempts: Mapped[int] = mapped_column(default=0)
    last_error: Mapped[str | None] = mapped_column(Text, default=None)
    enqueued_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    started_at: Mapped[datetime | None] = mapped_column(default=None)
    completed_at: Mapped[datetime | None] = mapped_column(default=None)

    __table_args__ = (Index("ix_processing_jobs_stage_status", "stage", "status"),)


class LlmExtraction(Base):
    __tablename__ = "llm_extractions"

    id: Mapped[uuid.UUID] = uuid_pk()
    article_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("articles.id"), index=True)
    provider: Mapped[str] = mapped_column(String(50))
    model: Mapped[str] = mapped_column(String(100))
    status: Mapped[ProcessingStatus] = mapped_column(str_enum(ProcessingStatus))
    # Validated structured payload (topics, entities, sentiment, claims, ...)
    extraction: Mapped[dict[str, Any]] = mapped_column(default=dict)
    prompt_tokens: Mapped[int] = mapped_column(default=0)
    completion_tokens: Mapped[int] = mapped_column(default=0)
    total_tokens: Mapped[int] = mapped_column(default=0)
    cost_usd: Mapped[float] = mapped_column(Numeric(12, 6), default=0)
    latency_ms: Mapped[int | None] = mapped_column(default=None)
    error: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
