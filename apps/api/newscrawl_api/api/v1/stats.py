"""Aggregated statistics for the operations dashboard."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Query
from newscrawl_contracts.enums import CrawlJobStatus
from pydantic import BaseModel
from sqlalchemy import func, select

from newscrawl_api.api.deps import CurrentUser, DbDep
from newscrawl_api.models import (
    Article,
    ArticleDailyStat,
    ArticleEntity,
    ArticleTopic,
    CrawlJob,
    CrawlUrl,
    Entity,
    LlmExtraction,
    RetentionDailyStat,
    RetentionDeleteByLanguage,
    RetentionDeleteBySource,
    RetentionPurgeCycle,
    Source,
    Topic,
)

router = APIRouter(prefix="/stats", tags=["stats"])


class OverviewResponse(BaseModel):
    total_articles: int
    articles_last_24h: int
    total_sources: int
    enabled_sources: int
    active_jobs: int
    frontier: dict[str, int]
    articles_by_language: dict[str, int]
    articles_per_day: list[dict[str, object]]
    llm_cost_usd_total: float
    llm_tokens_total: int


class TimeseriesPoint(BaseModel):
    day: str
    source_slug: str
    count: int


class TopEntityResponse(BaseModel):
    name: str
    entity_type: str
    article_count: int


class TopTopicResponse(BaseModel):
    name: str
    slug: str
    article_count: int


class SentimentBucket(BaseModel):
    sentiment: str
    count: int


class LlmDailyCost(BaseModel):
    day: str
    provider: str
    extractions: int
    total_tokens: int
    cost_usd: float


class SourceHealthResponse(BaseModel):
    source_id: uuid.UUID
    name: str
    slug: str
    language: str
    enabled: bool
    requires_browser: bool
    articles_total: int
    articles_last_24h: int
    urls_queued: int
    urls_success: int
    urls_failed: int
    last_article_at: datetime | None


@router.get("/overview", response_model=OverviewResponse)
async def overview(db: DbDep, _user: CurrentUser) -> OverviewResponse:
    now = datetime.now(UTC)
    day_ago = now - timedelta(hours=24)
    week_ago = now - timedelta(days=7)

    total_articles = await db.scalar(select(func.count(Article.id))) or 0
    articles_last_24h = (
        await db.scalar(select(func.count(Article.id)).where(Article.created_at >= day_ago)) or 0
    )
    total_sources = await db.scalar(select(func.count(Source.id))) or 0
    enabled_sources = (
        await db.scalar(select(func.count(Source.id)).where(Source.enabled.is_(True))) or 0
    )
    active_jobs = (
        await db.scalar(
            select(func.count(CrawlJob.id)).where(
                CrawlJob.status.in_([CrawlJobStatus.QUEUED, CrawlJobStatus.RUNNING])
            )
        )
        or 0
    )

    frontier_rows = (
        await db.execute(select(CrawlUrl.status, func.count()).group_by(CrawlUrl.status))
    ).all()
    frontier = {status.value: count for status, count in frontier_rows}

    language_rows = (
        (await db.execute(select(Article.language, func.count()).group_by(Article.language)))
        .tuples()
        .all()
    )
    articles_by_language: dict[str, int] = dict(language_rows)

    # Durable daily totals (survive retention deletes of the underlying articles).
    week_start = week_ago.date()
    per_day_rows = (
        await db.execute(
            select(ArticleDailyStat.day, ArticleDailyStat.articles_created)
            .where(ArticleDailyStat.day >= week_start)
            .order_by(ArticleDailyStat.day)
        )
    ).all()
    articles_per_day = [{"day": day.isoformat(), "count": count} for day, count in per_day_rows]

    llm_cost = await db.scalar(select(func.coalesce(func.sum(LlmExtraction.cost_usd), 0))) or 0
    llm_tokens = (
        await db.scalar(select(func.coalesce(func.sum(LlmExtraction.total_tokens), 0))) or 0
    )

    return OverviewResponse(
        total_articles=total_articles,
        articles_last_24h=articles_last_24h,
        total_sources=total_sources,
        enabled_sources=enabled_sources,
        active_jobs=active_jobs,
        frontier=frontier,
        articles_by_language=articles_by_language,
        articles_per_day=articles_per_day,
        llm_cost_usd_total=float(llm_cost),
        llm_tokens_total=int(llm_tokens),
    )


@router.get("/sources", response_model=list[SourceHealthResponse])
async def source_health(db: DbDep, _user: CurrentUser) -> list[SourceHealthResponse]:
    day_ago = datetime.now(UTC) - timedelta(hours=24)
    sources = (await db.scalars(select(Source).order_by(Source.name))).all()

    article_counts = dict(
        (await db.execute(select(Article.source_id, func.count()).group_by(Article.source_id)))
        .tuples()
        .all()
    )
    recent_counts = dict(
        (
            await db.execute(
                select(Article.source_id, func.count())
                .where(Article.created_at >= day_ago)
                .group_by(Article.source_id)
            )
        )
        .tuples()
        .all()
    )
    last_article = dict(
        (
            await db.execute(
                select(Article.source_id, func.max(Article.created_at)).group_by(Article.source_id)
            )
        )
        .tuples()
        .all()
    )
    url_rows = (
        await db.execute(
            select(CrawlUrl.source_id, CrawlUrl.status, func.count()).group_by(
                CrawlUrl.source_id, CrawlUrl.status
            )
        )
    ).all()
    url_counts: dict[uuid.UUID, dict[str, int]] = {}
    for source_id, status, count in url_rows:
        url_counts.setdefault(source_id, {})[status.value] = count

    result = []
    for source in sources:
        counts = url_counts.get(source.id, {})
        result.append(
            SourceHealthResponse(
                source_id=source.id,
                name=source.name,
                slug=source.slug,
                language=source.language,
                enabled=source.enabled,
                requires_browser=source.requires_browser,
                articles_total=article_counts.get(source.id, 0),
                articles_last_24h=recent_counts.get(source.id, 0),
                urls_queued=counts.get("queued", 0) + counts.get("retry_pending", 0),
                urls_success=counts.get("success", 0),
                urls_failed=counts.get("failed", 0) + counts.get("blocked", 0),
                last_article_at=last_article.get(source.id),
            )
        )
    return result


@router.get("/timeseries", response_model=list[TimeseriesPoint])
async def articles_timeseries(
    db: DbDep,
    _user: CurrentUser,
    days: Annotated[int, Query(ge=1, le=365)] = 30,
) -> list[TimeseriesPoint]:
    """Articles ingested per day per source (dashboard trend charts)."""
    since = datetime.now(UTC) - timedelta(days=days)
    day_bucket = func.date_trunc("day", Article.created_at)
    rows = (
        await db.execute(
            select(day_bucket.label("day"), Source.slug, func.count())
            .join(Source, Source.id == Article.source_id)
            .where(Article.created_at >= since)
            .group_by(day_bucket, Source.slug)
            .order_by(day_bucket)
        )
    ).all()
    return [
        TimeseriesPoint(day=day.date().isoformat(), source_slug=slug, count=count)
        for day, slug, count in rows
    ]


@router.get("/entities/top", response_model=list[TopEntityResponse])
async def top_entities(
    db: DbDep,
    _user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    entity_type: str | None = None,
) -> list[TopEntityResponse]:
    stmt = (
        select(Entity.name, Entity.entity_type, func.count(ArticleEntity.article_id))
        .join(ArticleEntity, ArticleEntity.entity_id == Entity.id)
        .group_by(Entity.id, Entity.name, Entity.entity_type)
        .order_by(func.count(ArticleEntity.article_id).desc())
        .limit(limit)
    )
    if entity_type:
        stmt = stmt.where(Entity.entity_type == entity_type)
    rows = (await db.execute(stmt)).all()
    return [
        TopEntityResponse(name=name, entity_type=etype.value, article_count=count)
        for name, etype, count in rows
    ]


@router.get("/topics/top", response_model=list[TopTopicResponse])
async def top_topics(
    db: DbDep,
    _user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[TopTopicResponse]:
    rows = (
        await db.execute(
            select(Topic.name, Topic.slug, func.count(ArticleTopic.article_id))
            .join(ArticleTopic, ArticleTopic.topic_id == Topic.id)
            .group_by(Topic.id, Topic.name, Topic.slug)
            .order_by(func.count(ArticleTopic.article_id).desc())
            .limit(limit)
        )
    ).all()
    return [
        TopTopicResponse(name=name, slug=slug, article_count=count) for name, slug, count in rows
    ]


_SENTIMENT_CANONICAL = ("positive", "negative", "neutral", "not available")


def _normalize_sentiment_label(value: str | None) -> str:
    if value is None:
        return "not available"
    key = value.strip().lower()
    if key in ("positive", "negative", "neutral"):
        return key
    return "not available"


@router.get("/sentiment", response_model=list[SentimentBucket])
async def sentiment_distribution(
    db: DbDep,
    _user: CurrentUser,
) -> list[SentimentBucket]:
    rows = (
        await db.execute(select(Article.sentiment, func.count()).group_by(Article.sentiment))
    ).all()
    totals: dict[str, int] = {label: 0 for label in _SENTIMENT_CANONICAL}
    for sentiment, count in rows:
        label = _normalize_sentiment_label(sentiment)
        totals[label] = totals.get(label, 0) + int(count)
    return [SentimentBucket(sentiment=label, count=totals[label]) for label in _SENTIMENT_CANONICAL]


@router.get("/llm/daily", response_model=list[LlmDailyCost])
async def llm_daily_costs(
    db: DbDep,
    _user: CurrentUser,
    days: Annotated[int, Query(ge=1, le=365)] = 30,
) -> list[LlmDailyCost]:
    since = datetime.now(UTC) - timedelta(days=days)
    day_bucket = func.date_trunc("day", LlmExtraction.created_at)
    rows = (
        await db.execute(
            select(
                day_bucket.label("day"),
                LlmExtraction.provider,
                func.count(),
                func.coalesce(func.sum(LlmExtraction.total_tokens), 0),
                func.coalesce(func.sum(LlmExtraction.cost_usd), 0),
            )
            .where(LlmExtraction.created_at >= since)
            .group_by(day_bucket, LlmExtraction.provider)
            .order_by(day_bucket)
        )
    ).all()
    return [
        LlmDailyCost(
            day=day.date().isoformat(),
            provider=provider,
            extractions=count,
            total_tokens=int(tokens),
            cost_usd=float(cost),
        )
        for day, provider, count, tokens, cost in rows
    ]


class RetentionCycleResponse(BaseModel):
    id: int
    started_at: datetime
    finished_at: datetime
    cutoff_at: datetime
    retention_hours: int
    articles_deleted: int
    batches: int
    raw_html_deleted: int
    by_language: dict[str, int]
    by_source: dict[str, int]
    status: str
    error_message: str | None
    duration_seconds: float


class RetentionDayPoint(BaseModel):
    day: str
    articles_deleted: int
    cycles: int
    raw_html_deleted: int


class RetentionLanguageBucket(BaseModel):
    language: str
    articles_deleted: int


class RetentionSourceBucket(BaseModel):
    source_id: uuid.UUID
    source_name: str
    source_slug: str
    articles_deleted: int


class RetentionStatsResponse(BaseModel):
    retention_hours: int
    interval_minutes: int
    total_deleted: int
    deleted_last_24h: int
    deleted_today: int
    cycles_today: int
    live_articles: int
    overdue_live_articles: int
    last_cycle_at: datetime | None
    last_cycle_deleted: int
    estimated_deleted_before_tracking: int
    deleted_per_day: list[RetentionDayPoint]
    by_language: list[RetentionLanguageBucket]
    by_source: list[RetentionSourceBucket]
    recent_cycles: list[RetentionCycleResponse]


@router.get("/retention", response_model=RetentionStatsResponse)
async def retention_stats(
    db: DbDep,
    _user: CurrentUser,
    days: Annotated[int, Query(ge=1, le=90)] = 14,
    cycle_limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> RetentionStatsResponse:
    """Deletion / retention audit for the operations dashboard."""
    from newscrawl_api.config import get_settings

    settings = get_settings()
    now = datetime.now(UTC)
    today = now.date()
    day_ago = now - timedelta(hours=24)
    since = today - timedelta(days=days - 1)

    total_deleted = (
        await db.scalar(select(func.coalesce(func.sum(RetentionDailyStat.articles_deleted), 0)))
        or 0
    )
    deleted_last_24h = (
        await db.scalar(
            select(func.coalesce(func.sum(RetentionPurgeCycle.articles_deleted), 0)).where(
                RetentionPurgeCycle.finished_at >= day_ago
            )
        )
        or 0
    )
    today_row = await db.get(RetentionDailyStat, today)
    deleted_today = today_row.articles_deleted if today_row else 0
    cycles_today = today_row.cycles if today_row else 0

    live_articles = await db.scalar(select(func.count(Article.id))) or 0
    overdue_live_articles = (
        await db.scalar(
            select(func.count(Article.id)).where(
                Article.created_at < now - timedelta(hours=settings.article_retention_hours)
            )
        )
        or 0
    )

    last_cycle = (
        await db.scalars(
            select(RetentionPurgeCycle).order_by(RetentionPurgeCycle.started_at.desc()).limit(1)
        )
    ).first()

    created_total = (
        await db.scalar(select(func.coalesce(func.sum(ArticleDailyStat.articles_created), 0))) or 0
    )
    # Anything created historically that is no longer live and not yet attributed
    # to tracked purge cycles (pre-instrumentation deletes).
    tracked_deleted = int(total_deleted)
    estimated_before = max(0, int(created_total) - int(live_articles) - tracked_deleted)

    per_day_rows = (
        await db.execute(
            select(RetentionDailyStat)
            .where(RetentionDailyStat.day >= since)
            .order_by(RetentionDailyStat.day)
        )
    ).scalars().all()
    deleted_per_day = [
        RetentionDayPoint(
            day=row.day.isoformat(),
            articles_deleted=row.articles_deleted,
            cycles=row.cycles,
            raw_html_deleted=row.raw_html_deleted,
        )
        for row in per_day_rows
    ]

    lang_rows = (
        await db.execute(
            select(
                RetentionDeleteByLanguage.language,
                func.sum(RetentionDeleteByLanguage.articles_deleted),
            )
            .where(RetentionDeleteByLanguage.day >= since)
            .group_by(RetentionDeleteByLanguage.language)
            .order_by(func.sum(RetentionDeleteByLanguage.articles_deleted).desc())
        )
    ).all()
    by_language = [
        RetentionLanguageBucket(language=lang, articles_deleted=int(count))
        for lang, count in lang_rows
    ]

    source_rows = (
        await db.execute(
            select(
                RetentionDeleteBySource.source_id,
                Source.name,
                Source.slug,
                func.sum(RetentionDeleteBySource.articles_deleted),
            )
            .join(Source, Source.id == RetentionDeleteBySource.source_id)
            .where(RetentionDeleteBySource.day >= since)
            .group_by(RetentionDeleteBySource.source_id, Source.name, Source.slug)
            .order_by(func.sum(RetentionDeleteBySource.articles_deleted).desc())
            .limit(20)
        )
    ).all()
    by_source = [
        RetentionSourceBucket(
            source_id=source_id,
            source_name=name,
            source_slug=slug,
            articles_deleted=int(count),
        )
        for source_id, name, slug, count in source_rows
    ]

    cycles = (
        await db.scalars(
            select(RetentionPurgeCycle)
            .order_by(RetentionPurgeCycle.started_at.desc())
            .limit(cycle_limit)
        )
    ).all()
    recent_cycles = [
        RetentionCycleResponse(
            id=c.id,
            started_at=c.started_at,
            finished_at=c.finished_at,
            cutoff_at=c.cutoff_at,
            retention_hours=c.retention_hours,
            articles_deleted=c.articles_deleted,
            batches=c.batches,
            raw_html_deleted=c.raw_html_deleted,
            by_language={k: int(v) for k, v in (c.by_language or {}).items()},
            by_source={k: int(v) for k, v in (c.by_source or {}).items()},
            status=c.status,
            error_message=c.error_message,
            duration_seconds=max(
                0.0, (c.finished_at - c.started_at).total_seconds()
            ),
        )
        for c in cycles
    ]

    interval_minutes = (
        settings.article_retention_interval_minutes
        if settings.article_retention_interval_minutes > 0
        else int(settings.article_retention_interval_hours * 60)
    )

    return RetentionStatsResponse(
        retention_hours=settings.article_retention_hours,
        interval_minutes=max(1, interval_minutes),
        total_deleted=int(total_deleted),
        deleted_last_24h=int(deleted_last_24h),
        deleted_today=int(deleted_today),
        cycles_today=int(cycles_today),
        live_articles=int(live_articles),
        overdue_live_articles=int(overdue_live_articles),
        last_cycle_at=last_cycle.finished_at if last_cycle else None,
        last_cycle_deleted=last_cycle.articles_deleted if last_cycle else 0,
        estimated_deleted_before_tracking=estimated_before,
        deleted_per_day=deleted_per_day,
        by_language=by_language,
        by_source=by_source,
        recent_cycles=recent_cycles,
    )
