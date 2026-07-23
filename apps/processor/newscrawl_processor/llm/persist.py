"""Persist a validated LLM analysis: article enrichment + entities + topics
+ the llm_extractions audit row (tokens and cost)."""

import re
import unicodedata

from newscrawl_api.models import (
    Article,
    ArticleEntity,
    ArticleTopic,
    Entity,
    LlmExtraction,
    Topic,
)
from newscrawl_contracts.enums import EntityType, ProcessingStatus
from newscrawl_crawler_utils import normalize_text
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from newscrawl_processor.llm.extractor import LlmUsage
from newscrawl_processor.llm.schema import ArticleAnalysis


def topic_slug(name: str) -> str:
    """Unicode-preserving slug (Bangla topic names stay Bangla).

    Strips punctuation/symbols by Unicode category rather than `\\w`, which
    would drop Bengali vowel signs and hasanta (combining-mark categories).
    """
    normalized = unicodedata.normalize("NFC", name.strip().lower())
    kept = [
        ch for ch in normalized if ch == "-" or not unicodedata.category(ch).startswith(("P", "S"))
    ]
    return re.sub(r"[\s_]+", "-", "".join(kept)).strip("-")[:200]


async def apply_analysis(
    db: AsyncSession,
    article: Article,
    analysis: ArticleAnalysis,
    usage: LlmUsage,
    *,
    latency_ms: int | None = None,
) -> LlmExtraction:
    # Enrich the article. The LLM summary fills the gap when the source page
    # had none; a publisher-provided summary is kept.
    if not article.summary:
        article.summary = analysis.summary
    article.sentiment = analysis.sentiment
    article.event_type = analysis.event_type
    article.political_category = analysis.political_category

    await _link_entities(db, article, analysis)
    await _link_topics(db, article, analysis)

    extraction = LlmExtraction(
        article_id=article.id,
        provider=usage.provider,
        model=usage.model,
        status=ProcessingStatus.COMPLETED,
        extraction=analysis.model_dump(mode="json"),
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
        total_tokens=usage.total_tokens,
        cost_usd=usage.cost_usd,
        latency_ms=latency_ms,
        error="; ".join(usage.errors)[:2000] if usage.errors else None,
    )
    db.add(extraction)
    await db.commit()
    return extraction


async def record_failure(
    db: AsyncSession,
    article: Article,
    usage: LlmUsage,
    *,
    error: str,
    latency_ms: int | None = None,
) -> None:
    db.add(
        LlmExtraction(
            article_id=article.id,
            provider=usage.provider or "none",
            model=usage.model or "none",
            status=ProcessingStatus.FAILED,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            total_tokens=usage.total_tokens,
            cost_usd=usage.cost_usd,
            latency_ms=latency_ms,
            error=error[:2000],
        )
    )
    await db.commit()


async def _link_entities(db: AsyncSession, article: Article, analysis: ArticleAnalysis) -> None:
    seen: set[tuple[str, str]] = set()
    for extracted in analysis.entities:
        name = normalize_text(extracted.name)
        if not name:
            continue
        normalized = name.lower()
        entity_type = EntityType(extracted.type)
        key = (normalized, entity_type.value)
        if key in seen:
            continue
        seen.add(key)

        entity = await db.scalar(
            select(Entity).where(
                Entity.normalized_name == normalized, Entity.entity_type == entity_type
            )
        )
        if entity is None:
            entity = Entity(name=name, normalized_name=normalized, entity_type=entity_type)
            db.add(entity)
            await db.flush()

        link = await db.get(ArticleEntity, (article.id, entity.id))
        if link is None:
            db.add(ArticleEntity(article_id=article.id, entity_id=entity.id))


async def _link_topics(db: AsyncSession, article: Article, analysis: ArticleAnalysis) -> None:
    seen: set[str] = set()
    for raw_name in analysis.topics:
        name = normalize_text(raw_name)
        slug = topic_slug(name)
        if not slug or slug in seen:
            continue
        seen.add(slug)

        topic = await db.scalar(select(Topic).where(Topic.slug == slug))
        if topic is None:
            topic = Topic(name=name[:200], slug=slug)
            db.add(topic)
            await db.flush()

        link = await db.get(ArticleTopic, (article.id, topic.id))
        if link is None:
            db.add(ArticleTopic(article_id=article.id, topic_id=topic.id))
