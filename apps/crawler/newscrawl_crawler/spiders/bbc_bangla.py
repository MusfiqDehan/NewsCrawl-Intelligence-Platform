"""BBC Bangla (Bengali service) spider."""

import newscrawl_crawler.selectors.bbc_bangla  # noqa: F401 - registers selectors
from newscrawl_crawler.spiders.base import NewsSpiderBase


class BbcBanglaSpider(NewsSpiderBase):
    name = "bbc-bangla"
    source_slug = "bbc-bangla"
