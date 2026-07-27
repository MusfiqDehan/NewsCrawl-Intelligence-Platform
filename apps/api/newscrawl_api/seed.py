"""Idempotent database seeding: news sources + initial admin user.

Run with:  python -m newscrawl_api.seed
"""

import asyncio

from newscrawl_contracts.enums import UserRole
from sqlalchemy import select

from newscrawl_api.config import get_settings
from newscrawl_api.db import dispose_engine, session_scope
from newscrawl_api.models import Source, User
from newscrawl_api.observability import configure_logging, get_logger
from newscrawl_api.seed_data import SOURCES
from newscrawl_api.services.auth import hash_password


async def seed() -> None:
    settings = get_settings()
    log = get_logger()

    async with session_scope() as db:
        # Sources: insert new ones, never overwrite operator-tuned configs.
        existing_slugs = set((await db.scalars(select(Source.slug))).all())
        created = 0
        for source_config in SOURCES:
            if source_config["slug"] in existing_slugs:
                continue
            db.add(Source(**source_config))
            created += 1
        log.info("sources_seeded", created=created, skipped=len(SOURCES) - created)

        # Backfill selectors onto pre-existing rows that have never had them
        # set. NULL means "never touched" — an operator save always writes a
        # concrete value (even {}), so this only ever affects rows nobody has
        # edited yet and is safe to rerun indefinitely.
        backfilled = 0
        for source_config in SOURCES:
            if source_config["slug"] not in existing_slugs or "selectors" not in source_config:
                continue
            existing = await db.scalar(select(Source).where(Source.slug == source_config["slug"]))
            if existing is not None and existing.selectors is None:
                existing.selectors = source_config["selectors"]
                backfilled += 1
        if backfilled:
            log.info("source_selectors_backfilled", count=backfilled)

        # Admin user
        admin_email = settings.admin_email.lower()
        admin = await db.scalar(select(User).where(User.email == admin_email))
        if admin is None:
            db.add(
                User(
                    email=admin_email,
                    password_hash=hash_password(settings.admin_password),
                    role=UserRole.ADMIN,
                )
            )
            log.info("admin_user_created", email=admin_email)
        else:
            log.info("admin_user_exists", email=admin_email)


async def _run() -> None:
    try:
        await seed()
    finally:
        await dispose_engine()


def main() -> None:
    configure_logging("seed", get_settings().log_level)
    asyncio.run(_run())


if __name__ == "__main__":
    main()
