import uuid
from pathlib import Path
from typing import Any

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


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
    }
