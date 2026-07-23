"""End-to-end pipeline test.

Raw page message → cleaning worker → article persisted → LLM worker (stubbed
extractor) → enrichment persisted → embedding worker (fake backend) → vector
stored → article served by the API (list, detail, similar, semantic search).

Runs against the local Postgres + Redis stack; Redis Streams are isolated on
a dedicated logical DB so real/dev queues are untouched.
"""

import hashlib
import math
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx
import pytest
from newscrawl_api.config import get_settings
from newscrawl_api.coordination import StreamQueue
from newscrawl_api.db import session_scope
from newscrawl_api.main import create_app
from newscrawl_api.models import (
    Article,
    ArticleEmbedding,
    ArticleEntity,
    ArticleTopic,
    ArticleVersion,
    Entity,
    LlmExtraction,
    ProcessingJob,
    Source,
    Topic,
)
from newscrawl_api.services.embedding_backend import set_embedding_backend
from newscrawl_contracts import RawPageMessage
from newscrawl_contracts.streams import STREAM_CLEANING, STREAM_EMBEDDING, STREAM_LLM
from newscrawl_processor.embeddings import EmbeddingService
from newscrawl_processor.llm.extractor import LlmUsage
from newscrawl_processor.llm.schema import ArticleAnalysis, ExtractedEntity
from newscrawl_processor.run_embedding_worker import EmbeddingWorker
from newscrawl_processor.run_llm_worker import LlmWorker
from newscrawl_processor.run_worker import CleaningWorker
from redis.asyncio import Redis
from sqlalchemy import delete, select

pytestmark = pytest.mark.e2e

E2E_REDIS_DB = 9
DIM = 1024

BODY = (
    "The government announced a new flood relief programme for the coastal "
    "districts on Thursday. Officials said thousands of families displaced by "
    "the rising waters will receive emergency shelter, food assistance and "
    "medical support over the coming weeks. Local volunteers have joined the "
    "relief effort, distributing supplies by boat to villages cut off from "
    "the main roads. The meteorological department warned that further "
    "rainfall is expected in the region, and asked residents in low-lying "
    "areas to move to higher ground. Opposition leaders criticised the pace "
    "of the response and demanded additional funding for embankment repairs."
)


