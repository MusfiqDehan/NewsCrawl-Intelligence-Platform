"""Kaler Kantho spider (Cloudflare-protected: crawls via the browser path)."""

import newscrawl_crawler.selectors.kaler_kantho  # noqa: F401 - registers selectors
from newscrawl_crawler.spiders.base import NewsSpiderBase


class KalerKanthoSpider(NewsSpiderBase):
    name = "kaler-kantho"
    source_slug = "kaler-kantho"
