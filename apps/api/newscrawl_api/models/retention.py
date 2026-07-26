"""Durable retention / deletion audit tables.

Article rows older than 24h are purged; these tables keep the operational
history so the dashboard can show how many were deleted, when, and by whom
(language / source breakdowns).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import BigInteger, Date, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from newscrawl_api.models.base import Base


class RetentionPurgeCycle(Base):
    """One retention worker purge cycle (may span multiple DB batches)."""

    __tablename__ = "retention_purge_cycles"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    started_at: Mapped[datetime]
    finished_at: Mapped[datetime]
    cutoff_at: Mapped[datetime]
    retention_hours: Mapped[int] = mapped_column(Integer)
    articles_deleted: Mapped[int] = mapped_column(Integer, default=0)
    batches: Mapped[int] = mapped_column(Integer, default=0)
    raw_html_deleted: Mapped[int] = mapped_column(Integer, default=0)
    by_language: Mapped[dict[str, Any]] = mapped_column(default=dict)
    by_source: Mapped[dict[str, Any]] = mapped_column(default=dict)
    status: Mapped[str] = mapped_column(String(32), default="completed")
    error_message: Mapped[str | None] = mapped_column(Text, default=None)

    __table_args__ = (Index("ix_retention_purge_cycles_started_at", "started_at"),)


class RetentionDailyStat(Base):
    """Articles deleted per UTC calendar day (deletion day, not crawl day)."""

    __tablename__ = "retention_daily_stats"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    articles_deleted: Mapped[int] = mapped_column(Integer, default=0)
    cycles: Mapped[int] = mapped_column(Integer, default=0)
    raw_html_deleted: Mapped[int] = mapped_column(Integer, default=0)
    by_language: Mapped[dict[str, Any]] = mapped_column(default=dict)
    by_source: Mapped[dict[str, Any]] = mapped_column(default=dict)


class RetentionDeleteByLanguage(Base):
    """Cumulative language breakdown of deleted articles (all time + daily rollups)."""

    __tablename__ = "retention_delete_by_language"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    language: Mapped[str] = mapped_column(String(8), primary_key=True)
    articles_deleted: Mapped[int] = mapped_column(Integer, default=0)


class RetentionDeleteBySource(Base):
    """Cumulative source breakdown of deleted articles."""

    __tablename__ = "retention_delete_by_source"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sources.id"), primary_key=True)
    articles_deleted: Mapped[int] = mapped_column(Integer, default=0)
