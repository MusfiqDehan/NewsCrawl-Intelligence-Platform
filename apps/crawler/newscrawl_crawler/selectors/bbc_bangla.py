"""BBC Bangla (bbc.com/bengali) — Bengali service.

Same Simorgh platform as BBC News but a different page composition: the body
paragraphs live in dir-attributed rich-text containers under <main>.
"""

from newscrawl_crawler.selectors.base import SelectorSet, register

BBC_BANGLA = SelectorSet(
    title=("h1::text",),
    author=(
        '[data-testid="byline-name"]::text',
        "[class*=byline] [class*=name]::text",
    ),
    published_at=("time::attr(datetime)",),
    body=(
        # [dir] scoping skips image captions and promo blocks
        "main [dir] p",
        "main p",
    ),
    images=("main figure img::attr(src)",),
    tags=('[data-testid="topic-list"] a::text',),
    body_probe="main [dir] p",
)

register("bbc-bangla", BBC_BANGLA)