class FakeBackend:
    """Deterministic bag-of-words embedder.

    Reports the configured model name so its vectors live in the same
    (model, version) slot the API's search service is pinned to.
    """

    model_name = get_settings().embedding_model
    dimension = DIM

    def encode(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            vector = [0.0] * DIM
            for token in text.split()[:64]:
                token_hash = int.from_bytes(hashlib.sha256(token.encode()).digest()[:4], "big")
                vector[token_hash % DIM] += 1.0
            norm = math.sqrt(sum(x * x for x in vector)) or 1.0
            vectors.append([x / norm for x in vector])
        return vectors


class StubExtractor:
    """Deterministic stand-in for the LLM provider chain."""

    async def analyze(
        self, *, title: str, body: str, language: str
    ) -> tuple[ArticleAnalysis, LlmUsage]:
        analysis = ArticleAnalysis(
            summary="Flood relief programme announced for coastal districts.",
            topics=["Flood relief", "Disaster response"],
            entities=[ExtractedEntity(name="Meteorological Department", type="organization")],
            sentiment="mixed",
            event_type="disaster",
            political_category=None,
            keywords=["flood", "relief", "coastal"],
        )
        usage = LlmUsage(
            provider="stub",
            model="stub-model",
            prompt_tokens=500,
            completion_tokens=120,
            cost_usd=0.0003,
            attempts=1,
        )
        return analysis, usage


@pytest.fixture
async def redis() -> AsyncIterator[Redis]:
    settings = get_settings()
    base = settings.redis_url.rsplit("/", 1)[0]
    client: Redis = Redis.from_url(f"{base}/{E2E_REDIS_DB}", decode_responses=True)
    await client.flushdb()
    yield client
    await client.flushdb()
    await client.aclose()


@pytest.fixture(autouse=True)
async def _engine_per_loop() -> AsyncIterator[None]:
    set_embedding_backend(FakeBackend())
    yield
    set_embedding_backend(None)
    from newscrawl_api.db import dispose_engine

    await dispose_engine()


@pytest.fixture
async def source() -> AsyncIterator[Source]:
    unique = uuid.uuid4().hex[:8]
    async with session_scope() as db:
        src = Source(
            name="E2E Test Source",
            slug=f"e2e-{unique}",
            base_url=f"https://e2e-{unique}.example.com",
            language="en",
            country="BD",
            allowed_domains=[f"e2e-{unique}.example.com"],
        )
        db.add(src)
        await db.flush()
        source_id, base_url, slug = src.id, src.base_url, src.slug
    src.id, src.base_url, src.slug = source_id, base_url, slug

    yield src

    async with session_scope() as db:
        article_ids = (
            await db.scalars(select(Article.id).where(Article.source_id == source_id))
        ).all()
        if article_ids:
            for table, column in (
                (ArticleEmbedding, ArticleEmbedding.article_id),
                (ArticleEntity, ArticleEntity.article_id),
                (ArticleTopic, ArticleTopic.article_id),
                (ArticleVersion, ArticleVersion.article_id),
                (LlmExtraction, LlmExtraction.article_id),
                (ProcessingJob, ProcessingJob.article_id),
            ):
                await db.execute(delete(table).where(column.in_(article_ids)))
            await db.execute(delete(Article).where(Article.id.in_(article_ids)))
        await db.execute(delete(Source).where(Source.id == source_id))


async def test_full_pipeline(redis: Redis, source: Source) -> None:
    queue = StreamQueue(redis, group="e2e-processors", consumer="e2e-worker")
    for stream in (STREAM_CLEANING, STREAM_LLM, STREAM_EMBEDDING):
        await queue.ensure_group(stream)

    # ── 1. Crawl plane hands off a raw page ──────────────────────────────────
    page = RawPageMessage(
        url_id=999_999_001,
        source_id=source.id,
        source_slug=source.slug,
        normalized_url=f"{source.base_url}/news/flood-relief",
        canonical_url=f"{source.base_url}/news/flood-relief",
        raw_html_location=f"s3://newscrawl-raw-html/e2e/{source.slug}.html",
        http_status=200,
        fetched_at=datetime.now(UTC),
        extracted={
            "title": "Flood relief programme announced for coastal districts",
            "body": BODY,
            "author": "Staff Correspondent",
            "published_at": "2026-07-23T06:00:00+06:00",
            "tags": ["flood", "relief"],
        },
    )
    await queue.publish(STREAM_CLEANING, page.model_dump(mode="json"))

    # ── 2. Cleaning worker persists the article and fans out ────────────────
    handled = await CleaningWorker(queue).process_batch()
    assert handled == 1

    async with session_scope() as db:
        article = await db.scalar(select(Article).where(Article.source_id == source.id))
        assert article is not None
        assert article.language == "en"
        assert article.word_count > 80
        article_id = article.id

    assert int(await redis.xlen(STREAM_LLM)) == 1
    assert int(await redis.xlen(STREAM_EMBEDDING)) == 1

    # ── 3. LLM worker enriches (stubbed provider chain) ──────────────────────
    await LlmWorker(queue, StubExtractor()).process_batch()  # type: ignore[arg-type]

    async with session_scope() as db:
        article = await db.get(Article, article_id)
        assert article is not None
        assert article.summary is not None and "relief" in article.summary.lower()
        assert article.sentiment == "mixed"
        assert article.event_type == "disaster"

        entity_names = (
            await db.scalars(
                select(Entity.name)
                .join(ArticleEntity, ArticleEntity.entity_id == Entity.id)
                .where(ArticleEntity.article_id == article_id)
            )
        ).all()
        assert "Meteorological Department" in entity_names

        topic_names = (
            await db.scalars(
                select(Topic.name)
                .join(ArticleTopic, ArticleTopic.topic_id == Topic.id)
                .where(ArticleTopic.article_id == article_id)
            )
        ).all()
        assert "Flood relief" in topic_names

        extraction = await db.scalar(
            select(LlmExtraction).where(LlmExtraction.article_id == article_id)
        )
        assert extraction is not None
        assert extraction.total_tokens == 620

    # ── 4. Embedding worker stores vectors ────────────────────────────────────
    service = EmbeddingService(FakeBackend(), version=get_settings().embedding_version)
    await EmbeddingWorker(queue, service).process_batch()

    async with session_scope() as db:
        embeddings = (
            await db.scalars(
                select(ArticleEmbedding).where(ArticleEmbedding.article_id == article_id)
            )
        ).all()
        assert len(embeddings) == 2  # title + body

    # ── 5. The API serves the article ─────────────────────────────────────────
    app = create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        async with app.router.lifespan_context(app):
            settings = get_settings()
            login = await client.post(
                "/api/v1/auth/login",
                json={"email": settings.admin_email, "password": settings.admin_password},
            )
            headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

            listing = await client.get(
                "/api/v1/articles", params={"source_id": str(source.id)}, headers=headers
            )
            assert listing.status_code == 200
            assert listing.json()["total"] == 1
            assert listing.json()["items"][0]["id"] == str(article_id)

            detail = await client.get(f"/api/v1/articles/{article_id}", headers=headers)
            assert detail.status_code == 200
            assert detail.json()["summary"] is not None
            assert detail.json()["sentiment"] == "mixed"

            search = await client.get(
                "/api/v1/search/semantic",
                params={"q": "flood relief coastal districts", "limit": 5},
                headers=headers,
            )
            assert search.status_code == 200
            result_ids = [r["article"]["id"] for r in search.json()["results"]]
            assert str(article_id) in result_ids
