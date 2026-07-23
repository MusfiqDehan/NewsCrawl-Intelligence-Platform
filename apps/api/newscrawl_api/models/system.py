"""Coarse-grained platform metrics snapshots (dashboards query these; Prometheus
remains the operational metrics store)."""

from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from newscrawl_api.models.base import Base


class SystemMetric(Base):
    __tablename__ = "system_metrics"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    metric_name: Mapped[str] = mapped_column(String(200))
    value: Mapped[float]
    labels: Mapped[dict[str, Any]] = mapped_column(default=dict)
    recorded_at: Mapped[datetime] = mapped_column(server_default=text("now()"))

    __table_args__ = (Index("ix_system_metrics_name_time", "metric_name", "recorded_at"),)
