"""Durable daily article-create counters (survive 24h retention deletes)."""

from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def increment_daily_article_count(
    db: AsyncSession,
    day: date | None = None,
    *,
    by: int = 1,
) -> None:
    """Bump the counter for a UTC calendar day (called on each new article)."""
    if by <= 0:
        return
    target = day or datetime.now(UTC).date()
    await db.execute(
        text(
            """
            INSERT INTO article_daily_stats (day, articles_created)
            VALUES (:day, :by)
            ON CONFLICT (day) DO UPDATE
            SET articles_created = article_daily_stats.articles_created + :by
            """
        ),
        {"day": target, "by": by},
    )


async def sync_daily_stats_from_live_articles(db: AsyncSession) -> None:
    """Ensure each day is at least as high as currently retained rows.

    Called before retention deletes so any day that never received create-time
    increments still keeps a durable chart count.
    """
    await db.execute(
        text(
            """
            INSERT INTO article_daily_stats (day, articles_created)
            SELECT created_at::date AS day, count(*)::int AS articles_created
            FROM articles
            GROUP BY 1
            ON CONFLICT (day) DO UPDATE
            SET articles_created = GREATEST(
                article_daily_stats.articles_created,
                EXCLUDED.articles_created
            )
            """
        )
    )
