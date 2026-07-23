"""Schema contract tests — catch accidental drops of critical tables/indexes."""

from newscrawl_api.models import Base

EXPECTED_TABLES = {
    "sources",
    "users",
    "crawl_jobs",
    "crawl_workers",
    "crawl_urls",
    "crawl_attempts",
    "crawl_events",
    "articles",
    "article_versions",
    "entities",
    "article_entities",
    "topics",
    "article_topics",
    "article_embeddings",
    "processing_jobs",
    "llm_extractions",
    "system_metrics",
}


def test_all_expected_tables_defined() -> None:
    assert set(Base.metadata.tables.keys()) == EXPECTED_TABLES


def _unique_constraint_columns(table_name: str) -> set[tuple[str, ...]]:
    from sqlalchemy import UniqueConstraint

    table = Base.metadata.tables[table_name]
    return {
        tuple(c.name for c in constraint.columns)
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }


def test_url_hash_is_unique() -> None:
    assert ("url_hash",) in _unique_constraint_columns("crawl_urls")


def test_high_volume_tables_are_partitioned() -> None:
    for table_name, column in [("crawl_attempts", "attempted_at"), ("crawl_events", "created_at")]:
        table = Base.metadata.tables[table_name]
        assert table.dialect_options["postgresql"]["partition_by"] == f"RANGE ({column})"
        # Partition key must be part of the primary key
        assert column in {c.name for c in table.primary_key.columns}


def test_frontier_claim_index_is_partial() -> None:
    crawl_urls = Base.metadata.tables["crawl_urls"]
    claim_index = next(ix for ix in crawl_urls.indexes if ix.name == "ix_crawl_urls_claim")
    assert claim_index.dialect_options["postgresql"]["where"] is not None


def test_embeddings_are_model_versioned() -> None:
    unique_columns = _unique_constraint_columns("article_embeddings")
    assert (
        "article_id",
        "embedding_kind",
        "embedding_model",
        "embedding_version",
    ) in unique_columns
