"""Frontier integration tests — require the local stack (make dev + migrate)."""

import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from newscrawl_api.db import get_session_factory
from newscrawl_api.models import CrawlUrl, Source
from newscrawl_api.services.frontier import DiscoveredUrl, Frontier
from newscrawl_contracts.enums import FailureCategory, UrlStatus, UrlType
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
async def _engine_per_loop() -> AsyncIterator[None]:
    """pytest-asyncio uses one event loop per test; the module-level engine
    must not leak across loops."""
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
    """A scratch source with a unique host (url_hash is globally unique, so
    tests must never share URLs), removed with its URLs after the test."""
    unique = uuid.uuid4().hex[:8]
    host = f"frontier-{unique}.example.com"
    src = Source(
        name="Frontier Test",
        slug=f"frontier-test-{unique}",
        base_url=f"https://{host}",
        language="en",
        country="US",
        allowed_domains=[host],
    )
    db.add(src)
    await db.commit()
    src_id = src.id
    yield src
    await db.rollback()
    await db.execute(delete(CrawlUrl).where(CrawlUrl.source_id == src_id))
    await db.execute(delete(Source).where(Source.id == src_id))
    await db.commit()


def frontier() -> Frontier:
    return Frontier(lease_seconds=60, max_retries=3)


async def test_add_urls_dedupes(db: AsyncSession, source: Source) -> None:
    f = frontier()
    urls = [
        DiscoveredUrl(url=f"{source.base_url}/a", url_type=UrlType.ARTICLE),
        DiscoveredUrl(url=f"{source.base_url}/a/", url_type=UrlType.ARTICLE),
        DiscoveredUrl(url=f"{source.base_url}/a?utm_source=x", url_type=UrlType.ARTICLE),
        DiscoveredUrl(url=f"{source.base_url}/b", url_type=UrlType.ARTICLE),
    ]
    added = await f.add_urls(db, source, urls)
    await db.commit()
    assert added == 2  # /a variants collapse into one

    # Re-adding is a no-op
    added_again = await f.add_urls(db, source, urls)
    await db.commit()
    assert added_again == 0


async def test_offsite_urls_dropped(db: AsyncSession, source: Source) -> None:
    added = await frontier().add_urls(db, source, [DiscoveredUrl(url="https://evil.example.org/x")])
    await db.commit()
    assert added == 0


async def test_claim_lease_and_success(db: AsyncSession, source: Source) -> None:
    f = frontier()
    await f.add_urls(
        db,
        source,
        [DiscoveredUrl(url=f"{source.base_url}/story", url_type=UrlType.ARTICLE)],
    )
    await db.commit()

    claimed = await f.claim_batch(db, worker_id="w1", source_id=source.id)
    await db.commit()
    assert len(claimed) == 1
    url = claimed[0]
    assert url.status == UrlStatus.LEASED
    assert url.lease_owner == "w1"
    assert url.lease_expires_at is not None

    # A second claim finds nothing (lease held)
    assert await f.claim_batch(db, worker_id="w2", source_id=source.id) == []
    await db.commit()

    await f.mark_success(db, url.id, http_status=200, content_hash="abc", etag='W/"1"')
    await db.commit()

    refreshed = await db.get(CrawlUrl, url.id)
    assert refreshed is not None
    assert refreshed.status == UrlStatus.SUCCESS
    assert refreshed.lease_owner is None
    assert refreshed.etag == 'W/"1"'
    assert refreshed.next_crawl_at is not None
    assert refreshed.next_crawl_at > datetime.now(UTC)


async def test_concurrent_claims_never_overlap(source: Source) -> None:
    """Two workers claiming in parallel sessions must get disjoint URLs."""
    f = frontier()
    factory = get_session_factory()

    async with factory() as setup:
        src = await setup.get(Source, source.id)
        assert src is not None
        await f.add_urls(
            setup,
            src,
            [
                DiscoveredUrl(
                    url=f"{source.base_url}/page-{i}",
                    url_type=UrlType.ARTICLE,
                )
                for i in range(30)
            ],
        )
        await setup.commit()

    async def claim(worker_id: str) -> set[int]:
        async with factory() as session:
            urls = await f.claim_batch(session, worker_id=worker_id, source_id=source.id, limit=20)
            await session.commit()
            return {u.id for u in urls}

    a, b = await asyncio.gather(claim("worker-a"), claim("worker-b"))
    assert a & b == set()
    assert len(a | b) == 30


