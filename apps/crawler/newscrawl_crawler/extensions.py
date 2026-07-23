"""Scrapy extension exporting crawl-plane metrics to Prometheus.

A single prometheus_client HTTP server is started per worker process (spider
passes run sequentially in one process, so the default registry is shared and
counters accumulate across passes). Signals feed live counters; on spider
close a selection of Scrapy's own stats is flushed into labelled gauges.
"""

import os
from typing import Any, Self

from prometheus_client import REGISTRY, Counter, Gauge, start_http_server
from scrapy import signals
from scrapy.crawler import Crawler
from scrapy.exceptions import NotConfigured
from scrapy.http import Request, Response
from scrapy.spiders import Spider

RESPONSES = Counter(
    "newscrawl_crawler_responses_total",
    "HTTP responses received by the crawl plane",
    ["source", "status"],
)
ITEMS = Counter(
    "newscrawl_crawler_items_total",
    "Items scraped (pages that produced a PageItem)",
    ["source"],
)
ERRORS = Counter(
    "newscrawl_crawler_errors_total",
    "Spider callback errors",
    ["source"],
)
BROWSER_PAGES = Counter(
    "newscrawl_crawler_browser_pages_total",
    "Pages fetched via the Playwright fallback",
    ["source"],
)
SPIDER_PASSES = Counter(
    "newscrawl_crawler_spider_passes_total",
    "Spider passes finished",
    ["source", "reason"],
)
LAST_PASS_STAT = Gauge(
    "newscrawl_crawler_last_pass",
    "Selected Scrapy stats from the most recent finished pass",
    ["source", "stat"],
)

# Scrapy stat key -> short label value exported per pass.
_EXPORTED_STATS = {
    "downloader/request_count": "requests",
    "downloader/response_count": "responses",
    "item_scraped_count": "items",
    "log_count/ERROR": "log_errors",
    "browser/retries": "browser_retries",
    "elapsed_time_seconds": "elapsed_seconds",
}

_server_started = False


def _ensure_metrics_server(port: int) -> None:
    global _server_started
    if not _server_started:
        start_http_server(port, registry=REGISTRY)
        _server_started = True


class PrometheusStatsExtension:
    def __init__(self, source_slug: str) -> None:
        self.source = source_slug

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        if not crawler.settings.getbool("PROMETHEUS_METRICS_ENABLED", True):
            raise NotConfigured
        port = int(
            os.environ.get(
                "CRAWLER_METRICS_PORT", crawler.settings.getint("PROMETHEUS_METRICS_PORT", 9101)
            )
        )
        _ensure_metrics_server(port)

        ext = cls(source_slug="unknown")
        crawler.signals.connect(ext.spider_opened, signal=signals.spider_opened)
        crawler.signals.connect(ext.spider_closed, signal=signals.spider_closed)
        crawler.signals.connect(ext.response_received, signal=signals.response_received)
        crawler.signals.connect(ext.item_scraped, signal=signals.item_scraped)
        crawler.signals.connect(ext.spider_error, signal=signals.spider_error)
        return ext

    def spider_opened(self, spider: Spider) -> None:
        source = getattr(spider, "source", None)
        self.source = getattr(source, "slug", None) or spider.name

    def response_received(self, response: Response, request: Request, spider: Spider) -> None:
        RESPONSES.labels(source=self.source, status=str(response.status)).inc()
        if request.meta.get("playwright"):
            BROWSER_PAGES.labels(source=self.source).inc()

    def item_scraped(self, item: Any, spider: Spider) -> None:
        ITEMS.labels(source=self.source).inc()

    def spider_error(self, failure: Any, response: Response, spider: Spider) -> None:
        ERRORS.labels(source=self.source).inc()

    def spider_closed(self, spider: Spider, reason: str) -> None:
        SPIDER_PASSES.labels(source=self.source, reason=reason).inc()
        stats = getattr(getattr(spider, "crawler", None), "stats", None)
        if stats is None:
            return
        snapshot = stats.get_stats()
        for stat_key, label in _EXPORTED_STATS.items():
            value = snapshot.get(stat_key)
            if isinstance(value, (int, float)):
                LAST_PASS_STAT.labels(source=self.source, stat=label).set(float(value))
