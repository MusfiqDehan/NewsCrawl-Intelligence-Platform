"""Scrapy settings.

Retries are deliberately disabled: the frontier owns retry scheduling with
exponential backoff, and double-retrying would corrupt its bookkeeping.
"""

from newscrawl_api.config import get_settings

from newscrawl_crawler.browser import should_abort_request

_settings = get_settings()

BOT_NAME = "newscrawl"

SPIDER_MODULES = ["newscrawl_crawler.spiders"]
NEWSPIDER_MODULE = "newscrawl_crawler.spiders"

TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"

# ── Playwright fallback ──────────────────────────────────────────────────────
# The handler only routes requests with meta {"playwright": True} through the
# browser; everything else stays on Scrapy's plain HTTP downloader.
DOWNLOAD_HANDLERS = {
    "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
    "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
}
PLAYWRIGHT_BROWSER_TYPE = "chromium"
PLAYWRIGHT_LAUNCH_OPTIONS = {
    "headless": True,
    "args": ["--disable-gpu", "--disable-dev-shm-usage", "--no-sandbox"],
}
PLAYWRIGHT_MAX_CONTEXTS = 4
PLAYWRIGHT_MAX_PAGES_PER_CONTEXT = 4
PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT = 45_000  # ms
PLAYWRIGHT_ABORT_REQUEST = should_abort_request
PLAYWRIGHT_RESTART_DISCONNECTED_BROWSER = True

# ── Identity & legal ─────────────────────────────────────────────────────────
USER_AGENT = _settings.crawler_user_agent
ROBOTSTXT_OBEY = True

# ── Politeness (per-source values are applied per crawl in the worker) ───────
DOWNLOAD_DELAY = 2.0
RANDOMIZE_DOWNLOAD_DELAY = True
CONCURRENT_REQUESTS = 8
CONCURRENT_REQUESTS_PER_DOMAIN = 2
AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 1.0
AUTOTHROTTLE_MAX_DELAY = 30.0
AUTOTHROTTLE_TARGET_CONCURRENCY = 1.0

# ── Timeouts & retries ───────────────────────────────────────────────────────
DOWNLOAD_TIMEOUT = 30
RETRY_ENABLED = False  # the frontier owns retries (backoff + max attempts)
DOWNLOAD_MAXSIZE = 10 * 1024 * 1024  # 10 MB hard cap per response

# ── Middlewares ──────────────────────────────────────────────────────────────
DOWNLOADER_MIDDLEWARES = {
    # Cluster-wide per-domain politeness (shared Redis token bucket)
    "newscrawl_crawler.middlewares.DistributedPolitenessMiddleware": 543,
}
POLITENESS_REQUESTS_PER_SECOND = 0.5
POLITENESS_BURST = 2

# ── Pipelines ────────────────────────────────────────────────────────────────
ITEM_PIPELINES = {
    "newscrawl_crawler.pipelines.storage.RawHtmlStoragePipeline": 100,
    "newscrawl_crawler.pipelines.frontier.FrontierUpdatePipeline": 200,
}

# ── Observability ────────────────────────────────────────────────────────────
EXTENSIONS = {
    "scrapy.extensions.closespider.CloseSpider": 500,
    "newscrawl_crawler.extensions.PrometheusStatsExtension": 510,
}
PROMETHEUS_METRICS_ENABLED = True
PROMETHEUS_METRICS_PORT = 9101  # override with CRAWLER_METRICS_PORT env var

# ── Misc ─────────────────────────────────────────────────────────────────────
TELNETCONSOLE_ENABLED = False
COOKIES_ENABLED = False
COMPRESSION_ENABLED = True
LOG_LEVEL = _settings.log_level
REQUEST_FINGERPRINTER_IMPLEMENTATION = "2.7"

DEFAULT_REQUEST_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "bn,en;q=0.8",
}
