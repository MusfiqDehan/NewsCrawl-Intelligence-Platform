"""BBC News (bbc.com/news) — English service.

Articles ship ReportageNewsArticle JSON-LD with headline/datePublished/author
but no articleBody, so the body always comes from the text-block components.
"""

from newscrawl_crawler.selectors.base import SelectorSet, register

BBC_NEWS = SelectorSet(
    title=("h1::text",),
    author=(
        '[data-testid="byline-name"]::text',
        "[class*=byline] [class*=name]::text",
    ),
    published_at=("time::attr(datetime)",),
    category=('[data-testid="navigation-link"] span::text',),
    body=(
        'article [data-component="text-block"] p',
        "article p",
        "main p",
    ),
    images=("article figure img::attr(src)",),
    tags=('[data-testid="topic-list"] a::text',),
    body_probe='article [data-component="text-block"]',
)

register("bbc-news", BBC_NEWS)
