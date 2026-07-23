"""Playwright fallback policy: routing, resource blocking, runtime detection."""

import uuid
from dataclasses import dataclass
from typing import Any

import scrapy
from newscrawl_contracts.enums import UrlType
from newscrawl_crawler.browser import browser_request_meta, should_abort_request
from newscrawl_crawler.items import PageItem
from newscrawl_crawler.spiders.prothom_alo import ProthomAloSpider
from scrapy.http import HtmlResponse, Request


@dataclass
class FakePlaywrightRequest:
    url: str
    resource_type: str


class TestResourceBlocking:
    def test_heavy_resource_types_are_aborted(self) -> None:
        for resource_type in ("image", "media", "font"):
            request = FakePlaywrightRequest("https://www.kalerkantho.com/x.png", resource_type)
            assert should_abort_request(request)  # type: ignore[arg-type]

    def test_document_and_script_are_allowed(self) -> None:
        for resource_type in ("document", "script", "xhr", "fetch", "stylesheet"):
            request = FakePlaywrightRequest("https://www.kalerkantho.com/page", resource_type)
            assert not should_abort_request(request)  # type: ignore[arg-type]

    def test_ad_and_tracker_hosts_are_aborted_regardless_of_type(self) -> None:
        request = FakePlaywrightRequest(
            "https://securepubads.g.doubleclick.net/tag/js/gpt.js", "script"
        )
        assert should_abort_request(request)  # type: ignore[arg-type]
        request = FakePlaywrightRequest("https://www.googletagmanager.com/gtm.js", "script")
        assert should_abort_request(request)  # type: ignore[arg-type]


class TestBrowserRequestMeta:
    def test_meta_routes_through_playwright_with_shared_context(self) -> None:
        meta = browser_request_meta("kaler-kantho")
        assert meta["playwright"] is True
        # Context named per source → cookies (e.g. solved CF challenge) reused
        assert meta["playwright_context"] == "kaler-kantho"
        assert meta["playwright_page_goto_kwargs"]["wait_until"] == "domcontentloaded"


JS_SHELL_HTML = b"""<html><head><title>Loading...</title></head>
<body><div id="root"></div><script src="/app.js"></script></body></html>"""


def article_response(meta_extra: dict[str, Any] | None = None) -> HtmlResponse:
    url = "https://www.prothomalo.com/bangladesh/abcd1234xy"
    meta: dict[str, Any] = {
        "url_id": 1,
        "url_type": UrlType.ARTICLE,
        "fetch_started": __import__("datetime").datetime.now(__import__("datetime").UTC),
    }
    meta.update(meta_extra or {})
    request = Request(url, meta=meta)
    return HtmlResponse(url=url, body=JS_SHELL_HTML, request=request)


async def collect(agen: Any) -> list[Any]:
    return [x async for x in agen]


class TestRuntimeDetection:
    async def test_unusable_http_article_is_retried_via_browser(
        self, source_config_dict: dict[str, Any]
    ) -> None:
        spider = ProthomAloSpider(source_config=source_config_dict)
        results = await collect(spider.parse_page(article_response()))
        assert len(results) == 1
        retry = results[0]
        assert isinstance(retry, scrapy.Request)
        assert retry.meta["playwright"] is True
        assert retry.meta["browser_retry"] is True
        assert retry.dont_filter

    async def test_browser_retry_happens_only_once(
        self, source_config_dict: dict[str, Any]
    ) -> None:
        spider = ProthomAloSpider(source_config=source_config_dict)
        response = article_response({"playwright": True, "browser_retry": True})
        results = await collect(spider.parse_page(response))
        assert len(results) == 1
        item = results[0]
        assert isinstance(item, PageItem)
        assert item.fetch_method == "browser"
        # Unusable extraction flows to the pipeline, which drops + records it
        assert item.extracted is not None
        assert not item.extracted["body"]

    async def test_usable_http_article_is_not_retried(
        self, source_config_dict: dict[str, Any], prothom_alo_html: str
    ) -> None:
        spider = ProthomAloSpider(source_config=source_config_dict)
        url = "https://www.prothomalo.com/bangladesh/abcd1234xy"
        request = Request(
            url,
            meta={
                "url_id": 1,
                "url_type": UrlType.ARTICLE,
                "fetch_started": __import__("datetime").datetime.now(__import__("datetime").UTC),
            },
        )
        response = HtmlResponse(url=url, body=prothom_alo_html.encode(), request=request)
        results = await collect(spider.parse_page(response))
        assert len(results) == 1
        item = results[0]
        assert isinstance(item, PageItem)
        assert item.fetch_method == "http"
        assert item.extracted is not None and item.extracted["title"]


class TestBrowserFailureClassification:
    def test_playwright_errors_are_browser_failures(self) -> None:
        from newscrawl_contracts.enums import FailureCategory
        from playwright.async_api import TimeoutError as PlaywrightTimeout
        from twisted.python.failure import Failure

        failure = Failure(PlaywrightTimeout("Timeout 45000ms exceeded."))  # type: ignore[no-untyped-call]
        category, message = ProthomAloSpider._classify_failure(failure)
        assert category == FailureCategory.BROWSER_FAILURE
        assert "playwright" in message


class TestRequiresBrowserRouting:
    def _kaler_kantho_spider(self) -> Any:
        config = {
            "id": str(uuid.uuid4()),
            "name": "Kaler Kantho",
            "slug": "kaler-kantho",
            "base_url": "https://www.kalerkantho.com",
            "language": "bn",
            "country": "BD",
            "allowed_domains": ["kalerkantho.com"],
            "article_url_patterns": [r"^https://www\.kalerkantho\.com/.+"],
            "requires_browser": True,
        }
        from newscrawl_crawler.spiders.kaler_kantho import KalerKanthoSpider

        return KalerKanthoSpider(source_config=config)

    def test_browser_source_pages_route_through_playwright(self) -> None:
        spider = self._kaler_kantho_spider()
        for url_type in (UrlType.ARTICLE, UrlType.HOMEPAGE, UrlType.SECTION, UrlType.OTHER):
            assert spider._needs_browser(url_type)

    def test_xml_feeds_never_need_browser(self) -> None:
        spider = self._kaler_kantho_spider()
        for url_type in (UrlType.SITEMAP, UrlType.RSS):
            assert not spider._needs_browser(url_type)

    def test_plain_http_source_never_routes_through_browser(
        self, source_config_dict: dict[str, Any]
    ) -> None:
        spider = ProthomAloSpider(source_config=source_config_dict)
        assert not spider._needs_browser(UrlType.ARTICLE)
