"""Al Jazeera English spider."""

import newscrawl_crawler.selectors.aljazeera  # noqa: F401 - registers selectors
from newscrawl_crawler.spiders.base import NewsSpiderBase


class AlJazeeraSpider(NewsSpiderBase):
    name = "aljazeera"
    source_slug = "aljazeera"
