"""Stats/analytics endpoints + Prometheus metrics (real Postgres + Redis)."""

import hashlib
import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from newscrawl_api.main import create_app

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
async def _engine_per_loop() -> AsyncIterator[None]:
    yield
    from newscrawl_api.db import dispose_engine

    await dispose_engine()


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    app = create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as test_client:
        async with app.router.lifespan_context(app):
            yield test_client


@pytest.fixture
async def admin_headers(client: httpx.AsyncClient) -> dict[str, str]:
    from newscrawl_api.config import get_settings

    settings = get_settings()
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": settings.admin_email, "password": settings.admin_password},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
async def analytics_data() -> AsyncIterator[dict[str, uuid.UUID]]:
    """A source with two articles, one entity, one topic, one LLM extraction."""
    from newscrawl_api.db import session_scope
    from newscrawl_api.models import (
        Article,
        ArticleEntity,
        ArticleTopic,
        Entity,
        LlmExtraction,
        Source,
        Topic,
    )
    from newscrawl_contracts.enums import EntityType, ProcessingStatus
    from sqlalchemy import delete

    unique = uuid.uuid4().hex[:8]
    ids: dict[str, uuid.UUID] = {}
    async with session_scope() as db:
        source = Source(
            name="Stats API Test",
            slug=f"stats-api-{unique}",
            base_url=f"https://stats-{unique}.example.com",
            language="en",
            country="BD",
            allowed_domains=[f"stats-{unique}.example.com"],
        )
        db.add(source)
        await db.flush()
        ids["source"] = source.id

        for key, sentiment in (("a1", "positive"), ("a2", "negative")):
            article = Article(
                source_id=source.id,
                canonical_url=f"{source.base_url}/{key}",
                title=f"Stats article {key} {unique}",
                body="stats body text " * 40,
                language="en",
                sentiment=sentiment,
                content_hash=hashlib.sha256(f"{unique}-{key}".encode()).hexdigest(),
                word_count=120,
            )
            db.add(article)
            await db.flush()
            ids[key] = article.id

        entity = Entity(
            name=f"Stats Person {unique}",
            normalized_name=f"stats person {unique}",
            entity_type=EntityType.PERSON,
        )
        topic = Topic(name=f"Stats Topic {unique}", slug=f"stats-topic-{unique}")
        db.add_all([entity, topic])
        await db.flush()
        ids["entity"] = entity.id
        ids["topic"] = topic.id

        db.add_all(
            [
                ArticleEntity(article_id=ids["a1"], entity_id=entity.id),
                ArticleEntity(article_id=ids["a2"], entity_id=entity.id),
                ArticleTopic(article_id=ids["a1"], topic_id=topic.id),
                LlmExtraction(
                    article_id=ids["a1"],
                    provider="gemini",
                    model="gemini-test",
                    status=ProcessingStatus.COMPLETED,
                    prompt_tokens=100,
                    completion_tokens=50,
                    total_tokens=150,
                    cost_usd=0.0012,
                ),
            ]
        )

    yield ids

    async with session_scope() as db:
        await db.execute(delete(LlmExtraction).where(LlmExtraction.article_id == ids["a1"]))
        await db.execute(delete(ArticleEntity).where(ArticleEntity.entity_id == ids["entity"]))
        await db.execute(delete(ArticleTopic).where(ArticleTopic.topic_id == ids["topic"]))
        await db.execute(delete(Entity).where(Entity.id == ids["entity"]))
        await db.execute(delete(Topic).where(Topic.id == ids["topic"]))
        await db.execute(delete(Article).where(Article.source_id == ids["source"]))
        await db.execute(delete(Source).where(Source.id == ids["source"]))


