"""Integration tests for the API — require the local stack (make dev + migrate).

Run with:  make test-integration
"""

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from newscrawl_api.main import create_app

pytestmark = pytest.mark.integration


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    app = create_app()
    async with (
        # Trigger lifespan so redis client and engine are wired up
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as test_client,
    ):
        async with app.router.lifespan_context(app):
            yield test_client


@pytest.fixture
async def admin_token(client: httpx.AsyncClient) -> str:
    from newscrawl_api.config import get_settings

    settings = get_settings()
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": settings.admin_email, "password": settings.admin_password},
    )
    assert response.status_code == 200, response.text
    return str(response.json()["access_token"])


async def test_health(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_ready(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["postgres"] == "ok"
    assert body["redis"] == "ok"


async def test_login_bad_credentials(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": f"nobody-{uuid.uuid4().hex[:8]}@example.com", "password": "wrong"},
    )
    assert response.status_code == 401


async def test_sources_require_auth(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/v1/sources")).status_code == 401


async def test_sources_crud_flow(client: httpx.AsyncClient, admin_token: str) -> None:
    headers = {"Authorization": f"Bearer {admin_token}"}

    listing = await client.get("/api/v1/sources", headers=headers)
    assert listing.status_code == 200
    slugs = {source["slug"] for source in listing.json()}
    assert "prothom-alo" in slugs

    # Create a scratch source, patch it, verify persistence
    slug = f"test-src-{uuid.uuid4().hex[:8]}"
    created = await client.post(
        "/api/v1/sources",
        headers=headers,
        json={
            "name": "Test Source",
            "slug": slug,
            "base_url": "https://test.example.com",
            "language": "en",
            "country": "US",
        },
    )
    assert created.status_code == 201, created.text
    source_id = created.json()["id"]

    patched = await client.patch(
        f"/api/v1/sources/{source_id}",
        headers=headers,
        json={"crawl_enabled": False, "rate_limit_delay_seconds": 5.0},
    )
    assert patched.status_code == 200
    assert patched.json()["crawl_enabled"] is False
    assert patched.json()["rate_limit_delay_seconds"] == 5.0

    duplicate = await client.post(
        "/api/v1/sources",
        headers=headers,
        json={
            "name": "Dup",
            "slug": slug,
            "base_url": "https://dup.example.com",
            "language": "en",
            "country": "US",
        },
    )
    assert duplicate.status_code == 409
