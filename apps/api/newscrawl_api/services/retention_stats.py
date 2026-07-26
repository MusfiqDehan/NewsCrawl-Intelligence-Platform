"""Record retention purge outcomes for the deletion-stats dashboard."""

from __future__ import annotations

import json
import uuid
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from newscrawl_api.models.retention import RetentionPurgeCycle


def _merge_counts(existing: dict[str, Any] | None, incoming: dict[str, int]) -> dict[str, int]:
    merged: dict[str, int] = {str(k): int(v) for k, v in (existing or {}).items()}
    for key, value in incoming.items():
        merged[str(key)] = merged.get(str(key), 0) + int(value)
    return merged


async def record_purge_cycle(
    db: AsyncSession,
    *,
    started_at: datetime,
    finished_at: datetime,
    cutoff_at: datetime,
    retention_hours: int,
    articles_deleted: int,
    batches: int,
    raw_html_deleted: int,
    by_language: dict[str, int],
    by_source: dict[str, int],
    status: str = "completed",
    error_message: str | None = None,
) -> RetentionPurgeCycle:
    """Persist a cycle row plus daily / language / source rollups."""
    cycle = RetentionPurgeCycle(
        started_at=started_at,
        finished_at=finished_at,
        cutoff_at=cutoff_at,
        retention_hours=retention_hours,
        articles_deleted=articles_deleted,
        batches=batches,
        raw_html_deleted=raw_html_deleted,
        by_language=dict(by_language),
        by_source=dict(by_source),
        status=status,
        error_message=error_message,
    )
    db.add(cycle)

    day = finished_at.astimezone(UTC).date() if finished_at.tzinfo else finished_at.date()

    await db.execute(
        text(
            """
            INSERT INTO retention_daily_stats
                (day, articles_deleted, cycles, raw_html_deleted, by_language, by_source)
            VALUES
                (:day, :deleted, 1, :raw_html, '{}'::jsonb, '{}'::jsonb)
            ON CONFLICT (day) DO UPDATE SET
                articles_deleted = retention_daily_stats.articles_deleted + EXCLUDED.articles_deleted,
                cycles = retention_daily_stats.cycles + 1,
                raw_html_deleted = retention_daily_stats.raw_html_deleted + EXCLUDED.raw_html_deleted
            """
        ),
        {"day": day, "deleted": articles_deleted, "raw_html": raw_html_deleted},
    )

    row = (
        await db.execute(
            text(
                "SELECT by_language, by_source FROM retention_daily_stats WHERE day = :day FOR UPDATE"
            ),
            {"day": day},
        )
    ).mappings().one()
    await db.execute(
        text(
            """
            UPDATE retention_daily_stats
            SET by_language = CAST(:by_lang AS jsonb),
                by_source = CAST(:by_src AS jsonb)
            WHERE day = :day
            """
        ),
        {
            "day": day,
            "by_lang": json.dumps(_merge_counts(row["by_language"], by_language)),
            "by_src": json.dumps(_merge_counts(row["by_source"], by_source)),
        },
    )

    for language, count in by_language.items():
        if count <= 0:
            continue
        await db.execute(
            text(
                """
                INSERT INTO retention_delete_by_language (day, language, articles_deleted)
                VALUES (:day, :language, :count)
                ON CONFLICT (day, language) DO UPDATE
                SET articles_deleted = retention_delete_by_language.articles_deleted + :count
                """
            ),
            {"day": day, "language": language, "count": int(count)},
        )

    for source_id, count in by_source.items():
        if count <= 0:
            continue
        await db.execute(
            text(
                """
                INSERT INTO retention_delete_by_source (day, source_id, articles_deleted)
                VALUES (:day, CAST(:source_id AS uuid), :count)
                ON CONFLICT (day, source_id) DO UPDATE
                SET articles_deleted = retention_delete_by_source.articles_deleted + :count
                """
            ),
            {"day": day, "source_id": str(source_id), "count": int(count)},
        )

    await db.flush()
    return cycle


def tally_batch(
    languages: list[str],
    source_ids: list[uuid.UUID],
) -> tuple[Counter[str], Counter[str]]:
    return Counter(languages), Counter(str(sid) for sid in source_ids)
