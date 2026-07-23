"""BBC News (English service) spider."""

import newscrawl_crawler.selectors.bbc_news  # noqa: F401 - registers selectors
from newscrawl_crawler.spiders.base import NewsSpiderBase


class BbcNewsSpider(NewsSpiderBase):
    name = "bbc-news"
    source_slug = "bbc-news"
