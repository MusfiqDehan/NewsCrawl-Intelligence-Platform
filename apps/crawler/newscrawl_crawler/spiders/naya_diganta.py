"""Naya Diganta spider."""

import newscrawl_crawler.selectors.naya_diganta  # noqa: F401 - registers selectors
from newscrawl_crawler.spiders.base import NewsSpiderBase


class NayaDigantaSpider(NewsSpiderBase):
    name = "naya-diganta"
    source_slug = "naya-diganta"