class TestOverview:
    async def test_overview_counts(
        self,
        client: httpx.AsyncClient,
        admin_headers: dict[str, str],
        analytics_data: dict[str, uuid.UUID],
    ) -> None:
        response = await client.get("/api/v1/stats/overview", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total_articles"] >= 2
        assert data["total_sources"] >= 1
        assert data["llm_tokens_total"] >= 150
        assert data["llm_cost_usd_total"] > 0
        assert any(point["count"] >= 2 for point in data["articles_per_day"])

    async def test_requires_auth(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/api/v1/stats/overview")
        assert response.status_code == 401


class TestSourceHealth:
    async def test_source_row_present(
        self,
        client: httpx.AsyncClient,
        admin_headers: dict[str, str],
        analytics_data: dict[str, uuid.UUID],
    ) -> None:
        response = await client.get("/api/v1/stats/sources", headers=admin_headers)
        assert response.status_code == 200
        rows = {row["source_id"]: row for row in response.json()}
        row = rows[str(analytics_data["source"])]
        assert row["articles_total"] == 2
        assert row["last_article_at"] is not None


class TestAnalytics:
    async def test_timeseries(
        self,
        client: httpx.AsyncClient,
        admin_headers: dict[str, str],
        analytics_data: dict[str, uuid.UUID],
    ) -> None:
        response = await client.get(
            "/api/v1/stats/timeseries", params={"days": 7}, headers=admin_headers
        )
        assert response.status_code == 200
        points = response.json()
        ours = [p for p in points if p["source_slug"].startswith("stats-api-")]
        assert sum(p["count"] for p in ours) == 2

    async def test_top_entities(
        self,
        client: httpx.AsyncClient,
        admin_headers: dict[str, str],
        analytics_data: dict[str, uuid.UUID],
    ) -> None:
        response = await client.get(
            "/api/v1/stats/entities/top", params={"limit": 100}, headers=admin_headers
        )
        assert response.status_code == 200
        matches = [e for e in response.json() if e["name"].startswith("Stats Person")]
        assert matches and matches[0]["article_count"] == 2
        assert matches[0]["entity_type"] == "person"

    async def test_top_topics(
        self,
        client: httpx.AsyncClient,
        admin_headers: dict[str, str],
        analytics_data: dict[str, uuid.UUID],
    ) -> None:
        response = await client.get(
            "/api/v1/stats/topics/top", params={"limit": 100}, headers=admin_headers
        )
        assert response.status_code == 200
        matches = [t for t in response.json() if t["name"].startswith("Stats Topic")]
        assert matches and matches[0]["article_count"] == 1

    async def test_sentiment_distribution(
        self,
        client: httpx.AsyncClient,
        admin_headers: dict[str, str],
        analytics_data: dict[str, uuid.UUID],
    ) -> None:
        response = await client.get("/api/v1/stats/sentiment", headers=admin_headers)
        assert response.status_code == 200
        buckets = {b["sentiment"]: b["count"] for b in response.json()}
        assert buckets.get("positive", 0) >= 1
        assert buckets.get("negative", 0) >= 1

    async def test_llm_daily_costs(
        self,
        client: httpx.AsyncClient,
        admin_headers: dict[str, str],
        analytics_data: dict[str, uuid.UUID],
    ) -> None:
        response = await client.get(
            "/api/v1/stats/llm/daily", params={"days": 7}, headers=admin_headers
        )
        assert response.status_code == 200
        gemini_rows = [r for r in response.json() if r["provider"] == "gemini"]
        assert gemini_rows
        assert sum(r["total_tokens"] for r in gemini_rows) >= 150


class TestPrometheusMetrics:
    async def test_http_metrics_exported(
        self, client: httpx.AsyncClient, admin_headers: dict[str, str]
    ) -> None:
        # Generate one labelled request, then check it shows up on /metrics.
        await client.get("/api/v1/stats/overview", headers=admin_headers)
        response = await client.get("/api/v1/metrics")
        assert response.status_code == 200
        body = response.text
        assert "newscrawl_http_requests_total" in body
        # Route-template label (router prefix not included in route.path)
        assert 'path="/stats/overview"' in body

    async def test_platform_gauges_refresh(self, client: httpx.AsyncClient) -> None:
        from newscrawl_api.config import get_settings
        from newscrawl_api.observability import refresh_platform_gauges
        from redis.asyncio import Redis

        redis = Redis.from_url(get_settings().redis_url, decode_responses=True)
        try:
            await refresh_platform_gauges(redis)
        finally:
            await redis.aclose()

        response = await client.get("/api/v1/metrics")
        body = response.text
        assert "newscrawl_articles_total" in body
        assert "newscrawl_queue_depth" in body
