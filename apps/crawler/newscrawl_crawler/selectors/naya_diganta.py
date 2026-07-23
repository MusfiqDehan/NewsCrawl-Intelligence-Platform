"""Naya Diganta (dailynayadiganta.com) — SvelteKit frontend.

No JSON-LD at all: OpenGraph provides title/summary/image and everything
else comes from CSS selectors. The publish timestamp lives in the *title*
attribute of the <time> elements (ISO 8601), not in a datetime attribute.
"""

from newscrawl_crawler.selectors.base import SelectorSet, register

NAYA_DIGANTA = SelectorSet(
    title=("h1.post-title::text", "h1::text"),
    author=(
        ".post-reporters a::text",
        ".post-reporters h5::text",
        ".post_sources h5 a::text",
    ),
    published_at=(
        ".post-publish-date time::attr(title)",
        "time::attr(title)",
    ),
    category=(".breadcrumb a::text",),
    body=(
        "div.post-body .richtext p",
        "div.post-body p",
    ),
    images=(
        ".post-featured-image img::attr(src)",
        "figure img::attr(src)",
    ),
    body_probe="div.post-body",
)

register("naya-diganta", NAYA_DIGANTA)
