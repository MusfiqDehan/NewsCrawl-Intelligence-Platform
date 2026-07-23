"""Embedding storage + the semantic (final) dedup stage.

Vectors are stored per (article_id, kind, model, version) — re-running the
worker after a model swap writes new rows under the new model/version and
never silently overwrites the old space.

Semantic dedup: SimHash gray-zone candidates (Hamming 4-6) are re-judged by
body-embedding cosine similarity once vectors exist. Confirmed rewrites are
persisted but marked via articles.duplicate_of.
"""

import uuid
from dataclasses import dataclass

from newscrawl_api.models import Article, ArticleEmbedding
from newscrawl_api.services.embedding_backend import EmbeddingBackend
from newscrawl_contracts.enums import EmbeddingKind
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from newscrawl_processor.dedup import DedupService

# Cosine similarity above which two articles tell the same story.
SEMANTIC_DUPLICATE_THRESHOLD = 0.92

# How much body text feeds the embedding (BGE-M3 handles 8192 tokens; this
# keeps encoding latency predictable).
MAX_EMBED_CHARS = 6_000


@dataclass
class EmbedResult:
    kinds: list[EmbeddingKind]
    duplicate_of: uuid.UUID | None = None
    semantic_similarity: float | None = None


class EmbeddingService:
    def __init__(
        self,
        backend: EmbeddingBackend,
        *,
        version: int = 1,
        dedup: DedupService | None = None,
    ) -> None:
        self.backend = backend
        self.version = version
        self.dedup = dedup or DedupService()

    async def embed_article(
        self,
        db: AsyncSession,
        article: Article,
        kinds: list[EmbeddingKind] | None = None,
    ) -> EmbedResult:
        kinds = kinds or [EmbeddingKind.TITLE, EmbeddingKind.BODY]
        texts = {
            EmbeddingKind.TITLE: article.title,
            EmbeddingKind.SUMMARY: article.summary or "",
            EmbeddingKind.BODY: f"{article.title}\n{article.body[:MAX_EMBED_CHARS]}",
        }
        wanted = [k for k in kinds if texts.get(k)]
        vectors = self.backend.encode([texts[k] for k in wanted])

        for kind, vector in zip(wanted, vectors, strict=True):
            # Idempotent upsert of the (article, kind, model, version) slot
            await db.execute(
                delete(ArticleEmbedding).where(
                    ArticleEmbedding.article_id == article.id,
                    ArticleEmbedding.embedding_kind == kind,
                    ArticleEmbedding.embedding_model == self.backend.model_name,
                    ArticleEmbedding.embedding_version == self.version,
                )
            )
            db.add(
                ArticleEmbedding(
                    article_id=article.id,
                    embedding_kind=kind,
                    embedding_model=self.backend.model_name,
                    embedding_dimension=self.backend.dimension,
                    embedding_version=self.version,
                    embedding=vector,
                )
            )
        await db.commit()

        duplicate_of, similarity = await self._semantic_dedup(db, article)
        return EmbedResult(kinds=wanted, duplicate_of=duplicate_of, semantic_similarity=similarity)

    async def _semantic_dedup(
        self, db: AsyncSession, article: Article
    ) -> tuple[uuid.UUID | None, float | None]:
        """Judge SimHash gray-zone candidates by embedding cosine similarity."""
        if article.simhash is None or article.duplicate_of is not None:
            return article.duplicate_of, None

        near = await self.dedup.find_duplicate(
            db,
            content_hash=article.content_hash,
            simhash=article.simhash,
            exclude_article_id=article.id,
        )
        candidates = near.semantic_candidates
        if near.is_duplicate and near.duplicate_of is not None:
            # A closer duplicate appeared after this article was persisted.
            candidates = [near.duplicate_of, *candidates]
        if not candidates:
            return None, None

        own = await self._body_vector(db, article.id)
        if own is None:
            return None, None

        best_id: uuid.UUID | None = None
        best_similarity = 0.0
        for candidate_id in candidates:
            candidate_vector = await self._body_vector(db, candidate_id)
            if candidate_vector is None:
                continue
            similarity = _cosine(own, candidate_vector)
            if similarity > best_similarity:
                best_id, best_similarity = candidate_id, similarity

        if best_id is not None and best_similarity >= SEMANTIC_DUPLICATE_THRESHOLD:
            article.duplicate_of = best_id
            await db.commit()
            return best_id, best_similarity
        return None, best_similarity if best_id is not None else None

    async def _body_vector(self, db: AsyncSession, article_id: uuid.UUID) -> list[float] | None:
        vector = await db.scalar(
            select(ArticleEmbedding.embedding).where(
                ArticleEmbedding.article_id == article_id,
                ArticleEmbedding.embedding_kind == EmbeddingKind.BODY,
                ArticleEmbedding.embedding_model == self.backend.model_name,
                ArticleEmbedding.embedding_version == self.version,
            )
        )
        return list(vector) if vector is not None else None


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(dot / (norm_a * norm_b))
