"""Al Jazeera English (aljazeera.com).

NewsArticle JSON-LD carries the metadata (headline, dates, author) but not
the body — the body is the wysiwyg rich-text container.
"""

from newscrawl_crawler.selectors.base import SelectorSet, register

ALJAZEERA = SelectorSet(
    title=("h1::text", "header h1 span::text"),
    subtitle=("p.article__subhead::text", "em.article__subhead::text"),
    author=(
        ".article-author-name-item a::text",
        ".article-author-name-item::text",
        "[class*=author] a::text",
    ),
    published_at=(
        ".article-dates .date-simple span[aria-hidden]::text",
        "time::attr(datetime)",
    ),
    body=(
        "div.wysiwyg p",
        "main .wysiwyg p",
    ),
    images=("main figure img::attr(src)",),
    tags=(".article-tags a::text",),
    body_probe="div.wysiwyg",
)

register("aljazeera", ALJAZEERA)
