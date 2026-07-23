"""Seed the frontier with a source's discovery URLs (sitemaps, RSS, sections).

Run with:  python -m newscrawl_crawler.seed_frontier --source prothom-alo

In production this is done by creating a crawl job through the API; this CLI
exists for local development and operational recovery.
"""

import argparse
import asyncio

from newscrawl_api.config import get_settings
from newscrawl_api.db import dispose_engine, session_scope
from newscrawl_api.models import Source
from newscrawl_api.observability import configure_logging, get_logger
from newscrawl_api.services.frontier import DiscoveredUrl, Frontier
from newscrawl_contracts.enums import UrlType
from sqlalchemy import select


def discovery_urls(source: Source) -> list[DiscoveredUrl]:
    urls: list[DiscoveredUrl] = [DiscoveredUrl(url=source.base_url, url_type=UrlType.HOMEPAGE)]
    urls += [DiscoveredUrl(url=u, url_type=UrlType.SITEMAP) for u in source.sitemap_urls]
    urls += [DiscoveredUrl(url=u, url_type=UrlType.RSS) for u in source.rss_urls]
    urls += [DiscoveredUrl(url=u, url_type=UrlType.SECTION) for u in source.section_urls]
    return urls


async def seed(slug: str | None) -> None:
    log = get_logger("seed_frontier")
    frontier = Frontier()
    async with session_scope() as db:
        query = select(Source).where(Source.enabled.is_(True))
        if slug:
            query = query.where(Source.slug == slug)
        sources = (await db.scalars(query)).all()
        if not sources:
            log.warning("no_sources_matched", slug=slug)
        for source in sources:
            added = await frontier.add_urls(db, source, discovery_urls(source))
            log.info("frontier_seeded", source=source.slug, added=added)


async def _run(slug: str | None) -> None:
    try:
        await seed(slug)
    finally:
        await dispose_engine()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=None)
    args = parser.parse_args()
    configure_logging("seed_frontier", get_settings().log_level)
    asyncio.run(_run(args.source))


if __name__ == "__main__":
    main()
