"""Semantic search + similar-articles over pgvector embeddings.

All queries are pinned to (embedding_model, embedding_version) so a model
swap can never mix vector spaces: new vectors are written under a new
version, and search moves over only when the operator flips the setting.
"""

import re
import uuid
from dataclasses import dataclass

from newscrawl_contracts.enums import EmbeddingKind
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from newscrawl_api.models import Article, ArticleEmbedding

# Bengali / Bangla script (plus common Bangla digits/marks in the same block).
_BANGLA_CHARS = re.compile(r"[\u0980-\u09FF]")
_LATIN_CHARS = re.compile(r"[A-Za-z]")


def detect_query_language(query: str) -> str | None:
    """Infer bn/en from script when the caller does not pass an explicit filter."""
    bangla = len(_BANGLA_CHARS.findall(query))
    latin = len(_LATIN_CHARS.findall(query))
    if bangla >= 2 and bangla >= latin:
        return "bn"
    if latin >= 2 and latin > bangla:
        return "en"
    return None


@dataclass
class ScoredArticle:
    article: Article
    similarity: float


class SemanticSearchService:
    def __init__(self, model: str, version: int) -> None:
        self.model = model
        self.version = version

    async def search(
        self,
        db: AsyncSession,
        query_vector: list[float],
        *,
        kind: EmbeddingKind = EmbeddingKind.BODY,
        limit: int = 20,
        language: str | None = None,
        source_id: uuid.UUID | None = None,
        include_duplicates: bool = False,
    ) -> list[ScoredArticle]:
        distance = ArticleEmbedding.embedding.cosine_distance(query_vector)
        stmt = (
            select(Article, distance.label("distance"))
            .join(ArticleEmbedding, ArticleEmbedding.article_id == Article.id)
            .where(
                ArticleEmbedding.embedding_kind == kind,
                ArticleEmbedding.embedding_model == self.model,
                ArticleEmbedding.embedding_version == self.version,
            )
            .order_by(distance)
            .limit(limit)
        )
        if language:
            stmt = stmt.where(Article.language == language)
        if source_id:
            stmt = stmt.where(Article.source_id == source_id)
        if not include_duplicates:
            stmt = stmt.where(Article.duplicate_of.is_(None))

        rows = (await db.execute(stmt)).all()
        return [
            ScoredArticle(article=article, similarity=1.0 - float(dist)) for article, dist in rows
        ]

    async def lexical_search(
        self,
        db: AsyncSession,
        query: str,
        *,
        limit: int = 20,
        language: str | None = None,
        source_id: uuid.UUID | None = None,
        include_duplicates: bool = False,
    ) -> list[ScoredArticle]:
        """Substring match on title/body — used when vector coverage is thin
        for a language (e.g. Bangla still waiting on the embedding backlog)."""
        pattern = f"%{query.strip()}%"
        # Prefer title hits; only fall back to body when the title has no matches
        # so long related articles do not drown out the exact headline matches.
        title_stmt = (
            select(Article)
            .where(Article.title.ilike(pattern))
            .order_by(Article.published_at.desc().nulls_last(), Article.created_at.desc())
            .limit(limit)
        )
        if language:
            title_stmt = title_stmt.where(Article.language == language)
        if source_id:
            title_stmt = title_stmt.where(Article.source_id == source_id)
        if not include_duplicates:
            title_stmt = title_stmt.where(Article.duplicate_of.is_(None))

        title_hits = list((await db.scalars(title_stmt)).all())
        if len(title_hits) >= limit:
            return [ScoredArticle(article=a, similarity=1.0) for a in title_hits[:limit]]

        remaining = limit - len(title_hits)
        seen = {a.id for a in title_hits}
        body_stmt = (
            select(Article)
            .where(Article.body.ilike(pattern))
            .order_by(Article.published_at.desc().nulls_last(), Article.created_at.desc())
            .limit(remaining)
        )
        if seen:
            body_stmt = body_stmt.where(Article.id.notin_(seen))
        if language:
            body_stmt = body_stmt.where(Article.language == language)
        if source_id:
            body_stmt = body_stmt.where(Article.source_id == source_id)
        if not include_duplicates:
            body_stmt = body_stmt.where(Article.duplicate_of.is_(None))

        body_hits = list((await db.scalars(body_stmt)).all())
        return (
            [ScoredArticle(article=a, similarity=1.0) for a in title_hits]
            + [ScoredArticle(article=a, similarity=0.85) for a in body_hits]
        )

    async def similar_to(
        self,
        db: AsyncSession,
        article_id: uuid.UUID,
        *,
        kind: EmbeddingKind = EmbeddingKind.BODY,
        limit: int = 10,
    ) -> list[ScoredArticle] | None:
        """Nearest neighbours of an existing article; None when the article
        has no embedding yet."""
        vector = await db.scalar(
            select(ArticleEmbedding.embedding).where(
                ArticleEmbedding.article_id == article_id,
                ArticleEmbedding.embedding_kind == kind,
                ArticleEmbedding.embedding_model == self.model,
                ArticleEmbedding.embedding_version == self.version,
            )
        )
        if vector is None:
            return None
        results = await self.search(
            db, list(vector), kind=kind, limit=limit + 1, include_duplicates=True
        )
        return [r for r in results if r.article.id != article_id][:limit]
