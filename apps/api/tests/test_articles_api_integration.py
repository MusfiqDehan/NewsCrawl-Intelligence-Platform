"""Articles + semantic search endpoints (real stack, fake embedding backend)."""

import hashlib
import math
import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from newscrawl_api.main import create_app
from newscrawl_api.services.embedding_backend import set_embedding_backend

pytestmark = pytest.mark.integration

DIM = 1024


class FakeBackend:
    model_name = "fake-embedder"
    dimension = DIM

    def encode(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            vector = [0.0] * DIM
            head = text.split()[0] if text.split() else ""
            head_hash = int.from_bytes(hashlib.sha256(head.encode()).digest()[:4], "big")
            vector[head_hash % DIM] = 10.0
            for token in text.split()[1:32]:
                token_hash = int.from_bytes(hashlib.sha256(token.encode()).digest()[:4], "big")
                vector[token_hash % DIM] += 0.1
            norm = math.sqrt(sum(x * x for x in vector))
            vectors.append([x / norm for x in vector])
        return vectors


@pytest.fixture(autouse=True)
async def _engine_per_loop() -> AsyncIterator[None]:
    set_embedding_backend(FakeBackend())
    yield
    set_embedding_backend(None)
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
async def seeded_articles(
    client: httpx.AsyncClient, admin_headers: dict[str, str]
) -> AsyncIterator[dict[str, uuid.UUID]]:
    """Two flood articles + one cricket article, embedded with FakeBackend."""
    from newscrawl_api.db import session_scope
    from newscrawl_api.models import Article, ArticleEmbedding, Source
    from newscrawl_processor.embeddings import EmbeddingService
    from sqlalchemy import delete, select

    unique = uuid.uuid4().hex[:8]
    ids: dict[str, uuid.UUID] = {}
    async with session_scope() as db:
        source = Source(
            name="Articles API Test",
            slug=f"articles-api-{unique}",
            base_url=f"https://articles-{unique}.example.com",
            language="en",
            country="BD",
            allowed_domains=[f"articles-{unique}.example.com"],
        )
        db.add(source)
        await db.flush()
        ids["source"] = source.id

        specs = {
            "flood1": ("Flood alert issued", "flood waters rising in northern districts " * 20),
            "flood2": ("Flood update morning", "flood waters rising in southern districts " * 20),
            "cricket": ("Cricket final tonight", "cricket team prepares for the trophy " * 20),
        }
        for key, (title, body) in specs.items():
            article = Article(
                source_id=source.id,
                canonical_url=f"{source.base_url}/{key}",
                title=title,
                body=body,
                language="en",
                content_hash=hashlib.sha256(key.encode()).hexdigest(),
                word_count=len(body.split()),
            )
            db.add(article)
            await db.flush()
            ids[key] = article.id

        service = EmbeddingService(FakeBackend(), version=1)
        for key in specs:
            article_obj = await db.get(Article, ids[key])
            assert article_obj is not None
            await service.embed_article(db, article_obj)

    yield ids

    async with session_scope() as db:
        article_ids = (
            await db.scalars(select(Article.id).where(Article.source_id == ids["source"]))
        ).all()
        await db.execute(
            delete(ArticleEmbedding).where(ArticleEmbedding.article_id.in_(article_ids))
        )
        await db.execute(delete(Article).where(Article.source_id == ids["source"]))
        await db.execute(delete(Source).where(Source.id == ids["source"]))


async def test_articles_require_auth(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/v1/articles")).status_code == 401


async def test_list_articles_with_filters(
    client: httpx.AsyncClient,
    admin_headers: dict[str, str],
    seeded_articles: dict[str, uuid.UUID],
) -> None:
    response = await client.get(
        "/api/v1/articles",
        headers=admin_headers,
        params={"source_id": str(seeded_articles["source"]), "q": "flood"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    titles = {item["title"] for item in body["items"]}
    assert titles == {"Flood alert issued", "Flood update morning"}


async def test_get_article_detail(
    client: httpx.AsyncClient,
    admin_headers: dict[str, str],
    seeded_articles: dict[str, uuid.UUID],
) -> None:
    response = await client.get(
        f"/api/v1/articles/{seeded_articles['flood1']}", headers=admin_headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Flood alert issued"
    assert "flood waters" in body["body"]


async def test_similar_articles_endpoint(
    client: httpx.AsyncClient,
    admin_headers: dict[str, str],
    seeded_articles: dict[str, uuid.UUID],
) -> None:
    from newscrawl_api.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    # The endpoint pins to the configured model — align it with the fixture
    response = await client.get(
        f"/api/v1/articles/{seeded_articles['flood1']}/similar",
        headers=admin_headers,
        params={"limit": 2},
    )
    if settings.embedding_model != "fake-embedder":
        # Vectors exist under 'fake-embedder'; the configured model has none
        assert response.status_code == 409
    else:
        assert response.status_code == 200


async def test_semantic_search_endpoint(
    client: httpx.AsyncClient,
    admin_headers: dict[str, str],
    seeded_articles: dict[str, uuid.UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from newscrawl_api.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "embedding_model", "fake-embedder")
    monkeypatch.setattr(settings, "embedding_version", 1)

    response = await client.get(
        "/api/v1/search/semantic",
        headers=admin_headers,
        params={"q": "flood waters everywhere", "source_id": str(seeded_articles["source"])},
    )
    assert response.status_code == 200
    results = response.json()["results"]
    assert results
    assert results[0]["article"]["id"] == str(seeded_articles["flood1"])
    assert results[0]["similarity"] > results[-1]["similarity"]
    # Cricket article ranks last or below the floods
    top_two = {r["article"]["id"] for r in results[:2]}
    assert str(seeded_articles["cricket"]) not in top_two
