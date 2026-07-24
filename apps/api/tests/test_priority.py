from datetime import UTC, datetime, timedelta

from newscrawl_api.services.priority import PriorityConfig, compute_priority
from newscrawl_contracts.enums import UrlType

NOW = datetime(2026, 7, 23, 12, 0, tzinfo=UTC)


def test_discovery_hubs_beat_articles() -> None:
    def score(url_type: UrlType) -> float:
        return compute_priority(source_weight=1.0, url_type=url_type, now=NOW)

    assert (
        score(UrlType.HOMEPAGE)
        > score(UrlType.RSS)
        > score(UrlType.SITEMAP)
        > score(UrlType.SECTION)
        > score(UrlType.ARTICLE)
        > score(UrlType.OTHER)
    )


def test_fresh_article_beats_old_article() -> None:
    fresh = compute_priority(
        source_weight=1.0,
        url_type=UrlType.ARTICLE,
        published_at=NOW - timedelta(hours=1),
        now=NOW,
    )
    old = compute_priority(
        source_weight=1.0,
        url_type=UrlType.ARTICLE,
        published_at=NOW - timedelta(days=30),
        now=NOW,
    )
    assert fresh > old


def test_depth_penalty_capped() -> None:
    shallow = compute_priority(source_weight=1.0, url_type=UrlType.ARTICLE, depth=0, now=NOW)
    deep = compute_priority(source_weight=1.0, url_type=UrlType.ARTICLE, depth=6, now=NOW)
    deeper = compute_priority(source_weight=1.0, url_type=UrlType.ARTICLE, depth=60, now=NOW)
    assert shallow > deep
    assert deep == deeper  # capped


def test_breaking_news_dominates() -> None:
    breaking = compute_priority(
        source_weight=0.5, url_type=UrlType.ARTICLE, is_breaking=True, now=NOW
    )
    homepage = compute_priority(source_weight=1.5, url_type=UrlType.HOMEPAGE, now=NOW)
    assert breaking > homepage


def test_change_rate_boost() -> None:
    volatile = compute_priority(
        source_weight=1.0, url_type=UrlType.ARTICLE, change_rate=1.0, now=NOW
    )
    static = compute_priority(source_weight=1.0, url_type=UrlType.ARTICLE, change_rate=0.0, now=NOW)
    assert volatile > static


def test_configurable_weights() -> None:
    config = PriorityConfig(type_weights={UrlType.SECTION: 100.0})
    section = compute_priority(source_weight=1.0, url_type=UrlType.SECTION, config=config, now=NOW)
    homepage = compute_priority(
        source_weight=1.0, url_type=UrlType.HOMEPAGE, config=config, now=NOW
    )
    assert section > homepage
