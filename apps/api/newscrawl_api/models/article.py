"""Article storage: articles, versions, entities, topics, embeddings."""

import uuid
from datetime import date, datetime
from typing import Any

from newscrawl_contracts.enums import EmbeddingKind, EntityType, ExtractionMethod
from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, Date, ForeignKey, Index, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from newscrawl_api.models.base import Base, TimestampMixin, str_enum, uuid_pk


class ArticleDailyStat(Base):
    """Durable per-day crawl counts that survive 24h article retention."""

    __tablename__ = "article_daily_stats"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    articles_created: Mapped[int] = mapped_column(default=0)


class Article(Base, TimestampMixin):
    __tablename__ = "articles"

    id: Mapped[uuid.UUID] = uuid_pk()
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sources.id"))
    url_id: Mapped[int | None] = mapped_column(BigInteger, default=None, index=True)
    canonical_url: Mapped[str] = mapped_column(Text, unique=True)

    title: Mapped[str] = mapped_column(Text)
    subtitle: Mapped[str | None] = mapped_column(Text, default=None)
    author: Mapped[str | None] = mapped_column(String(500), default=None)
    category: Mapped[str | None] = mapped_column(String(200), default=None)
    language: Mapped[str] = mapped_column(String(8))
    country: Mapped[str | None] = mapped_column(String(8), default=None)
    published_at: Mapped[datetime | None] = mapped_column(default=None)
    updated_at_source: Mapped[datetime | None] = mapped_column(default=None)

    body: Mapped[str] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text, default=None)
    image_urls: Mapped[list[str]] = mapped_column(default=list)
    tags: Mapped[list[str]] = mapped_column(default=list)

    raw_html_location: Mapped[str | None] = mapped_column(String(500), default=None)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    # 64-bit SimHash stored as signed bigint for near-duplicate banding
    simhash: Mapped[int | None] = mapped_column(BigInteger, default=None, index=True)
    word_count: Mapped[int] = mapped_column(default=0)
    extraction_method: Mapped[ExtractionMethod] = mapped_column(
        str_enum(ExtractionMethod), default=ExtractionMethod.SELECTORS
    )
    extraction_confidence: Mapped[float] = mapped_column(default=1.0)
    current_version: Mapped[int] = mapped_column(default=1)

    # Filled after LLM extraction
    sentiment: Mapped[str | None] = mapped_column(String(20), default=None)
    event_type: Mapped[str | None] = mapped_column(String(100), default=None)
    political_category: Mapped[str | None] = mapped_column(String(100), default=None)

    # Semantic-dedup verdict (embedding stage): persisted but marked
    duplicate_of: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("articles.id"), default=None, index=True
    )

    __table_args__ = (
        Index("ix_articles_source_published", "source_id", "published_at"),
        Index("ix_articles_language", "language"),
        Index("ix_articles_published_at", "published_at"),
    )


class ArticleVersion(Base):
    __tablename__ = "article_versions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    article_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("articles.id"), index=True)
    version: Mapped[int]
    content_hash: Mapped[str] = mapped_column(String(64))

    # Full snapshot of the versioned fields
    title: Mapped[str] = mapped_column(Text)
    subtitle: Mapped[str | None] = mapped_column(Text, default=None)
    author: Mapped[str | None] = mapped_column(String(500), default=None)
    category: Mapped[str | None] = mapped_column(String(200), default=None)
    published_at: Mapped[datetime | None] = mapped_column(default=None)
    body: Mapped[str] = mapped_column(Text)

    # Field-level change flags relative to the previous version
    title_changed: Mapped[bool] = mapped_column(default=False)
    body_changed: Mapped[bool] = mapped_column(default=False)
    author_changed: Mapped[bool] = mapped_column(default=False)
    published_at_changed: Mapped[bool] = mapped_column(default=False)
    category_changed: Mapped[bool] = mapped_column(default=False)
    metadata_changed: Mapped[bool] = mapped_column(default=False)

    detected_at: Mapped[datetime] = mapped_column(server_default=text("now()"))

    __table_args__ = (UniqueConstraint("article_id", "version"),)


class Entity(Base, TimestampMixin):
    __tablename__ = "entities"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(500))
    normalized_name: Mapped[str] = mapped_column(String(500))
    entity_type: Mapped[EntityType] = mapped_column(str_enum(EntityType))

    __table_args__ = (UniqueConstraint("normalized_name", "entity_type"),)


class ArticleEntity(Base):
    __tablename__ = "article_entities"

    article_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("articles.id"), primary_key=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("entities.id"), primary_key=True, index=True
    )
    mention_count: Mapped[int] = mapped_column(default=1)
    salience: Mapped[float | None] = mapped_column(default=None)


class Topic(Base, TimestampMixin):
    __tablename__ = "topics"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(200), unique=True)


class ArticleTopic(Base):
    __tablename__ = "article_topics"

    article_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("articles.id"), primary_key=True)
    topic_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("topics.id"), primary_key=True, index=True
    )
    confidence: Mapped[float | None] = mapped_column(default=None)


class ArticleEmbedding(Base):
    __tablename__ = "article_embeddings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    article_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("articles.id"), index=True)
    embedding_kind: Mapped[EmbeddingKind] = mapped_column(str_enum(EmbeddingKind))
    embedding_model: Mapped[str] = mapped_column(String(200))
    embedding_dimension: Mapped[int]
    embedding_version: Mapped[int] = mapped_column(default=1)
    embedding: Mapped[Any] = mapped_column(Vector(1024))
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))

    __table_args__ = (
        UniqueConstraint("article_id", "embedding_kind", "embedding_model", "embedding_version"),
        # HNSW cosine index is created in the migration (needs raw DDL options)
    )
