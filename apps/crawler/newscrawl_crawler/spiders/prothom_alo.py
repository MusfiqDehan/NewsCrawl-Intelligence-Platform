"""Prothom Alo spider.

All extraction logic lives in the selectors module and the shared extraction
engine; the spider only exists so the source has a dedicated entry point and
can override behaviour if the site diverges structurally.
"""

import newscrawl_crawler.selectors.prothom_alo  # noqa: F401 - registers selectors
from newscrawl_crawler.spiders.base import NewsSpiderBase


class ProthomAloSpider(NewsSpiderBase):
    name = "prothom-alo"
    source_slug = "prothom-alo"
