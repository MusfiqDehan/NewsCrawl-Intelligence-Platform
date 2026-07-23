"""Article exploration + semantic search endpoints."""

import asyncio
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from newscrawl_contracts.enums import EmbeddingKind
from sqlalchemy import func, select

from newscrawl_api.api.deps import CurrentUser, DbDep, SettingsDep
from newscrawl_api.models import Article
from newscrawl_api.schemas.article import (
    ArticleDetail,
    ArticleListResponse,
    ArticleSummary,
    ScoredArticleResponse,
    SemanticSearchResponse,
)
from newscrawl_api.services.embedding_backend import get_embedding_backend
from newscrawl_api.services.search import SemanticSearchService

router = APIRouter(tags=["articles"])


@router.get("/articles", response_model=ArticleListResponse)
async def list_articles(
    db: DbDep,
    _user: CurrentUser,
    source_id: uuid.UUID | None = None,
    language: str | None = None,
    q: str | None = Query(default=None, max_length=200, description="Title substring match"),
    published_after: datetime | None = None,
    published_before: datetime | None = None,
    include_duplicates: bool = False,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ArticleListResponse:
    stmt = select(Article)
    if source_id:
        stmt = stmt.where(Article.source_id == source_id)
    if language:
        stmt = stmt.where(Article.language == language)
    if q:
        stmt = stmt.where(Article.title.ilike(f"%{q}%"))
    if published_after:
        stmt = stmt.where(Article.published_at >= published_after)
    if published_before:
        stmt = stmt.where(Article.published_at <= published_before)
    if not include_duplicates:
        stmt = stmt.where(Article.duplicate_of.is_(None))

    total = await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = (
        await db.scalars(
            stmt.order_by(Article.published_at.desc().nulls_last(), Article.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return ArticleListResponse(
        items=[ArticleSummary.model_validate(a) for a in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/articles/{article_id}", response_model=ArticleDetail)
async def get_article(article_id: uuid.UUID, db: DbDep, _user: CurrentUser) -> ArticleDetail:
    article = await db.get(Article, article_id)
    if article is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")
    return ArticleDetail.model_validate(article)


@router.get("/articles/{article_id}/similar", response_model=list[ScoredArticleResponse])
async def similar_articles(
    article_id: uuid.UUID,
    db: DbDep,
    settings: SettingsDep,
    _user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> list[ScoredArticleResponse]:
    article = await db.get(Article, article_id)
    if article is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")

    service = SemanticSearchService(settings.embedding_model, settings.embedding_version)
    results = await service.similar_to(db, article_id, limit=limit)
    if results is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Article has not been embedded yet",
        )
    return [
        ScoredArticleResponse(
            article=ArticleSummary.model_validate(r.article), similarity=round(r.similarity, 4)
        )
        for r in results
    ]


@router.get("/search/semantic", response_model=SemanticSearchResponse)
async def semantic_search(
    db: DbDep,
    settings: SettingsDep,
    _user: CurrentUser,
    q: Annotated[str, Query(min_length=2, max_length=500)],
    language: str | None = None,
    source_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> SemanticSearchResponse:
    backend = get_embedding_backend()
    # Model inference is CPU-bound — keep the event loop responsive.
    vectors = await asyncio.to_thread(backend.encode, [q])

    service = SemanticSearchService(settings.embedding_model, settings.embedding_version)
    results = await service.search(
        db,
        vectors[0],
        kind=EmbeddingKind.BODY,
        limit=limit,
        language=language,
        source_id=source_id,
    )
    return SemanticSearchResponse(
        query=q,
        results=[
            ScoredArticleResponse(
                article=ArticleSummary.model_validate(r.article),
                similarity=round(r.similarity, 4),
            )
            for r in results
        ],
    )
