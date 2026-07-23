"""LLM analysis persistence: article enrichment, entities, topics, cost rows."""

import uuid
from collections.abc import AsyncIterator

import pytest
from newscrawl_api.db import get_session_factory
from newscrawl_api.models import (
    Article,
    ArticleEntity,
    ArticleTopic,
    Entity,
    LlmExtraction,
    Source,
)
from newscrawl_contracts.enums import ProcessingStatus
from newscrawl_processor.llm.extractor import LlmUsage
from newscrawl_processor.llm.persist import apply_analysis, record_failure, topic_slug
from newscrawl_processor.llm.schema import ArticleAnalysis
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration


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
async def article(db: AsyncSession) -> AsyncIterator[Article]:
    unique = uuid.uuid4().hex[:8]
    source = Source(
        name="LLM Test",
        slug=f"llm-test-{unique}",
        base_url=f"https://llm-{unique}.example.com",
        language="en",
        country="BD",
        allowed_domains=[f"llm-{unique}.example.com"],
    )
    db.add(source)
    await db.flush()
    art = Article(
        source_id=source.id,
        canonical_url=f"{source.base_url}/story",
        title="Policy announced",
        body="Body text. " * 50,
        language="en",
        content_hash=uuid.uuid4().hex + uuid.uuid4().hex,
        word_count=100,
    )
    db.add(art)
    await db.commit()
    art_id, source_id = art.id, source.id
    yield art
    await db.rollback()
    await db.execute(delete(LlmExtraction).where(LlmExtraction.article_id == art_id))
    await db.execute(delete(ArticleEntity).where(ArticleEntity.article_id == art_id))
    await db.execute(delete(ArticleTopic).where(ArticleTopic.article_id == art_id))
    await db.execute(delete(Article).where(Article.id == art_id))
    await db.execute(delete(Source).where(Source.id == source_id))
    await db.commit()


def analysis(**overrides: object) -> ArticleAnalysis:
    payload: dict[str, object] = {
        "summary": "A new policy was announced by the finance ministry on Thursday.",
        "topics": ["Economy", "  economy ", "Fiscal Policy"],
        "entities": [
            {"name": "Ministry of Finance", "type": "organization"},
            {"name": "ministry of finance", "type": "organization"},  # dup, case
            {"name": "Dhaka", "type": "location"},
        ],
        "sentiment": "neutral",
        "event_type": "policy announcement",
        "political_category": "governance",
        "keywords": ["policy"],
    }
    payload.update(overrides)
    return ArticleAnalysis.model_validate(payload)


def usage() -> LlmUsage:
    u = LlmUsage(provider="gemini", model="gemini-2.5-flash")
    u.prompt_tokens = 1200
    u.completion_tokens = 300
    u.cost_usd = 0.00111
    u.attempts = 1
    return u


async def test_analysis_enriches_article_and_links(db: AsyncSession, article: Article) -> None:
    await apply_analysis(db, article, analysis(), usage(), latency_ms=850)

    assert article.sentiment == "neutral"
    assert article.event_type == "policy announcement"
    assert article.summary is not None and article.summary.startswith("A new policy")

    entity_links = (
        await db.scalars(select(ArticleEntity).where(ArticleEntity.article_id == article.id))
    ).all()
    assert len(entity_links) == 2  # case-duplicate collapsed

    topic_links = (
        await db.scalars(select(ArticleTopic).where(ArticleTopic.article_id == article.id))
    ).all()
    assert len(topic_links) == 2  # "Economy" and "economy" collapse to one slug

    extraction = await db.scalar(
        select(LlmExtraction).where(LlmExtraction.article_id == article.id)
    )
    assert extraction is not None
    assert extraction.status == ProcessingStatus.COMPLETED
    assert extraction.total_tokens == 1500
    assert float(extraction.cost_usd) == pytest.approx(0.00111)
    assert extraction.latency_ms == 850


async def test_publisher_summary_is_kept(db: AsyncSession, article: Article) -> None:
    article.summary = "Publisher-provided standfirst."
    await db.commit()
    await apply_analysis(db, article, analysis(), usage())
    assert article.summary == "Publisher-provided standfirst."


async def test_reanalysis_does_not_duplicate_links(db: AsyncSession, article: Article) -> None:
    await apply_analysis(db, article, analysis(), usage())
    await apply_analysis(db, article, analysis(), usage())

    entity_links = (
        await db.scalars(select(ArticleEntity).where(ArticleEntity.article_id == article.id))
    ).all()
    assert len(entity_links) == 2
    extractions = (
        await db.scalars(select(LlmExtraction).where(LlmExtraction.article_id == article.id))
    ).all()
    assert len(extractions) == 2  # audit rows accumulate; links don't


async def test_entities_shared_across_articles(db: AsyncSession, article: Article) -> None:
    await apply_analysis(db, article, analysis(), usage())
    dhaka = await db.scalar(select(Entity).where(Entity.normalized_name == "dhaka"))
    assert dhaka is not None


async def test_failure_recorded_with_partial_usage(db: AsyncSession, article: Article) -> None:
    failed_usage = usage()
    await record_failure(db, article, failed_usage, error="All providers failed", latency_ms=5000)
    extraction = await db.scalar(
        select(LlmExtraction).where(LlmExtraction.article_id == article.id)
    )
    assert extraction is not None
    assert extraction.status == ProcessingStatus.FAILED
    assert extraction.error == "All providers failed"
    assert extraction.total_tokens == 1500


class TestTopicSlug:
    def test_english(self) -> None:
        assert topic_slug("Fiscal Policy") == "fiscal-policy"

    def test_bangla_preserved(self) -> None:
        assert topic_slug("অর্থনীতি") == "অর্থনীতি"

    def test_punctuation_stripped(self) -> None:
        assert topic_slug("U.S. — Bangladesh relations!") == "us-bangladesh-relations"
