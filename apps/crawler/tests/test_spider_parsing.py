"""NewsSpiderBase discovery parsing (sitemaps, RSS, sections) with fake responses."""

from datetime import UTC, datetime
from typing import Any

from newscrawl_contracts.enums import UrlType
from newscrawl_crawler.spiders.prothom_alo import ProthomAloSpider
from scrapy.http import HtmlResponse, Request, TextResponse, XmlResponse


def make_spider(source_config_dict: dict[str, Any]) -> ProthomAloSpider:
    return ProthomAloSpider(source_config=source_config_dict)


def xml_response(url: str, body: str) -> XmlResponse:
    return XmlResponse(url=url, body=body.encode(), request=Request(url))


class TestSitemapParsing:
    def test_sitemap_index_follows_recent_children(
        self, source_config_dict: dict[str, Any]
    ) -> None:
        spider = make_spider(source_config_dict)
        body = """<?xml version="1.0" encoding="UTF-8"?>
        <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
          <sitemap><loc>https://www.prothomalo.com/sitemap/sitemap-daily-2026-07-22.xml</loc>
            <lastmod>2026-07-22T23:00:00Z</lastmod></sitemap>
          <sitemap><loc>https://www.prothomalo.com/sitemap/sitemap-daily-2026-07-21.xml</loc>
            <lastmod>2026-07-21T23:00:00Z</lastmod></sitemap>
          <sitemap><loc>https://www.prothomalo.com/sitemap/sitemap-daily-2026-07-20.xml</loc>
            <lastmod>2026-07-20T23:00:00Z</lastmod></sitemap>
          <sitemap><loc>https://www.prothomalo.com/sitemap/sitemap-daily-2026-07-19.xml</loc>
            <lastmod>2026-07-19T23:00:00Z</lastmod></sitemap>
        </sitemapindex>"""
        links = spider._parse_sitemap(xml_response("https://www.prothomalo.com/sitemap.xml", body))
        assert len(links) == 3  # SITEMAP_INDEX_LIMIT most recent
        assert all(link.url_type == UrlType.SITEMAP for link in links)
        assert links[0].url.endswith("2026-07-22.xml")

    def test_urlset_classifies_articles(self, source_config_dict: dict[str, Any]) -> None:
        spider = make_spider(source_config_dict)
        body = """<?xml version="1.0" encoding="UTF-8"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
          <url><loc>https://www.prothomalo.com/bangladesh/3hiaapp62w</loc>
            <lastmod>2026-07-22T10:00:00Z</lastmod></url>
          <url><loc>https://www.prothomalo.com/world/india/59x5gajzy9</loc></url>
          <url><loc>https://www.prothomalo.com/collection/latest</loc></url>
        </urlset>"""
        links = spider._parse_sitemap(
            xml_response("https://www.prothomalo.com/sitemap/x.xml", body)
        )
        by_url = {link.url: link for link in links}
        assert by_url["https://www.prothomalo.com/bangladesh/3hiaapp62w"].url_type == (
            UrlType.ARTICLE
        )
        assert by_url["https://www.prothomalo.com/bangladesh/3hiaapp62w"].published_at == (
            datetime(2026, 7, 22, 10, 0, tzinfo=UTC)
        )
        assert by_url["https://www.prothomalo.com/world/india/59x5gajzy9"].url_type == (
            UrlType.ARTICLE
        )
        # Non-article page classified OTHER (low priority, not dropped)
        assert by_url["https://www.prothomalo.com/collection/latest"].url_type == UrlType.OTHER


class TestRssParsing:
    def test_rss_entries(self, source_config_dict: dict[str, Any]) -> None:
        spider = make_spider(source_config_dict)
        body = """<?xml version="1.0"?>
        <rss version="2.0"><channel><title>Feed</title>
          <item><title>Story 1</title>
            <link>https://www.prothomalo.com/politics/abcd1234xy</link>
            <pubDate>Wed, 22 Jul 2026 08:30:00 GMT</pubDate></item>
          <item><title>Story 2</title>
            <link>https://www.prothomalo.com/sports/zzzz9999aa</link></item>
        </channel></rss>"""
        response = TextResponse(
            url="https://feeds.example.com/rss.xml",
            body=body.encode(),
            request=Request("https://feeds.example.com/rss.xml"),
        )
        links = spider._parse_rss(response)
        assert len(links) == 2
        assert links[0].published_at == datetime(2026, 7, 22, 8, 30, tzinfo=UTC)
        assert all(link.url_type == UrlType.ARTICLE for link in links)


class TestSectionParsing:
    def test_article_links_matched_and_deduped(self, source_config_dict: dict[str, Any]) -> None:
        spider = make_spider(source_config_dict)
        body = """<html><body>
          <a href="/bangladesh/3hiaapp62w">story</a>
          <a href="https://www.prothomalo.com/bangladesh/3hiaapp62w">dup</a>
          <a href="/politics/c8pls9hsgx">another</a>
          <a href="/video">not article</a>
          <a href="https://other.example.com/bangladesh/zzzzzzzzzz">offsite-shaped</a>
        </body></html>"""
        response = HtmlResponse(
            url="https://www.prothomalo.com/bangladesh",
            body=body.encode(),
            request=Request("https://www.prothomalo.com/bangladesh"),
        )
        links = spider._parse_section(response)
        urls = sorted(link.url for link in links)
        assert urls == [
            "https://www.prothomalo.com/bangladesh/3hiaapp62w",
            "https://www.prothomalo.com/politics/c8pls9hsgx",
        ]

    def test_raw_hrefs_are_normalized_before_pattern_match(
        self, source_config_dict: dict[str, Any]
    ) -> None:
        """Patterns target the normalized form: trailing slashes and tracking
        params on raw hrefs must not hide article links (Naya Diganta links
        all carry trailing slashes)."""
        spider = make_spider(source_config_dict)
        body = """<html><body>
          <a href="/bangladesh/3hiaapp62w/">trailing slash</a>
          <a href="/politics/c8pls9hsgx?utm_source=fb&utm_medium=social">tracking params</a>
        </body></html>"""
        response = HtmlResponse(
            url="https://www.prothomalo.com/bangladesh",
            body=body.encode(),
            request=Request("https://www.prothomalo.com/bangladesh"),
        )
        links = spider._parse_section(response)
        assert len(links) == 2
        assert all(link.url_type == UrlType.ARTICLE for link in links)
