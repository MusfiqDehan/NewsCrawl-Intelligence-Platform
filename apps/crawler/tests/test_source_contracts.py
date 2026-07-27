"""Per-source extraction contract tests against saved real pages.

Contract: extraction from a saved page must keep producing a usable article
(title + substantial body in the right language + timestamp). When a site
changes its markup these tests fail first — refresh the fixture, fix the
selectors, and the rest of the pipeline stays untouched.
"""

import re

from newscrawl_crawler.extraction import extract_article
from newscrawl_crawler.selectors import SelectorSet

BENGALI_CHAR = re.compile(r"[ঀ-৿]")


class TestKalerKanthoContract:
    def test_extraction(self, kaler_kantho_html: str, kaler_kantho_selectors: SelectorSet) -> None:
        article = extract_article(kaler_kantho_html, selectors=kaler_kantho_selectors)
        assert article.is_usable
        # Full JSON-LD including articleBody
        assert article.extraction_method == "json_ld"
        assert article.extraction_confidence >= 0.9
        assert article.title and BENGALI_CHAR.search(article.title)
        assert article.body and len(article.body) > 500
        assert BENGALI_CHAR.search(article.body)
        assert article.published_at and article.published_at.startswith("20")
        assert article.canonical_url and "kalerkantho.com" in article.canonical_url

    def test_selector_fallback(
        self, kaler_kantho_html: str, kaler_kantho_selectors: SelectorSet
    ) -> None:
        stripped = re.sub(
            r'<script type="application/ld\+json">.*?</script>',
            "",
            kaler_kantho_html,
            flags=re.S,
        )
        article = extract_article(stripped, selectors=kaler_kantho_selectors)
        assert article.body and BENGALI_CHAR.search(article.body)
        assert article.extraction_method == "selectors"


class TestNayaDigantaContract:
    def test_extraction(self, naya_diganta_html: str, naya_diganta_selectors: SelectorSet) -> None:
        article = extract_article(naya_diganta_html, selectors=naya_diganta_selectors)
        assert article.is_usable
        # No JSON-LD on this site: body comes from selectors
        assert article.extraction_method == "selectors"
        assert article.title and BENGALI_CHAR.search(article.title)
        assert article.body and len(article.body) > 300
        assert BENGALI_CHAR.search(article.body)
        # Timestamp lives in the <time title=""> attribute
        assert article.published_at and article.published_at.startswith("20")
        assert article.canonical_url and "dailynayadiganta.com" in article.canonical_url


class TestBbcNewsContract:
    def test_extraction(self, bbc_news_html: str, bbc_news_selectors: SelectorSet) -> None:
        article = extract_article(bbc_news_html, selectors=bbc_news_selectors)
        assert article.is_usable
        # ReportageNewsArticle JSON-LD has metadata but no body → selectors
        assert article.extraction_method == "selectors"
        assert article.extraction_confidence >= 0.8
        assert article.title
        assert not BENGALI_CHAR.search(article.title)
        assert article.body and len(article.body) > 1000
        assert article.published_at and article.published_at.startswith("20")
        assert article.canonical_url and "bbc.com/news" in article.canonical_url

    def test_body_has_no_promo_noise(
        self, bbc_news_html: str, bbc_news_selectors: SelectorSet
    ) -> None:
        article = extract_article(bbc_news_html, selectors=bbc_news_selectors)
        assert article.body is not None
        assert "Follow BBC" not in article.body[:500]


class TestBbcBanglaContract:
    def test_extraction(self, bbc_bangla_html: str, bbc_bangla_selectors: SelectorSet) -> None:
        article = extract_article(bbc_bangla_html, selectors=bbc_bangla_selectors)
        assert article.is_usable
        assert article.title and BENGALI_CHAR.search(article.title)
        assert article.body and len(article.body) > 1000
        assert BENGALI_CHAR.search(article.body)
        assert article.published_at and article.published_at.startswith("20")
        assert article.canonical_url and "bbc.com/bengali" in article.canonical_url


class TestAlJazeeraContract:
    def test_extraction(self, aljazeera_html: str, aljazeera_selectors: SelectorSet) -> None:
        article = extract_article(aljazeera_html, selectors=aljazeera_selectors)
        assert article.is_usable
        # NewsArticle JSON-LD without body → metadata + selector body
        assert article.extraction_method == "selectors"
        assert article.extraction_confidence >= 0.8
        assert article.title
        assert article.body and len(article.body) > 1000
        assert article.author  # JSON-LD ships author
        assert article.published_at and article.published_at.startswith("20")
        assert article.canonical_url and "aljazeera.com" in article.canonical_url


class TestSeedSourceSelectors:
    def test_all_seed_sources_have_selectors(self) -> None:
        from newscrawl_api.seed_data import SOURCES

        for source in SOURCES:
            assert source.get("selectors"), f"no selectors configured for {source['slug']}"
