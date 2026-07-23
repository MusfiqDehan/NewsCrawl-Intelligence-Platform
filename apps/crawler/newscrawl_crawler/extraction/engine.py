"""Layered article extraction: JSON-LD → OpenGraph → per-source CSS selectors.

Most modern news sites (including all five initial sources) publish schema.org
NewsArticle JSON-LD; it is the most stable extraction surface because it is
what publishers maintain for Google News. CSS selectors are the fallback and
the completion layer (e.g. when articleBody is missing from JSON-LD).
"""

import html as html_module
import json
import re
from dataclasses import dataclass, field
from typing import Any

from parsel import Selector

from newscrawl_crawler.selectors.base import SelectorSet

_ARTICLE_TYPES = {"NewsArticle", "Article", "ReportageNewsArticle", "BackgroundNewsArticle"}


@dataclass
class ExtractedArticle:
    title: str | None = None
    subtitle: str | None = None
    author: str | None = None
    category: str | None = None
    published_at: str | None = None
    updated_at: str | None = None
    body: str | None = None
    summary: str | None = None
    image_urls: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    canonical_url: str | None = None
    extraction_method: str = "selectors"
    extraction_confidence: float = 0.0

    @property
    def is_usable(self) -> bool:
        return bool(self.title and self.body)

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "subtitle": self.subtitle,
            "author": self.author,
            "category": self.category,
            "published_at": self.published_at,
            "updated_at": self.updated_at,
            "body": self.body,
            "summary": self.summary,
            "image_urls": self.image_urls,
            "tags": self.tags,
            "canonical_url": self.canonical_url,
            "extraction_method": self.extraction_method,
            "extraction_confidence": self.extraction_confidence,
        }


def _iter_jsonld_objects(selector: Selector) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = []
    for script in selector.xpath('//script[@type="application/ld+json"]/text()').getall():
        try:
            data = json.loads(script)
        except json.JSONDecodeError, ValueError:
            continue
        candidates = data if isinstance(data, list) else [data]
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            graph = candidate.get("@graph")
            if isinstance(graph, list):
                objects.extend(g for g in graph if isinstance(g, dict))
            objects.append(candidate)
    return objects


def _author_names(raw: Any) -> str | None:
    if raw is None:
        return None
    if isinstance(raw, str):
        return raw.strip() or None
    if isinstance(raw, dict):
        name = raw.get("name")
        return name.strip() if isinstance(name, str) and name.strip() else None
    if isinstance(raw, list):
        names = [n for n in (_author_names(a) for a in raw) if n]
        return ", ".join(names) if names else None
    return None


