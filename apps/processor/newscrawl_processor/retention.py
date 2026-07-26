"""Delete articles older than the configured retention window.

Clears dependent rows first (no ON DELETE CASCADE), best-effort removes raw
HTML from object storage, then deletes the article rows in batches.
Every cycle is recorded for the deletion-stats dashboard.
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

import boto3
from botocore.config import Config as BotoConfig
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from newscrawl_api.config import Settings
from newscrawl_api.models import (
    Article,
    ArticleEmbedding,
    ArticleEntity,
    ArticleTopic,
    ArticleVersion,
    LlmExtraction,
    ProcessingJob,
)
from newscrawl_api.observability import get_logger
from newscrawl_api.services.article_daily_stats import sync_daily_stats_from_live_articles
from newscrawl_api.services.retention_stats import record_purge_cycle, tally_batch

log = get_logger()

_S3_URI = re.compile(r"^s3://([^/]+)/(.+)$")


def parse_s3_uri(location: str) -> tuple[str, str] | None:
    match = _S3_URI.match(location.strip())
    if not match:
        return None
    return match.group(1), match.group(2)


def _s3_client(settings: Settings) -> Any:
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region,
        config=BotoConfig(connect_timeout=10, read_timeout=30, retries={"max_attempts": 3}),
    )


def delete_raw_html_objects(settings: Settings, locations: list[str]) -> int:
    """Best-effort delete of s3:// URIs. Returns number of delete attempts."""
    keys_by_bucket: dict[str, list[str]] = {}
    for location in locations:
        if not location:
            continue
        parsed = parse_s3_uri(location)
        if parsed is None:
            # Also accept bare keys under the configured bucket.
            if location.startswith("http://") or location.startswith("https://"):
                path = urlparse(location).path.lstrip("/")
                if "/" in path:
                    bucket, _, key = path.partition("/")
                    keys_by_bucket.setdefault(bucket, []).append(key)
                continue
            keys_by_bucket.setdefault(settings.s3_bucket_raw_html, []).append(location)
            continue
        bucket, key = parsed
        keys_by_bucket.setdefault(bucket, []).append(key)

    if not keys_by_bucket:
        return 0

    client = _s3_client(settings)
    deleted = 0
    for bucket, keys in keys_by_bucket.items():
        for i in range(0, len(keys), 1000):
            chunk = keys[i : i + 1000]
            try:
                client.delete_objects(
                    Bucket=bucket,
                    Delete={"Objects": [{"Key": k} for k in chunk], "Quiet": True},
                )
                deleted += len(chunk)
            except Exception as exc:  # noqa: BLE001 — retention must not fail on S3 noise
                log.warning("raw_html_delete_failed", bucket=bucket, error=str(exc), count=len(chunk))
    return deleted


async def purge_expired_articles(
    db: AsyncSession,
    settings: Settings,
    *,
    retention_hours: int | None = None,
    batch_size: int = 200,
    max_batches: int = 500,
) -> int:
    """Delete articles with created_at older than retention_hours. Returns deleted count."""
    hours = retention_hours if retention_hours is not None else settings.article_retention_hours
    started_at = datetime.now(UTC)
    cutoff = started_at - timedelta(hours=hours)
    total_deleted = 0
    batches = 0
    raw_html_deleted = 0
    by_language: Counter[str] = Counter()
    by_source: Counter[str] = Counter()
    status = "completed"
    error_message: str | None = None

    try:
        # Snapshot live day totals into durable stats before rows disappear.
        await sync_daily_stats_from_live_articles(db)
        await db.commit()

        for _ in range(max_batches):
            rows = (
                await db.execute(
                    select(
                        Article.id,
                        Article.raw_html_location,
                        Article.language,
                        Article.source_id,
                    )
                    .where(Article.created_at < cutoff)
                    .order_by(Article.created_at.asc())
                    .limit(batch_size)
                )
            ).all()
            if not rows:
                break

            article_ids = [row.id for row in rows]
            locations = [row.raw_html_location for row in rows if row.raw_html_location]
            lang_counts, src_counts = tally_batch(
                [row.language for row in rows],
                [row.source_id for row in rows],
            )
            by_language.update(lang_counts)
            by_source.update(src_counts)

            # Break self-FK references from articles that may still be retained.
            await db.execute(
                update(Article)
                .where(Article.duplicate_of.in_(article_ids))
                .values(duplicate_of=None)
            )

            for table, column in (
                (ArticleEmbedding, ArticleEmbedding.article_id),
                (ArticleEntity, ArticleEntity.article_id),
                (ArticleTopic, ArticleTopic.article_id),
                (ArticleVersion, ArticleVersion.article_id),
                (LlmExtraction, LlmExtraction.article_id),
                (ProcessingJob, ProcessingJob.article_id),
            ):
                await db.execute(delete(table).where(column.in_(article_ids)))

            await db.execute(delete(Article).where(Article.id.in_(article_ids)))
            await db.commit()

            if locations:
                raw_html_deleted += delete_raw_html_objects(settings, locations)

            batches += 1
            total_deleted += len(article_ids)
            log.info(
                "retention_batch_deleted",
                deleted=len(article_ids),
                cutoff=cutoff.isoformat(),
                total=total_deleted,
            )
    except Exception as exc:
        status = "error"
        error_message = f"{type(exc).__name__}: {exc}"
        log.exception("retention_purge_failed")
        raise
    finally:
        finished_at = datetime.now(UTC)
        try:
            await db.rollback()
            await record_purge_cycle(
                db,
                started_at=started_at,
                finished_at=finished_at,
                cutoff_at=cutoff,
                retention_hours=hours,
                articles_deleted=total_deleted,
                batches=batches,
                raw_html_deleted=raw_html_deleted,
                by_language=dict(by_language),
                by_source=dict(by_source),
                status=status,
                error_message=error_message,
            )
            await db.commit()
        except Exception:
            log.exception("retention_stats_record_failed")
            await db.rollback()

    return total_deleted
