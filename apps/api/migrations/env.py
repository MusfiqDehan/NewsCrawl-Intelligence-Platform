"""Alembic environment — async engine, URL from application settings."""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection, pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from newscrawl_api.config import get_settings
from newscrawl_api.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", get_settings().database_url)

target_metadata = Base.metadata


# Indexes created with raw DDL (HNSW / trigram) — invisible to the ORM metadata.
MANUALLY_MANAGED_INDEXES = {"ix_article_embeddings_hnsw", "ix_articles_title_trgm"}


def include_object(obj: object, name: str | None, type_: str, *_: object) -> bool:
    # Partition child tables (crawl_attempts_p_2026m07, ...) are managed by raw
    # DDL, not by the ORM — don't let autogenerate try to drop them.
    if type_ == "table" and name is not None and "_p_" in name:
        return False
    if type_ == "index" and name in MANUALLY_MANAGED_INDEXES:
        return False
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_object=include_object,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