def _string_list(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        return [part.strip() for part in raw.split(",") if part.strip()]
    if isinstance(raw, dict):
        url = raw.get("url")
        return [url] if isinstance(url, str) else []
    if isinstance(raw, list):
        result: list[str] = []
        for entry in raw:
            result.extend(_string_list(entry))
        return result
    return []


_TAG_RE = re.compile(r"<[^>]+>")


def _plain_text(raw: str) -> str:
    """Convert an HTML-escaped or tag-bearing JSON-LD body to plain text.

    Publishers frequently put escaped HTML in articleBody (``&lt;p&gt;...``);
    unescape entities first, then strip any resulting tags.
    """
    text = html_module.unescape(raw)
    text = _TAG_RE.sub(" ", text)
    return re.sub(r"[ \t]+", " ", text).strip()


def _extract_jsonld(selector: Selector, article: ExtractedArticle) -> bool:
    for obj in _iter_jsonld_objects(selector):
        obj_type = obj.get("@type")
        types = set(obj_type) if isinstance(obj_type, list) else {obj_type}
        if not (types & _ARTICLE_TYPES):
            continue

        article.title = article.title or obj.get("headline") or obj.get("name")
        article.subtitle = article.subtitle or obj.get("alternativeHeadline")
        article.summary = article.summary or obj.get("description")
        article.author = article.author or _author_names(obj.get("author"))
        article.published_at = article.published_at or obj.get("datePublished")
        article.updated_at = article.updated_at or obj.get("dateModified")
        body = obj.get("articleBody")
        if isinstance(body, str) and body.strip():
            article.body = article.body or _plain_text(body)
        section = obj.get("articleSection")
        if isinstance(section, list):
            section = section[0] if section else None
        article.category = article.category or section
        article.tags = article.tags or _string_list(obj.get("keywords"))
        article.image_urls = article.image_urls or _string_list(obj.get("image"))
        main_entity = obj.get("mainEntityOfPage")
        if isinstance(main_entity, dict):
            main_entity = main_entity.get("@id")
        article.canonical_url = article.canonical_url or obj.get("url") or main_entity
        return True
    return False


def _extract_opengraph(selector: Selector, article: ExtractedArticle) -> None:
    def meta(prop: str) -> str | None:
        value = selector.xpath(f'//meta[@property="{prop}"]/@content').get()
        return value.strip() if value and value.strip() else None

    article.title = article.title or meta("og:title")
    article.summary = article.summary or meta("og:description")
    article.published_at = article.published_at or meta("article:published_time")
    article.updated_at = article.updated_at or meta("article:modified_time")
    article.category = article.category or meta("article:section")
    article.canonical_url = (
        article.canonical_url
        or meta("og:url")
        or selector.xpath('//link[@rel="canonical"]/@href').get()
    )
    if not article.image_urls:
        image = meta("og:image")
        if image:
            article.image_urls = [image]


def _extract_with_selectors(
    selector: Selector, selectors: SelectorSet, article: ExtractedArticle
) -> None:
    def first(css_list: tuple[str, ...]) -> str | None:
        for css in css_list:
            value = selector.css(css).get()
            if value and value.strip():
                return value.strip()
        return None

    article.title = article.title or first(selectors.title)
    article.subtitle = article.subtitle or first(selectors.subtitle)
    article.author = article.author or first(selectors.author)
    article.published_at = article.published_at or first(selectors.published_at)
    article.category = article.category or first(selectors.category)

    if not article.body:
        for css in selectors.body:
            paragraphs = [
                " ".join(fragment.strip() for fragment in p.css("::text").getall()).strip()
                for p in selector.css(css)
            ]
            paragraphs = [p for p in paragraphs if p]
            if paragraphs:
                article.body = "\n\n".join(paragraphs)
                break

    if not article.image_urls and selectors.images:
        for css in selectors.images:
            urls = [u for u in selector.css(css).getall() if u]
            if urls:
                article.image_urls = urls[:10]
                break

    if not article.tags and selectors.tags:
        for css in selectors.tags:
            tags = [t.strip() for t in selector.css(css).getall() if t.strip()]
            if tags:
                article.tags = tags
                break


def extract_article(html: str | bytes, *, selectors: SelectorSet | None = None) -> ExtractedArticle:
    if isinstance(html, bytes):
        html = html.decode("utf-8", errors="replace")
    selector = Selector(text=html)
    article = ExtractedArticle()

    found_jsonld = _extract_jsonld(selector, article)
    jsonld_had_body = found_jsonld and bool(article.body)

    _extract_opengraph(selector, article)
    if selectors is not None:
        _extract_with_selectors(selector, selectors, article)

    if jsonld_had_body:
        article.extraction_method = "json_ld"
        article.extraction_confidence = 0.95
    elif found_jsonld and article.body:
        # metadata from JSON-LD, body recovered via selectors
        article.extraction_method = "selectors"
        article.extraction_confidence = 0.85
    elif article.body:
        article.extraction_method = "selectors"
        article.extraction_confidence = 0.75
    else:
        article.extraction_method = "opengraph"
        article.extraction_confidence = 0.3 if article.title else 0.0
    return article
