"""Article persistence with version tracking and dedup gating.

Outcomes for an incoming cleaned article:
  - created   — new article (version 1)
  - updated   — existing canonical URL, content changed → new version with
                field-level change flags
  - unchanged — existing canonical URL, identical content hash
  - duplicate — different URL but same/near-same content as another article
                (staged dedup) → not persisted
"""

import uuid
from dataclasses import dataclass

from newscrawl_api.models import Article, ArticleVersion
from newscrawl_contracts.enums import ExtractionMethod
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from newscrawl_processor.cleaning import CleanedArticle
from newscrawl_processor.dedup import DedupService, article_simhash


@dataclass
class PersistResult:
    action: str  # "created" | "updated" | "unchanged" | "duplicate"
    article_id: uuid.UUID | None = None
    duplicate_of: uuid.UUID | None = None
    dedup_stage: str | None = None
    version: int | None = None


class ArticleService:
    def __init__(self, dedup: DedupService | None = None) -> None:
        self.dedup = dedup or DedupService()

    async def persist(
        self,
        db: AsyncSession,
        cleaned: CleanedArticle,
        *,
        source_id: uuid.UUID,
        canonical_url: str,
        url_id: int | None = None,
        raw_html_location: str | None = None,
        country: str | None = None,
    ) -> PersistResult:
        existing = await db.scalar(select(Article).where(Article.canonical_url == canonical_url))
        if existing is not None:
            return await self._update_existing(db, existing, cleaned)

        simhash = article_simhash(cleaned.title, cleaned.body)
        dedup = await self.dedup.find_duplicate(
            db, content_hash=cleaned.content_hash, simhash=simhash, source_id=source_id
        )
        if dedup.is_duplicate:
            return PersistResult(
                action="duplicate",
                duplicate_of=dedup.duplicate_of,
                dedup_stage=dedup.stage,
            )

        article = Article(
            source_id=source_id,
            url_id=url_id,
            canonical_url=canonical_url,
            title=cleaned.title,
            subtitle=cleaned.subtitle,
            author=cleaned.author,
            category=cleaned.category,
            language=cleaned.language.value,
            country=country,
            published_at=cleaned.published_at,
            updated_at_source=cleaned.updated_at,
            body=cleaned.body,
            summary=cleaned.summary,
            image_urls=cleaned.image_urls,
            tags=cleaned.tags,
            raw_html_location=raw_html_location,
            content_hash=cleaned.content_hash,
            simhash=simhash,
            word_count=cleaned.word_count,
            extraction_method=ExtractionMethod(cleaned.extraction_method),
            extraction_confidence=cleaned.extraction_confidence,
            current_version=1,
        )
        db.add(article)
        await db.flush()
        db.add(_version_snapshot(article, version=1))
        await db.commit()
        return PersistResult(action="created", article_id=article.id, version=1)

    async def _update_existing(
        self, db: AsyncSession, article: Article, cleaned: CleanedArticle
    ) -> PersistResult:
        if article.content_hash == cleaned.content_hash:
            return PersistResult(
                action="unchanged", article_id=article.id, version=article.current_version
            )

        changes = {
            "title_changed": article.title != cleaned.title,
            "body_changed": article.body != cleaned.body,
            "author_changed": article.author != cleaned.author,
            "published_at_changed": article.published_at != cleaned.published_at,
            "category_changed": article.category != cleaned.category,
            "metadata_changed": (
                article.subtitle != cleaned.subtitle
                or article.summary != cleaned.summary
                or article.tags != cleaned.tags
                or article.image_urls != cleaned.image_urls
            ),
        }

        article.title = cleaned.title
        article.subtitle = cleaned.subtitle
        article.author = cleaned.author
        article.category = cleaned.category
        article.published_at = cleaned.published_at
        article.updated_at_source = cleaned.updated_at
        article.body = cleaned.body
        article.summary = cleaned.summary
        article.image_urls = cleaned.image_urls
        article.tags = cleaned.tags
        article.content_hash = cleaned.content_hash
        article.simhash = article_simhash(cleaned.title, cleaned.body)
        article.word_count = cleaned.word_count
        article.current_version += 1

        db.add(_version_snapshot(article, version=article.current_version, **changes))
        await db.commit()
        return PersistResult(
            action="updated", article_id=article.id, version=article.current_version
        )


def _version_snapshot(article: Article, *, version: int, **change_flags: bool) -> ArticleVersion:
    return ArticleVersion(
        article_id=article.id,
        version=version,
        content_hash=article.content_hash,
        title=article.title,
        subtitle=article.subtitle,
        author=article.author,
        category=article.category,
        published_at=article.published_at,
        body=article.body,
        **change_flags,
    )
