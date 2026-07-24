"""Unauthenticated article browse + semantic search for the public explore UI."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query

from newscrawl_api.api.deps import DbDep, SettingsDep
from newscrawl_api.schemas.article import (
    ArticleDetail,
    ArticleListResponse,
    ScoredArticleResponse,
    SemanticSearchResponse,
)
from newscrawl_api.services import article_query

router = APIRouter(prefix="/public", tags=["public"])


@router.get("/articles", response_model=ArticleListResponse)
async def public_list_articles(
    db: DbDep,
    language: str | None = Query(default=None, pattern="^(bn|en)$"),
    q: str | None = Query(default=None, max_length=200, description="Title substring match"),
    published_after: datetime | None = None,
    published_before: datetime | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
) -> ArticleListResponse:
    return await article_query.list_articles(
        db,
        language=language,
        q=q,
        published_after=published_after,
        published_before=published_before,
        include_duplicates=False,
        page=page,
        page_size=page_size,
    )


@router.get("/articles/{article_id}", response_model=ArticleDetail)
async def public_get_article(article_id: uuid.UUID, db: DbDep) -> ArticleDetail:
    return await article_query.get_article(db, article_id)


@router.get("/articles/{article_id}/similar", response_model=list[ScoredArticleResponse])
async def public_similar_articles(
    article_id: uuid.UUID,
    db: DbDep,
    settings: SettingsDep,
    limit: Annotated[int, Query(ge=1, le=20)] = 10,
) -> list[ScoredArticleResponse]:
    return await article_query.similar_articles(
        db,
        article_id,
        embedding_model=settings.embedding_model,
        embedding_version=settings.embedding_version,
        limit=limit,
    )


@router.get("/search/semantic", response_model=SemanticSearchResponse)
async def public_semantic_search(
    db: DbDep,
    settings: SettingsDep,
    q: Annotated[str, Query(min_length=2, max_length=500)],
    language: str | None = Query(default=None, pattern="^(bn|en)$"),
    limit: Annotated[int, Query(ge=1, le=30)] = 20,
) -> SemanticSearchResponse:
    return await article_query.semantic_search(
        db,
        q,
        embedding_model=settings.embedding_model,
        embedding_version=settings.embedding_version,
        language=language,
        limit=limit,
    )
