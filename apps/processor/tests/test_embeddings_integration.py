"""Embedding storage, model versioning, semantic dedup, and vector search
against the real database — using a deterministic fake backend (no torch)."""

import hashlib
import math
import uuid
from collections.abc import AsyncIterator

import pytest
from newscrawl_api.db import get_session_factory
from newscrawl_api.models import Article, ArticleEmbedding, Source
from newscrawl_api.services.search import SemanticSearchService
from newscrawl_contracts.enums import EmbeddingKind
from newscrawl_processor.dedup import article_simhash
from newscrawl_processor.embeddings import EmbeddingService
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration

DIM = 1024


class FakeBackend:
    """Deterministic 'embeddings': direction dominated by the first word, so
    texts starting alike are highly similar and others are not."""

    model_name = "fake-embedder"
    dimension = DIM

    def encode(self, texts: list[str]) -> list[list[float]]:
        return [self._one(t) for t in texts]

    @staticmethod
    def _one(text: str) -> list[float]:
        head = text.split()[0] if text.split() else ""
        vector = [0.0] * DIM
        head_hash = int.from_bytes(hashlib.sha256(head.encode()).digest()[:4], "big")
        vector[head_hash % DIM] = 10.0  # dominant direction from the first word
        for token in text.split()[1:32]:
            token_hash = int.from_bytes(hashlib.sha256(token.encode()).digest()[:4], "big")
            vector[token_hash % DIM] += 0.1
        norm = math.sqrt(sum(x * x for x in vector))
        return [x / norm for x in vector]


@pytest.fixture(autouse=True)
async def _engine_per_loop() -> AsyncIterator[None]:
    yield
    from newscrawl_api.db import dispose_engine

    await dispose_engine()


@pytest.fixture
async def db() -> AsyncIterator[AsyncSession]:
    factory = get_session_factory()
    async with factory() as session:
        yield session
        await session.rollback()


@pytest.fixture
async def source(db: AsyncSession) -> AsyncIterator[Source]:
    unique = uuid.uuid4().hex[:8]
    src = Source(
        name="Embed Test",
        slug=f"embed-test-{unique}",
        base_url=f"https://embed-{unique}.example.com",
        language="en",
        country="BD",
        allowed_domains=[f"embed-{unique}.example.com"],
    )
    db.add(src)
    await db.commit()
    src_id = src.id
    yield src
    await db.rollback()
    article_ids = (await db.scalars(select(Article.id).where(Article.source_id == src_id))).all()
    if article_ids:
        await db.execute(
            delete(ArticleEmbedding).where(ArticleEmbedding.article_id.in_(article_ids))
        )
        # Clear self-referencing FK before deleting
        for article_id in article_ids:
            article = await db.get(Article, article_id)
            if article is not None:
                article.duplicate_of = None
        await db.flush()
    await db.execute(delete(Article).where(Article.source_id == src_id))
    await db.execute(delete(Source).where(Source.id == src_id))
    await db.commit()


async def make_article(db: AsyncSession, source: Source, title: str, body: str) -> Article:
    article = Article(
        source_id=source.id,
        canonical_url=f"{source.base_url}/{uuid.uuid4().hex}",
        title=title,
        body=body,
        language="en",
        content_hash=hashlib.sha256(f"{title}{body}".encode()).hexdigest(),
        simhash=article_simhash(title, body),
        word_count=len(body.split()),
    )
    db.add(article)
    await db.commit()
    return article


def service(version: int = 1) -> EmbeddingService:
    return EmbeddingService(FakeBackend(), version=version)


async def test_embeddings_stored_per_kind(db: AsyncSession, source: Source) -> None:
    article = await make_article(db, source, "Flood warning issued", "River levels rose " * 30)
    result = await service().embed_article(db, article)
    assert set(result.kinds) == {EmbeddingKind.TITLE, EmbeddingKind.BODY}

    rows = (
        await db.scalars(select(ArticleEmbedding).where(ArticleEmbedding.article_id == article.id))
    ).all()
    assert len(rows) == 2
    assert all(r.embedding_model == "fake-embedder" for r in rows)
    assert all(r.embedding_dimension == DIM for r in rows)


