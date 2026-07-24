"""Article exploration + semantic search endpoints (authenticated)."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query

from newscrawl_api.api.deps import CurrentUser, DbDep, SettingsDep
from newscrawl_api.schemas.article import (
    ArticleDetail,
    ArticleListResponse,
    ScoredArticleResponse,
    SemanticSearchResponse,
)
from newscrawl_api.services import article_query

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
    return await article_query.list_articles(
        db,
        source_id=source_id,
        language=language,
        q=q,
        published_after=published_after,
        published_before=published_before,
        include_duplicates=include_duplicates,
        page=page,
        page_size=page_size,
    )


@router.get("/articles/{article_id}", response_model=ArticleDetail)
async def get_article(article_id: uuid.UUID, db: DbDep, _user: CurrentUser) -> ArticleDetail:
    return await article_query.get_article(db, article_id)


@router.get("/articles/{article_id}/similar", response_model=list[ScoredArticleResponse])
async def similar_articles(
    article_id: uuid.UUID,
    db: DbDep,
    settings: SettingsDep,
    _user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> list[ScoredArticleResponse]:
    return await article_query.similar_articles(
        db,
        article_id,
        embedding_model=settings.embedding_model,
        embedding_version=settings.embedding_version,
        limit=limit,
    )


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
    return await article_query.semantic_search(
        db,
        q,
        embedding_model=settings.embedding_model,
        embedding_version=settings.embedding_version,
        language=language,
        source_id=source_id,
        limit=limit,
    )
