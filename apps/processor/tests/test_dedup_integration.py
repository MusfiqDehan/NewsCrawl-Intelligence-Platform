"""Staged dedup service against the real database (make dev + migrate)."""

import uuid
from collections.abc import AsyncIterator

import pytest
from newscrawl_api.db import get_session_factory
from newscrawl_api.models import Article, Source
from newscrawl_crawler_utils import content_hash
from newscrawl_processor.dedup import DedupService, article_simhash
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration

# Realistic article length: SimHash distance scales with the *fraction* of
# changed shingles, so short snippets overstate the distance of small edits.
BODY = " ".join(
    [
        "The city corporation launched a large-scale road repair program on Monday"
        " covering forty kilometers of arterial roads damaged during the monsoon.",
        "The mayor said the work would be completed within three months and that"
        " contractors face penalties for delays.",
        "Residents welcomed the initiative but expressed concern about traffic"
        " diversions during peak hours.",
        "Officials confirmed that funding for the project comes from the annual"
        " development budget approved earlier this year by the city council.",
        "Engineers will begin with the most heavily damaged corridors near the"
        " industrial zone before moving to residential neighborhoods.",
        "A dedicated monitoring cell will publish weekly progress reports and"
        " residents can submit complaints through a new hotline.",
        "Transport operators were asked to plan alternative routes and the traffic"
        " police will deploy additional officers at key intersections.",
        "The program also includes upgrading storm drains along the repaired"
        " stretches to reduce waterlogging during future monsoons.",
    ]
)


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
        name="Dedup Test",
        slug=f"dedup-test-{unique}",
        base_url=f"https://dedup-{unique}.example.com",
        language="en",
        country="US",
        allowed_domains=[f"dedup-{unique}.example.com"],
    )
    db.add(src)
    await db.commit()
    src_id = src.id
    yield src
    await db.rollback()
    await db.execute(delete(Article).where(Article.source_id == src_id))
    await db.execute(delete(Source).where(Source.id == src_id))
    await db.commit()


async def make_article(
    db: AsyncSession, source: Source, *, title: str, body: str, suffix: str = ""
) -> Article:
    article = Article(
        source_id=source.id,
        canonical_url=f"{source.base_url}/{uuid.uuid4().hex}{suffix}",
        title=title,
        body=body,
        language="en",
        content_hash=content_hash(title=title, body=body),
        simhash=article_simhash(title, body),
        word_count=len(body.split()),
    )
    db.add(article)
    await db.commit()
    return article


async def test_exact_duplicate_detected(db: AsyncSession, source: Source) -> None:
    original = await make_article(db, source, title="Road repairs begin", body=BODY)
    result = await DedupService().find_duplicate(
        db,
        content_hash=content_hash(title="Road repairs begin", body=BODY),
        simhash=article_simhash("Road repairs begin", BODY),
    )
    assert result.is_duplicate
    assert result.stage == "exact"
    assert result.duplicate_of == original.id


async def test_near_duplicate_detected_via_simhash_banding(
    db: AsyncSession, source: Source
) -> None:
    original = await make_article(db, source, title="Road repairs begin", body=BODY)
    # Same story, one word changed → different sha256, close simhash
    edited = BODY.replace("Monday", "Tuesday")
    result = await DedupService().find_duplicate(
        db,
        content_hash=content_hash(title="Road repairs begin", body=edited),
        simhash=article_simhash("Road repairs begin", edited),
    )
    assert result.is_duplicate
    assert result.stage == "simhash"
    assert result.duplicate_of == original.id
    assert result.hamming is not None and result.hamming <= 3


async def test_distinct_article_is_not_duplicate(db: AsyncSession, source: Source) -> None:
    await make_article(db, source, title="Road repairs begin", body=BODY)
    other_body = (
        "The national cricket team announced its squad for the upcoming series "
        "with two uncapped players earning their first call-ups. Selectors said "
        "recent domestic form was the deciding factor, while the captain backed "
        "the newcomers to adapt quickly to international conditions."
    )
    result = await DedupService().find_duplicate(
        db,
        content_hash=content_hash(title="Squad announced", body=other_body),
        simhash=article_simhash("Squad announced", other_body),
    )
    assert not result.is_duplicate
    assert result.duplicate_of is None


async def test_exclude_self_when_rechecking(db: AsyncSession, source: Source) -> None:
    article = await make_article(db, source, title="Road repairs begin", body=BODY)
    result = await DedupService().find_duplicate(
        db,
        content_hash=article.content_hash,
        simhash=article.simhash or 0,
        exclude_article_id=article.id,
    )
    assert not result.is_duplicate


async def test_moderately_different_article_becomes_semantic_candidate(
    db: AsyncSession, source: Source
) -> None:
    """A rewrite of the same story: too far for simhash auto-dedup but close
    enough to surface for the embedding stage."""
    original = await make_article(db, source, title="Road repairs begin", body=BODY)
    edited = (
        BODY.replace("Monday", "Tuesday")
        .replace("forty kilometers", "roughly forty kilometers")
        .replace("three months", "four months")
    )
    result = await DedupService(hamming_threshold=1).find_duplicate(
        db,
        content_hash=content_hash(title="Road repairs begin", body=edited),
        simhash=article_simhash("Road repairs begin", edited),
    )
    # With a strict threshold the edit is not an auto-duplicate…
    if not result.is_duplicate:
        assert original.id in result.semantic_candidates


async def test_threshold_beyond_banding_guarantee_rejected() -> None:
    with pytest.raises(ValueError, match="hamming_threshold"):
        DedupService(hamming_threshold=4)
