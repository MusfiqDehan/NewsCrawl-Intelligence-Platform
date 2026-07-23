"""Initial source configurations.

BBC is represented as two sources (English and Bangla services) sharing one
spider architecture — each source stays independently schedulable and a layout
change in one never affects the other.
"""

from typing import Any

SOURCES: list[dict[str, Any]] = [
    {
        "name": "Prothom Alo",
        "slug": "prothom-alo",
        "base_url": "https://www.prothomalo.com",
        "language": "bn",
        "country": "BD",
        "allowed_domains": ["prothomalo.com"],
        "article_url_patterns": [
            r"^https://www\.prothomalo\.com/[a-z-]+(/[a-z-]+)*/[a-z0-9]{8,}$",
        ],
        "section_urls": [
            "https://www.prothomalo.com/bangladesh",
            "https://www.prothomalo.com/politics",
            "https://www.prothomalo.com/world",
            "https://www.prothomalo.com/business",
            "https://www.prothomalo.com/sports",
            "https://www.prothomalo.com/entertainment",
            "https://www.prothomalo.com/opinion",
        ],
        "sitemap_urls": ["https://www.prothomalo.com/sitemap.xml"],
        "rss_urls": [],
        "crawl_frequency_minutes": 30,
        "rate_limit_delay_seconds": 2.0,
        "max_concurrency": 2,
        "requires_browser": False,
        "extraction_strategy": "selectors",
        "source_weight": 1.0,
    },
    {
        "name": "Kaler Kantho",
        "slug": "kaler-kantho",
        "base_url": "https://www.kalerkantho.com",
        "language": "bn",
        "country": "BD",
        "allowed_domains": ["kalerkantho.com"],
        "article_url_patterns": [
            r"^https://www\.kalerkantho\.com/(online|print)/[a-zA-Z-]+/\d{4}/\d{2}/\d{2}/\d+$",
        ],
        "section_urls": [
            "https://www.kalerkantho.com/online/national",
            "https://www.kalerkantho.com/online/country-news",
            "https://www.kalerkantho.com/online/Politics",
            "https://www.kalerkantho.com/online/world",
            "https://www.kalerkantho.com/online/business",
            "https://www.kalerkantho.com/online/sport",
        ],
        "sitemap_urls": ["https://www.kalerkantho.com/sitemap.xml"],
        "rss_urls": [],
        "crawl_frequency_minutes": 30,
        "rate_limit_delay_seconds": 2.0,
        "max_concurrency": 2,
        # Cloudflare JS challenge blocks plain HTTP fetches (403)
        "requires_browser": True,
        "extraction_strategy": "selectors",
        "source_weight": 1.0,
    },
    {
        "name": "Naya Diganta",
        "slug": "naya-diganta",
        "base_url": "https://www.dailynayadiganta.com",
        "language": "bn",
        "country": "BD",
        "allowed_domains": ["dailynayadiganta.com"],
        "article_url_patterns": [
            # Articles end in a 10-14 char base62 id containing at least one
            # uppercase letter or digit (distinguishes ids from section slugs)
            r"^https://www\.dailynayadiganta\.com/[a-z-]+(/[a-z-]+)*"
            r"/(?=[a-z0-9]*[A-Z0-9])[A-Za-z0-9]{10,14}$",
        ],
        "section_urls": [
            "https://www.dailynayadiganta.com/bangladesh/",
            "https://www.dailynayadiganta.com/international/",
            "https://www.dailynayadiganta.com/economy/",
            "https://www.dailynayadiganta.com/sports/",
            "https://www.dailynayadiganta.com/opinions/",
        ],
        "sitemap_urls": [],
        "rss_urls": [],
        "crawl_frequency_minutes": 60,
        "rate_limit_delay_seconds": 2.5,
        "max_concurrency": 2,
        "requires_browser": False,
        "extraction_strategy": "selectors",
        "source_weight": 0.8,
    },
    {
        "name": "BBC News",
        "slug": "bbc-news",
        "base_url": "https://www.bbc.com",
        "language": "en",
        "country": "GB",
        "allowed_domains": ["bbc.com", "bbc.co.uk"],
        "article_url_patterns": [
            # RSS links use bbc.co.uk, site links use bbc.com — accept both
            r"^https://www\.bbc\.(com|co\.uk)/news/articles/[a-z0-9]+$",
            r"^https://www\.bbc\.(com|co\.uk)/news/[a-z-]+-\d+$",
        ],
        "section_urls": [
            "https://www.bbc.com/news",
            "https://www.bbc.com/news/world",
            "https://www.bbc.com/news/world/asia",
        ],
        "sitemap_urls": ["https://www.bbc.com/sitemaps/https-index-com-news.xml"],
        "rss_urls": [
            "https://feeds.bbci.co.uk/news/rss.xml",
            "https://feeds.bbci.co.uk/news/world/rss.xml",
            "https://feeds.bbci.co.uk/news/world/asia/rss.xml",
        ],
        "crawl_frequency_minutes": 30,
        "rate_limit_delay_seconds": 1.5,
        "max_concurrency": 3,
        "requires_browser": False,
        "extraction_strategy": "selectors",
        "source_weight": 1.2,
    },
    {
        "name": "BBC Bangla",
        "slug": "bbc-bangla",
        "base_url": "https://www.bbc.com/bengali",
        "language": "bn",
        "country": "GB",
        "allowed_domains": ["bbc.com", "bbc.co.uk"],
        "article_url_patterns": [
            r"^https://www\.bbc\.(com|co\.uk)/bengali/articles/[a-z0-9]+$",
            r"^https://www\.bbc\.(com|co\.uk)/bengali/news-\d+$",
        ],
        "section_urls": ["https://www.bbc.com/bengali"],
        "sitemap_urls": [],
        "rss_urls": ["https://feeds.bbci.co.uk/bengali/rss.xml"],
        "crawl_frequency_minutes": 60,
        "rate_limit_delay_seconds": 1.5,
        "max_concurrency": 2,
        "requires_browser": False,
        "extraction_strategy": "selectors",
        "source_weight": 1.1,
    },
    {
        "name": "Al Jazeera",
        "slug": "aljazeera",
        "base_url": "https://www.aljazeera.com",
        "language": "en",
        "country": "QA",
        "allowed_domains": ["aljazeera.com"],
        "article_url_patterns": [
            r"^https://www\.aljazeera\.com/(news|features|economy|sports|opinions)/\d{4}/\d{1,2}/\d{1,2}/[a-z0-9-]+$",
        ],
        "section_urls": [
            "https://www.aljazeera.com/news/",
            "https://www.aljazeera.com/news/asia/",
            "https://www.aljazeera.com/economy/",
        ],
        "sitemap_urls": ["https://www.aljazeera.com/sitemap.xml"],
        "rss_urls": ["https://www.aljazeera.com/xml/rss/all.xml"],
        "crawl_frequency_minutes": 30,
        "rate_limit_delay_seconds": 2.0,
        "max_concurrency": 2,
        "requires_browser": False,
        "extraction_strategy": "selectors",
        "source_weight": 1.0,
        # robots.txt disallows /*?traffic_source= etc. — stripping these keeps
        # frontier URLs both deduplicated and robots-compliant
        "url_normalization": {
            "extra_tracking_params": ["traffic_source", "gb", "playlist"],
        },
    },
]
