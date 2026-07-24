"""Shared article list / detail / semantic search used by auth and public APIs."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime

from fastapi import HTTPException, status
from newscrawl_contracts.enums import EmbeddingKind
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from newscrawl_api.models import Article
from newscrawl_api.observability import get_logger
from newscrawl_api.schemas.article import (
    ArticleDetail,
    ArticleListResponse,
    ArticleSummary,
    ScoredArticleResponse,
    SemanticSearchResponse,
)
from newscrawl_api.services.embedding_backend import get_embedding_backend
from newscrawl_api.services.search import SemanticSearchService, detect_query_language

log = get_logger()

# Below this cosine similarity, prefer lexical ranking over noisy neighbours.
_MIN_SEMANTIC = 0.50


async def list_articles(
    db: AsyncSession,
    *,
    source_id: uuid.UUID | None = None,
    language: str | None = None,
    q: str | None = None,
    published_after: datetime | None = None,
    published_before: datetime | None = None,
    include_duplicates: bool = False,
    page: int = 1,
    page_size: int = 20,
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


async def get_article(db: AsyncSession, article_id: uuid.UUID) -> ArticleDetail:
    article = await db.get(Article, article_id)
    if article is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")
    return ArticleDetail.model_validate(article)


async def similar_articles(
    db: AsyncSession,
    article_id: uuid.UUID,
    *,
    embedding_model: str,
    embedding_version: int,
    limit: int = 10,
) -> list[ScoredArticleResponse]:
    article = await db.get(Article, article_id)
    if article is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")

    service = SemanticSearchService(embedding_model, embedding_version)
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


async def semantic_search(
    db: AsyncSession,
    q: str,
    *,
    embedding_model: str,
    embedding_version: int,
    language: str | None = None,
    source_id: uuid.UUID | None = None,
    limit: int = 20,
) -> SemanticSearchResponse:
    # Bangla script queries must not mix in English neighbours when the vector
    # index is still English-heavy (embedding backlog).
    effective_language = language or detect_query_language(q)

    service = SemanticSearchService(embedding_model, embedding_version)
    semantic: list = []
    try:
        backend = get_embedding_backend()
        vectors = await asyncio.to_thread(backend.encode, [q])
        semantic = await service.search(
            db,
            vectors[0],
            kind=EmbeddingKind.BODY,
            limit=limit,
            language=effective_language,
            source_id=source_id,
        )
    except Exception as exc:
        # Encode server may still be loading BGE-M3; lexical still returns hits.
        log.warning("semantic_encode_unavailable", error=str(exc), query=q[:80])

    lexical = await service.lexical_search(
        db,
        q,
        limit=limit,
        language=effective_language,
        source_id=source_id,
    )
    title_hits = [r for r in lexical if r.similarity >= 1.0]
    body_hits = [r for r in lexical if r.similarity < 1.0]
    strong_semantic = [r for r in semantic if r.similarity >= _MIN_SEMANTIC]

    if not strong_semantic:
        results = (title_hits + body_hits)[:limit]
    else:
        seen: set[uuid.UUID] = set()
        results = []
        for group in (title_hits, strong_semantic, body_hits):
            for item in group:
                if item.article.id in seen:
                    continue
                seen.add(item.article.id)
                results.append(item)
                if len(results) >= limit:
                    break
            if len(results) >= limit:
                break

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
