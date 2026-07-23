"""Kaler Kantho (kalerkantho.com).

Full NewsArticle JSON-LD including articleBody, so selectors are fallback
only. The site sits behind a Cloudflare JS challenge — requires_browser is
set in the source config and plain HTTP fetches will see HTTP 403.
"""

from newscrawl_crawler.selectors.base import SelectorSet, register

KALER_KANTHO = SelectorSet(
    title=("h1::text",),
    author=(
        "[class*=author] a::text",
        "[class*=author]::text",
        "[class*=reporter]::text",
    ),
    published_at=("time::attr(datetime)",),
    category=(".breadcrumb a::text", "nav[class*=breadcrumb] a::text"),
    body=(
        "article p",
        "div[class*=details] p",
        "main p",
    ),
    images=("article figure img::attr(src)", "article img::attr(src)"),
    tags=("[class*=tag] a::text",),
    body_probe="article p",
)

register("kaler-kantho", KALER_KANTHO)
