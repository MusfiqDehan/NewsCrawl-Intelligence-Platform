"""Source slug → spider class registry."""

from newscrawl_crawler.spiders.aljazeera import AlJazeeraSpider
from newscrawl_crawler.spiders.base import NewsSpiderBase
from newscrawl_crawler.spiders.bbc_bangla import BbcBanglaSpider
from newscrawl_crawler.spiders.bbc_news import BbcNewsSpider
from newscrawl_crawler.spiders.kaler_kantho import KalerKanthoSpider
from newscrawl_crawler.spiders.naya_diganta import NayaDigantaSpider
from newscrawl_crawler.spiders.prothom_alo import ProthomAloSpider

SPIDERS: dict[str, type[NewsSpiderBase]] = {
    spider.source_slug: spider
    for spider in (
        ProthomAloSpider,
        KalerKanthoSpider,
        NayaDigantaSpider,
        BbcNewsSpider,
        BbcBanglaSpider,
        AlJazeeraSpider,
    )
}


def spider_for(slug: str) -> type[NewsSpiderBase]:
    try:
        return SPIDERS[slug]
    except KeyError:
        raise KeyError(
            f"No spider registered for source {slug!r}. Known: {sorted(SPIDERS)}"
        ) from None
