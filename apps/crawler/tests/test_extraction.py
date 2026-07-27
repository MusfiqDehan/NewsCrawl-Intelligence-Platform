"""Extraction engine tests, including the Prothom Alo fixture contract."""

import re

from newscrawl_crawler.extraction import extract_article
from newscrawl_crawler.selectors import SelectorSet

BENGALI_CHAR = re.compile(r"[ঀ-৿]")


class TestProthomAloContract:
    """Contract: extraction from a saved real page must keep working.

    If Prothom Alo changes markup, refresh the fixture and fix selectors —
    this test failing is the early-warning signal."""

    def test_jsonld_extraction(
        self, prothom_alo_html: str, prothom_alo_selectors: SelectorSet
    ) -> None:
        article = extract_article(prothom_alo_html, selectors=prothom_alo_selectors)
        assert article.is_usable
        assert article.extraction_method == "json_ld"
        assert article.extraction_confidence >= 0.9
        assert article.title and BENGALI_CHAR.search(article.title)
        assert article.body and len(article.body) > 500
        assert BENGALI_CHAR.search(article.body)
        assert article.author
        assert article.published_at and article.published_at.startswith("20")
        assert article.category
        assert article.canonical_url and "prothomalo.com" in article.canonical_url

    def test_selector_fallback_without_jsonld(
        self, prothom_alo_html: str, prothom_alo_selectors: SelectorSet
    ) -> None:
        # Strip JSON-LD to force the selector path
        stripped = re.sub(
            r'<script type="application/ld\+json">.*?</script>',
            "",
            prothom_alo_html,
            flags=re.S,
        )
        article = extract_article(stripped, selectors=prothom_alo_selectors)
        assert article.body, "selector fallback must recover the body"
        assert BENGALI_CHAR.search(article.body)
        assert article.extraction_method == "selectors"
        assert article.extraction_confidence < 0.9


class TestGenericExtraction:
    def test_opengraph_only(self) -> None:
        html = """
        <html><head>
        <meta property="og:title" content="OG Title"/>
        <meta property="og:description" content="OG description"/>
        <meta property="article:published_time" content="2026-07-01T10:00:00Z"/>
        <meta property="og:url" content="https://example.com/canonical"/>
        </head><body><p>hi</p></body></html>
        """
        article = extract_article(html)
        assert article.title == "OG Title"
        assert article.summary == "OG description"
        assert article.published_at == "2026-07-01T10:00:00Z"
        assert article.canonical_url == "https://example.com/canonical"
        assert not article.is_usable  # no body → not usable

    def test_jsonld_graph_form(self) -> None:
        html = """
        <html><head><script type="application/ld+json">
        {"@context":"https://schema.org","@graph":[
          {"@type":"Organization","name":"Pub"},
          {"@type":"NewsArticle","headline":"Graph Headline",
           "articleBody":"Body text here.","datePublished":"2026-01-01T00:00:00Z",
           "author":{"@type":"Person","name":"Jane"}}
        ]}</script></head><body></body></html>
        """
        article = extract_article(html)
        assert article.title == "Graph Headline"
        assert article.body == "Body text here."
        assert article.author == "Jane"
        assert article.extraction_method == "json_ld"

    def test_author_list(self) -> None:
        html = """
        <html><head><script type="application/ld+json">
        {"@type":"NewsArticle","headline":"H","articleBody":"B",
         "author":[{"@type":"Person","name":"A One"},{"@type":"Person","name":"B Two"}]}
        </script></head><body></body></html>
        """
        article = extract_article(html)
        assert article.author == "A One, B Two"

    def test_malformed_jsonld_ignored(self) -> None:
        html = """
        <html><head>
        <script type="application/ld+json">{not valid json!!</script>
        <meta property="og:title" content="Fallback"/>
        </head><body></body></html>
        """
        article = extract_article(html)
        assert article.title == "Fallback"

    def test_escaped_html_body_becomes_plain_text(self) -> None:
        # Publishers commonly HTML-escape articleBody in JSON-LD.
        html = """
        <html><head><script type="application/ld+json">
        {"@type":"NewsArticle","headline":"H",
         "articleBody":"&lt;p&gt;First para.&lt;/p&gt;&lt;p&gt;Second &amp; last.&lt;/p&gt;"}
        </script></head><body></body></html>
        """
        article = extract_article(html)
        assert article.body is not None
        assert "<p>" not in article.body
        assert "&lt;" not in article.body
        assert "First para." in article.body
        assert "Second & last." in article.body

    def test_keywords_string_split(self) -> None:
        html = """
        <html><head><script type="application/ld+json">
        {"@type":"NewsArticle","headline":"H","articleBody":"B","keywords":"a, b, c"}
        </script></head><body></body></html>
        """
        article = extract_article(html)
        assert article.tags == ["a", "b", "c"]

    def test_empty_page(self) -> None:
        article = extract_article("<html><body></body></html>")
        assert not article.is_usable
        assert article.extraction_confidence == 0.0
