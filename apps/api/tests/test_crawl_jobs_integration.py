"""Crawl job lifecycle integration tests — require the local stack."""

import uuid
from collections.abc import AsyncIterator
from typing import Any

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
async def admin_token(client: httpx.AsyncClient) -> str:
    from newscrawl_api.config import get_settings

    settings = get_settings()
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": settings.admin_email, "password": settings.admin_password},
    )
    assert response.status_code == 200, response.text
    return str(response.json()["access_token"])


@pytest.fixture
async def scratch_source(
    client: httpx.AsyncClient, admin_token: str
) -> AsyncIterator[dict[str, Any]]:
    """A dedicated source so job URLs never collide with real sources."""
    unique = uuid.uuid4().hex[:8]
    host = f"jobtest-{unique}.example.com"
    response = await client.post(
        "/api/v1/sources",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "name": f"Job Test {unique}",
            "slug": f"job-test-{unique}",
            "base_url": f"https://{host}",
            "language": "en",
            "country": "US",
            "allowed_domains": [host],
            "section_urls": [f"https://{host}/news"],
            "rss_urls": [f"https://{host}/feed.xml"],
        },
    )
    assert response.status_code == 201, response.text
    source = response.json()
    yield source

    # Cleanup: job rows and frontier rows for this source
    from newscrawl_api.db import session_scope
    from newscrawl_api.models import CrawlJob, CrawlUrl
    from newscrawl_api.models import Source as SourceModel
    from sqlalchemy import delete

    source_id = uuid.UUID(source["id"])
    async with session_scope() as db:
        await db.execute(delete(CrawlUrl).where(CrawlUrl.source_id == source_id))
        await db.execute(delete(CrawlJob).where(CrawlJob.source_id == source_id))
        await db.execute(delete(SourceModel).where(SourceModel.id == source_id))


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_create_job_seeds_frontier(
    client: httpx.AsyncClient, admin_token: str, scratch_source: dict[str, Any]
) -> None:
    response = await client.post(
        "/api/v1/crawl-jobs",
        headers=auth(admin_token),
        json={"source_id": scratch_source["id"], "job_type": "incremental_crawl"},
    )
    assert response.status_code == 201, response.text
    job = response.json()
    assert job["status"] == "queued"
    # homepage + 1 rss + 1 section
    assert job["pages_discovered"] == 3

    from newscrawl_api.db import session_scope
    from newscrawl_api.models import CrawlUrl
    from sqlalchemy import func, select

    async with session_scope() as db:
        count = await db.scalar(
            select(func.count())
            .select_from(CrawlUrl)
            .where(CrawlUrl.crawl_job_id == uuid.UUID(job["id"]))
        )
    assert count == 3


async def test_second_job_requeues_existing_entry_urls(
    client: httpx.AsyncClient, admin_token: str, scratch_source: dict[str, Any]
) -> None:
    """Entry URLs already in the frontier must be re-adopted by a new job,
    not silently skipped — otherwise a second job would never crawl."""
    for expected_job in range(2):
        response = await client.post(
            "/api/v1/crawl-jobs",
            headers=auth(admin_token),
            json={"source_id": scratch_source["id"], "job_type": "incremental_crawl"},
        )
        assert response.status_code == 201, f"job {expected_job}: {response.text}"
        assert response.json()["pages_discovered"] == 3


async def test_job_lifecycle_pause_resume_cancel(
    client: httpx.AsyncClient, admin_token: str, scratch_source: dict[str, Any]
) -> None:
    created = await client.post(
        "/api/v1/crawl-jobs",
        headers=auth(admin_token),
        json={"source_id": scratch_source["id"], "job_type": "incremental_crawl"},
    )
    job_id = created.json()["id"]

    paused = await client.post(f"/api/v1/crawl-jobs/{job_id}/pause", headers=auth(admin_token))
    assert paused.status_code == 200
    assert paused.json()["status"] == "paused"

    resumed = await client.post(f"/api/v1/crawl-jobs/{job_id}/resume", headers=auth(admin_token))
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "queued"  # never started running

    cancelled = await client.post(f"/api/v1/crawl-jobs/{job_id}/cancel", headers=auth(admin_token))
    assert cancelled.status_code == 200
    body = cancelled.json()
    assert body["status"] == "cancelled"
    assert body["completed_at"] is not None

    # Terminal: any further action is a 409 conflict
    again = await client.post(f"/api/v1/crawl-jobs/{job_id}/pause", headers=auth(admin_token))
    assert again.status_code == 409


async def test_bad_params_rejected(
    client: httpx.AsyncClient, admin_token: str, scratch_source: dict[str, Any]
) -> None:
    response = await client.post(
        "/api/v1/crawl-jobs",
        headers=auth(admin_token),
        json={"source_id": scratch_source["id"], "job_type": "url_crawl", "params": {}},
    )
    assert response.status_code == 422
    assert "params.urls" in response.json()["detail"]


async def test_list_filters_by_status(
    client: httpx.AsyncClient, admin_token: str, scratch_source: dict[str, Any]
) -> None:
    created = await client.post(
        "/api/v1/crawl-jobs",
        headers=auth(admin_token),
        json={"source_id": scratch_source["id"], "job_type": "incremental_crawl"},
    )
    job_id = created.json()["id"]

    listed = await client.get(
        "/api/v1/crawl-jobs",
        headers=auth(admin_token),
        params={"source_id": scratch_source["id"], "status": "queued"},
    )
    assert listed.status_code == 200
    body = listed.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == job_id

    none_listed = await client.get(
        "/api/v1/crawl-jobs",
        headers=auth(admin_token),
        params={"source_id": scratch_source["id"], "status": "running"},
    )
    assert none_listed.json()["total"] == 0


async def test_viewer_cannot_create_jobs(
    client: httpx.AsyncClient, scratch_source: dict[str, Any]
) -> None:
    response = await client.post(
        "/api/v1/crawl-jobs",
        json={"source_id": scratch_source["id"], "job_type": "incremental_crawl"},
    )
    assert response.status_code == 401
