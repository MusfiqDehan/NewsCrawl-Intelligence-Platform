"""Prometheus stats extension: signal handlers update the right metrics."""

from types import SimpleNamespace
from typing import Any

from newscrawl_crawler.extensions import PrometheusStatsExtension
from prometheus_client import REGISTRY
from scrapy.http import Request, TextResponse


def _counter_value(name: str, **labels: str) -> float:
    return REGISTRY.get_sample_value(f"{name}_total", labels) or 0.0


def _gauge_value(name: str, **labels: str) -> float:
    return REGISTRY.get_sample_value(name, labels) or 0.0


def make_spider(slug: str) -> Any:
    return SimpleNamespace(name=f"{slug}-spider", source=SimpleNamespace(slug=slug))


class TestSignalHandlers:
    def test_spider_opened_binds_source_label(self) -> None:
        ext = PrometheusStatsExtension(source_slug="unknown")
        ext.spider_opened(make_spider("ext-test"))
        assert ext.source == "ext-test"

    def test_response_received_counts_status(self) -> None:
        ext = PrometheusStatsExtension(source_slug="ext-resp")
        request = Request("https://example.com/a")
        response = TextResponse(url="https://example.com/a", status=200, body=b"x", request=request)
        before = _counter_value("newscrawl_crawler_responses", source="ext-resp", status="200")
        ext.response_received(response, request, make_spider("ext-resp"))
        after = _counter_value("newscrawl_crawler_responses", source="ext-resp", status="200")
        assert after == before + 1

    def test_browser_pages_counted_for_playwright_requests(self) -> None:
        ext = PrometheusStatsExtension(source_slug="ext-browser")
        request = Request("https://example.com/b", meta={"playwright": True})
        response = TextResponse(url="https://example.com/b", status=200, body=b"x", request=request)
        before = _counter_value("newscrawl_crawler_browser_pages", source="ext-browser")
        ext.response_received(response, request, make_spider("ext-browser"))
        after = _counter_value("newscrawl_crawler_browser_pages", source="ext-browser")
        assert after == before + 1

    def test_items_and_errors_counted(self) -> None:
        ext = PrometheusStatsExtension(source_slug="ext-items")
        spider = make_spider("ext-items")
        ext.item_scraped({}, spider)
        ext.spider_error(None, None, spider)  # type: ignore[arg-type]
        assert _counter_value("newscrawl_crawler_items", source="ext-items") == 1
        assert _counter_value("newscrawl_crawler_errors", source="ext-items") == 1

    def test_spider_closed_exports_pass_stats(self) -> None:
        ext = PrometheusStatsExtension(source_slug="ext-close")

        class FakeStats:
            def get_stats(self) -> dict[str, Any]:
                return {"downloader/request_count": 7, "item_scraped_count": 3}

        spider = SimpleNamespace(
            name="ext-close-spider",
            source=SimpleNamespace(slug="ext-close"),
            crawler=SimpleNamespace(stats=FakeStats()),
        )
        ext.spider_closed(spider, reason="finished")  # type: ignore[arg-type]
        assert (
            _counter_value("newscrawl_crawler_spider_passes", source="ext-close", reason="finished")
            == 1
        )
        assert _gauge_value("newscrawl_crawler_last_pass", source="ext-close", stat="requests") == 7
        assert _gauge_value("newscrawl_crawler_last_pass", source="ext-close", stat="items") == 3
