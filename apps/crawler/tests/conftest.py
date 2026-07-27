import uuid
from pathlib import Path
from typing import Any

import pytest
from newscrawl_api.seed_data import SOURCES
from newscrawl_contracts import SelectorSetConfig
from newscrawl_crawler.selectors import SelectorSet, build_selector_set

FIXTURES = Path(__file__).parent / "fixtures"


def selector_set_for(slug: str) -> SelectorSet:
    """Build the SelectorSet for a seeded source, going through the same
    SelectorSetConfig -> build_selector_set path the crawl worker uses."""
    source = next(s for s in SOURCES if s["slug"] == slug)
    return build_selector_set(SelectorSetConfig(**source["selectors"]))


@pytest.fixture
def prothom_alo_html() -> str:
    return (FIXTURES / "prothom_alo_article.html").read_text(encoding="utf-8")


@pytest.fixture
def kaler_kantho_html() -> str:
    return (FIXTURES / "kaler_kantho_article.html").read_text(encoding="utf-8")


@pytest.fixture
def naya_diganta_html() -> str:
    return (FIXTURES / "naya_diganta_article.html").read_text(encoding="utf-8")


@pytest.fixture
def bbc_news_html() -> str:
    return (FIXTURES / "bbc_news_article.html").read_text(encoding="utf-8")


@pytest.fixture
def bbc_bangla_html() -> str:
    return (FIXTURES / "bbc_bangla_article.html").read_text(encoding="utf-8")


@pytest.fixture
def aljazeera_html() -> str:
    return (FIXTURES / "aljazeera_article.html").read_text(encoding="utf-8")


@pytest.fixture
def prothom_alo_selectors() -> SelectorSet:
    return selector_set_for("prothom-alo")


@pytest.fixture
def kaler_kantho_selectors() -> SelectorSet:
    return selector_set_for("kaler-kantho")


@pytest.fixture
def naya_diganta_selectors() -> SelectorSet:
    return selector_set_for("naya-diganta")


@pytest.fixture
def bbc_news_selectors() -> SelectorSet:
    return selector_set_for("bbc-news")


@pytest.fixture
def bbc_bangla_selectors() -> SelectorSet:
    return selector_set_for("bbc-bangla")


@pytest.fixture
def aljazeera_selectors() -> SelectorSet:
    return selector_set_for("aljazeera")


@pytest.fixture
def source_config_dict() -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "name": "Prothom Alo",
        "slug": "prothom-alo",
        "base_url": "https://www.prothomalo.com",
        "language": "bn",
        "country": "BD",
        "allowed_domains": ["prothomalo.com"],
        "article_url_patterns": [r"^https://www\.prothomalo\.com/[a-z-]+(/[a-z-]+)*/[a-z0-9]{8,}$"],
        "section_urls": ["https://www.prothomalo.com/bangladesh"],
        "sitemap_urls": ["https://www.prothomalo.com/sitemap.xml"],
        "rss_urls": [],
        "selectors": next(s for s in SOURCES if s["slug"] == "prothom-alo")["selectors"],
    }
