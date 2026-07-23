"""Semantic search + similar-articles over pgvector embeddings.

All queries are pinned to (embedding_model, embedding_version) so a model
swap can never mix vector spaces: new vectors are written under a new
version, and search moves over only when the operator flips the setting.
"""

import uuid
from dataclasses import dataclass

from newscrawl_contracts.enums import EmbeddingKind
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from newscrawl_api.models import Article, ArticleEmbedding


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
