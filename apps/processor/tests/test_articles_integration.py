"""Article persistence + version tracking against the real database."""

import uuid
from collections.abc import AsyncIterator

import pytest
from newscrawl_api.db import get_session_factory
from newscrawl_api.models import Article, ArticleVersion, Source
from newscrawl_processor.articles import ArticleService
from newscrawl_processor.cleaning import clean_extracted
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration

# Realistic article length — SimHash distance of a small edit scales with the
# fraction of changed shingles, so short snippets overstate it.
BODY = " ".join(
    [
        "Parliament passed the new education budget on Tuesday after a marathon"
        " session that stretched past midnight, allocating record funding for"
        " primary schools across all districts.",
        "Opposition members criticized the allocation formula but ultimately"
        " supported the bill in the final vote.",
        "The education minister said implementation begins with the new fiscal"
        " year, prioritizing teacher recruitment and classroom construction in"
        " underserved upazilas.",
        "Union leaders welcomed the salary provisions while urging faster"
        " disbursement than in previous budget cycles.",
        "The finance ministry projected that the expanded program would raise"
        " enrollment rates in the poorest districts within two academic years.",
        "Education researchers cautioned that construction targets have slipped"
        " in past budgets and called for quarterly public reporting on progress.",
        "District officials said land acquisition for new classrooms is already"
        " underway in several coastal upazilas affected by recent flooding.",
        "The bill also funds a national teacher training academy and digital"
        " learning materials in both Bangla and English for secondary schools.",
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
        name="Persist Test",
        slug=f"persist-test-{unique}",
        base_url=f"https://persist-{unique}.example.com",
        language="en",
        country="BD",
        allowed_domains=[f"persist-{unique}.example.com"],
    )
    db.add(src)
    await db.commit()
    src_id = src.id
    yield src
    await db.rollback()
    article_ids = (await db.scalars(select(Article.id).where(Article.source_id == src_id))).all()
    if article_ids:
        await db.execute(delete(ArticleVersion).where(ArticleVersion.article_id.in_(article_ids)))
    await db.execute(delete(Article).where(Article.source_id == src_id))
    await db.execute(delete(Source).where(Source.id == src_id))
    await db.commit()


def extraction(title: str = "Education budget passes", body: str = BODY) -> dict[str, object]:
    return {
        "title": title,
        "body": body,
        "author": "Staff Correspondent",
        "published_at": "2026-07-23T09:00:00+06:00",
        "extraction_method": "json_ld",
        "extraction_confidence": 0.95,
    }


async def test_new_article_created_with_version_1(db: AsyncSession, source: Source) -> None:
    service = ArticleService()
    url = f"{source.base_url}/education-budget"
    result = await service.persist(
        db, clean_extracted(extraction()), source_id=source.id, canonical_url=url, url_id=1
    )
    assert result.action == "created"
    assert result.version == 1

    article = await db.get(Article, result.article_id)
    assert article is not None
    assert article.simhash is not None
    assert article.language == "en"
    versions = (
        await db.scalars(select(ArticleVersion).where(ArticleVersion.article_id == article.id))
    ).all()
    assert len(versions) == 1


async def test_unchanged_content_is_noop(db: AsyncSession, source: Source) -> None:
    service = ArticleService()
    url = f"{source.base_url}/education-budget"
    first = await service.persist(
        db, clean_extracted(extraction()), source_id=source.id, canonical_url=url
    )
    again = await service.persist(
        db, clean_extracted(extraction()), source_id=source.id, canonical_url=url
    )
    assert again.action == "unchanged"
    assert again.article_id == first.article_id
    assert again.version == 1


async def test_changed_content_creates_version_with_field_flags(
    db: AsyncSession, source: Source
) -> None:
    service = ArticleService()
    url = f"{source.base_url}/education-budget"
    first = await service.persist(
        db, clean_extracted(extraction()), source_id=source.id, canonical_url=url
    )
    updated = await service.persist(
        db,
        clean_extracted(extraction(title="Education budget passes unanimously")),
        source_id=source.id,
        canonical_url=url,
    )
    assert updated.action == "updated"
    assert updated.article_id == first.article_id
    assert updated.version == 2

    version2 = await db.scalar(
        select(ArticleVersion).where(
            ArticleVersion.article_id == first.article_id, ArticleVersion.version == 2
        )
    )
    assert version2 is not None
    assert version2.title_changed
    assert not version2.body_changed
    assert not version2.author_changed

    article = await db.get(Article, first.article_id)
    assert article is not None
    assert article.current_version == 2
    assert article.title == "Education budget passes unanimously"


async def test_same_story_at_second_url_is_duplicate(db: AsyncSession, source: Source) -> None:
    service = ArticleService()
    first = await service.persist(
        db,
        clean_extracted(extraction()),
        source_id=source.id,
        canonical_url=f"{source.base_url}/education-budget",
    )
    # Same content republished at a different URL (e.g. syndication path)
    dup = await service.persist(
        db,
        clean_extracted(extraction()),
        source_id=source.id,
        canonical_url=f"{source.base_url}/news/education-budget-2026",
    )
    assert dup.action == "duplicate"
    assert dup.duplicate_of == first.article_id
    assert dup.dedup_stage == "exact"

    count = len((await db.scalars(select(Article.id).where(Article.source_id == source.id))).all())
    assert count == 1


async def test_near_duplicate_at_second_url_caught_by_simhash(
    db: AsyncSession, source: Source
) -> None:
    service = ArticleService()
    first = await service.persist(
        db,
        clean_extracted(extraction()),
        source_id=source.id,
        canonical_url=f"{source.base_url}/education-budget",
    )
    tweaked = extraction(body=BODY.replace("Tuesday", "Wednesday"))
    dup = await service.persist(
        db,
        clean_extracted(tweaked),
        source_id=source.id,
        canonical_url=f"{source.base_url}/education-budget-repost",
    )
    assert dup.action == "duplicate"
    assert dup.duplicate_of == first.article_id
    assert dup.dedup_stage == "simhash"
