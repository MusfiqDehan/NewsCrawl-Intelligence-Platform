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
    ArticleEntity,
    ArticleTopic,
    CrawlJob,
    CrawlUrl,
    Entity,
    LlmExtraction,
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

    day_bucket = func.date_trunc("day", Article.created_at)
    per_day_rows = (
        await db.execute(
            select(day_bucket.label("day"), func.count())
            .where(Article.created_at >= week_ago)
            .group_by(day_bucket)
            .order_by(day_bucket)
        )
    ).all()
    articles_per_day = [
        {"day": day.date().isoformat(), "count": count} for day, count in per_day_rows
    ]

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


@router.get("/sentiment", response_model=list[SentimentBucket])
async def sentiment_distribution(
    db: DbDep,
    _user: CurrentUser,
) -> list[SentimentBucket]:
    rows = (
        await db.execute(
            select(Article.sentiment, func.count())
            .where(Article.sentiment.is_not(None))
            .group_by(Article.sentiment)
            .order_by(func.count().desc())
        )
    ).all()
    return [SentimentBucket(sentiment=sentiment, count=count) for sentiment, count in rows]


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
