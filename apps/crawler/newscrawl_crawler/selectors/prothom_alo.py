"""Prothom Alo (prothomalo.com) — Quintype platform.

Articles ship complete schema.org NewsArticle JSON-LD (headline, articleBody,
datePublished, author), so selectors below are the fallback layer only.
"""

from newscrawl_crawler.selectors.base import SelectorSet, register

PROTHOM_ALO = SelectorSet(
    title=(
        "h1.IiRps::text",
        "h1[class*=headline]::text",
        "h1::text",
    ),
    author=(
        ".contributor-name::text",
        ".author-name::text",
        "span[class*=author] a::text",
    ),
    published_at=(
        "time::attr(datetime)",
        ".storyPageMetaData-m__publish-time__19bdV time::attr(datetime)",
    ),
    category=(
        ".breadcrumb a::text",
        "a[class*=section-name]::text",
    ),
    body=(
        "div.story-element-text p",
        "div.story-element-text",
        "div[class*=story-content] p",
    ),
    images=(
        "div.story-element-image img::attr(src)",
        "figure img::attr(src)",
    ),
    tags=(".tags a::text", "a[class*=tag]::text"),
    body_probe="div.story-element-text",
)

register("prothom-alo", PROTHOM_ALO)