async def test_re_embedding_same_version_is_idempotent(db: AsyncSession, source: Source) -> None:
    article = await make_article(db, source, "Flood warning issued", "River levels rose " * 30)
    await service().embed_article(db, article)
    await service().embed_article(db, article)
    count = len(
        (
            await db.scalars(
                select(ArticleEmbedding.id).where(ArticleEmbedding.article_id == article.id)
            )
        ).all()
    )
    assert count == 2


async def test_model_version_bump_keeps_old_vectors(db: AsyncSession, source: Source) -> None:
    article = await make_article(db, source, "Flood warning issued", "River levels rose " * 30)
    await service(version=1).embed_article(db, article)
    await service(version=2).embed_article(db, article)
    versions = (
        await db.scalars(
            select(ArticleEmbedding.embedding_version).where(
                ArticleEmbedding.article_id == article.id
            )
        )
    ).all()
    assert sorted(versions) == [1, 1, 2, 2]


async def test_vector_search_ranks_same_topic_first(db: AsyncSession, source: Source) -> None:
    flood = await make_article(db, source, "Flood alert", "flood waters rising in the north " * 20)
    await make_article(db, source, "Cricket final", "cricket team wins the trophy match " * 20)
    for article in (await db.scalars(select(Article).where(Article.source_id == source.id))).all():
        await service().embed_article(db, article)

    backend = FakeBackend()
    search = SemanticSearchService("fake-embedder", 1)
    results = await search.search(
        db, backend.encode(["flood waters everywhere"])[0], source_id=source.id, limit=2
    )
    assert results
    assert results[0].article.id == flood.id
    assert results[0].similarity > results[1].similarity


async def test_similar_articles(db: AsyncSession, source: Source) -> None:
    a1 = await make_article(db, source, "Flood alert", "flood waters rising in the north " * 20)
    a2 = await make_article(db, source, "Flood update", "flood waters rising in the south " * 20)
    await make_article(db, source, "Cricket final", "cricket team wins the trophy match " * 20)
    for article in (await db.scalars(select(Article).where(Article.source_id == source.id))).all():
        await service().embed_article(db, article)

    search = SemanticSearchService("fake-embedder", 1)
    results = await search.similar_to(db, a1.id, limit=2)
    assert results is not None
    assert results[0].article.id == a2.id
    assert all(r.article.id != a1.id for r in results)


async def test_similar_to_unembedded_article_returns_none(db: AsyncSession, source: Source) -> None:
    article = await make_article(db, source, "No vectors yet", "body " * 50)
    search = SemanticSearchService("fake-embedder", 1)
    assert await search.similar_to(db, article.id) is None


async def test_semantic_dedup_marks_gray_zone_rewrite(db: AsyncSession, source: Source) -> None:
    base_body = (
        "flood waters rising across the northern districts as rivers overflow their banks "
        "following three days of continuous heavy rainfall in the upstream catchment areas. "
        "authorities opened emergency shelters and moved livestock to higher ground while "
        "engineers monitored embankments for signs of erosion near the major river crossings. "
        "local officials distributed dry food and drinking water to marooned families and "
        "asked residents in low lying areas to move to designated schools and colleges. "
        "the water development board said levels at two gauging stations crossed the danger "
        "mark overnight and could remain above it for at least another seventy two hours. "
        "ferry services on the main river routes were suspended and road links to three "
        "upazilas were cut off after approach roads went under water late in the evening."
    )
    # A lightly edited republication: SimHash-close (auto-dup or gray zone),
    # and the fake backend sees nearly identical token sets → cosine ≈ 1.
    rewrite_body = base_body.replace("three days", "four days")
    original = await make_article(db, source, "Flood alert", base_body)
    rewrite = await make_article(db, source, "Flood alert", rewrite_body)

    await service().embed_article(db, original)
    result = await service().embed_article(db, rewrite)

    assert result.duplicate_of == original.id
    assert result.semantic_similarity is not None
    assert result.semantic_similarity >= 0.92
    await db.refresh(rewrite)
    assert rewrite.duplicate_of == original.id