async def test_failure_backoff_then_gives_up(db: AsyncSession, source: Source) -> None:
    f = frontier()
    await f.add_urls(db, source, [DiscoveredUrl(url=f"{source.base_url}/flaky")])
    await db.commit()

    for attempt in range(1, 4):
        # Make it due immediately, then claim and fail it
        await db.execute(
            update(CrawlUrl)
            .where(CrawlUrl.source_id == source.id)
            .values(next_crawl_at=datetime.now(UTC) - timedelta(seconds=1))
        )
        await db.commit()
        [url] = await f.claim_batch(db, worker_id="w1", source_id=source.id)
        status = await f.mark_failed(
            db,
            url.id,
            category=FailureCategory.HTTP_5XX,
            error="server exploded",
            http_status=500,
        )
        await db.commit()
        if attempt < 3:
            assert status == UrlStatus.RETRY_PENDING
        else:
            assert status == UrlStatus.FAILED  # max_retries=3 exhausted

    refreshed = await db.scalar(select(CrawlUrl).where(CrawlUrl.source_id == source.id))
    assert refreshed is not None
    assert refreshed.retry_count == 3


async def test_permanent_failure_blocks_immediately(db: AsyncSession, source: Source) -> None:
    f = frontier()
    await f.add_urls(db, source, [DiscoveredUrl(url=f"{source.base_url}/forbidden")])
    await db.commit()
    [url] = await f.claim_batch(db, worker_id="w1", source_id=source.id)
    status = await f.mark_failed(
        db, url.id, category=FailureCategory.ROBOTS_RESTRICTED, error="robots.txt disallow"
    )
    await db.commit()
    assert status == UrlStatus.BLOCKED


async def test_expired_leases_are_reaped(db: AsyncSession, source: Source) -> None:
    f = frontier()
    source_id = source.id
    await f.add_urls(db, source, [DiscoveredUrl(url=f"{source.base_url}/orphan")])
    await db.commit()
    [url] = await f.claim_batch(db, worker_id="crashed-worker", source_id=source.id)
    url_id = url.id
    await db.commit()

    # Simulate a crashed worker: lease long expired
    await db.execute(
        update(CrawlUrl)
        .where(CrawlUrl.id == url_id)
        .values(lease_expires_at=datetime.now(UTC) - timedelta(minutes=10))
    )
    await db.commit()

    reaped = await f.reap_expired_leases(db)
    await db.commit()
    assert reaped == 1

    db.expire_all()
    refreshed = await db.get(CrawlUrl, url_id)
    assert refreshed is not None
    assert refreshed.status == UrlStatus.QUEUED
    assert refreshed.lease_owner is None

    # And it can be claimed again by a healthy worker
    reclaimed = await f.claim_batch(db, worker_id="healthy", source_id=source_id)
    assert [u.id for u in reclaimed] == [url_id]
    await db.commit()


async def test_release_returns_url_to_queue(db: AsyncSession, source: Source) -> None:
    f = frontier()
    await f.add_urls(db, source, [DiscoveredUrl(url=f"{source.base_url}/graceful")])
    await db.commit()
    [url] = await f.claim_batch(db, worker_id="w1", source_id=source.id)
    url_id = url.id
    await f.release(db, url_id, "w1")
    await db.commit()

    db.expire_all()
    refreshed = await db.get(CrawlUrl, url_id)
    assert refreshed is not None
    assert refreshed.status == UrlStatus.QUEUED


async def test_priority_order_respected(db: AsyncSession, source: Source) -> None:
    f = frontier()
    await f.add_urls(
        db,
        source,
        [
            DiscoveredUrl(url=f"{source.base_url}/low", url_type=UrlType.OTHER),
            DiscoveredUrl(url=f"{source.base_url}/high", url_type=UrlType.HOMEPAGE),
        ],
    )
    await db.commit()
    claimed = await f.claim_batch(db, worker_id="w1", source_id=source.id, limit=1)
    await db.commit()
    assert claimed[0].normalized_url.endswith("/high")
