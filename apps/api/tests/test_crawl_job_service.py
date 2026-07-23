"""Crawl job state machine and entry-URL derivation (pure unit tests)."""

from itertools import pairwise

import pytest
from newscrawl_api.models import Source
from newscrawl_api.services.crawl_jobs import (
    TERMINAL_STATUSES,
    VALID_TRANSITIONS,
    JobParamsError,
    entry_urls_for_job,
)
from newscrawl_contracts.enums import CrawlJobStatus, CrawlJobType, UrlType


def make_source() -> Source:
    return Source(
        name="T",
        slug="t",
        base_url="https://t.example.com",
        language="en",
        country="US",
        allowed_domains=["t.example.com"],
        sitemap_urls=["https://t.example.com/sitemap.xml"],
        rss_urls=["https://t.example.com/feed"],
        section_urls=["https://t.example.com/politics"],
    )


class TestStateMachine:
    def test_every_status_has_transition_rules(self) -> None:
        assert set(VALID_TRANSITIONS) == set(CrawlJobStatus)

    def test_terminal_statuses_have_no_exits(self) -> None:
        for status in TERMINAL_STATUSES:
            assert VALID_TRANSITIONS[status] == frozenset()

    def test_happy_path_is_reachable(self) -> None:
        path = [
            CrawlJobStatus.CREATED,
            CrawlJobStatus.QUEUED,
            CrawlJobStatus.RUNNING,
            CrawlJobStatus.COMPLETED,
        ]
        for current, target in pairwise(path):
            assert target in VALID_TRANSITIONS[current]

    def test_pause_resume_cycle(self) -> None:
        assert CrawlJobStatus.PAUSED in VALID_TRANSITIONS[CrawlJobStatus.RUNNING]
        assert CrawlJobStatus.RUNNING in VALID_TRANSITIONS[CrawlJobStatus.PAUSED]

    def test_cancel_allowed_from_all_non_terminal(self) -> None:
        for status in set(CrawlJobStatus) - TERMINAL_STATUSES:
            assert CrawlJobStatus.CANCELLED in VALID_TRANSITIONS[status]

    def test_completed_cannot_restart(self) -> None:
        assert CrawlJobStatus.RUNNING not in VALID_TRANSITIONS[CrawlJobStatus.COMPLETED]


class TestEntryUrls:
    def test_full_crawl_uses_all_discovery_surfaces(self) -> None:
        urls = entry_urls_for_job(make_source(), CrawlJobType.FULL_CRAWL, {})
        types = {u.url_type for u in urls}
        assert types == {UrlType.HOMEPAGE, UrlType.SITEMAP, UrlType.RSS, UrlType.SECTION}

    def test_incremental_skips_sitemaps(self) -> None:
        urls = entry_urls_for_job(make_source(), CrawlJobType.INCREMENTAL_CRAWL, {})
        assert UrlType.SITEMAP not in {u.url_type for u in urls}

    def test_url_crawl_requires_urls(self) -> None:
        with pytest.raises(JobParamsError):
            entry_urls_for_job(make_source(), CrawlJobType.URL_CRAWL, {})

    def test_url_crawl_marks_articles(self) -> None:
        urls = entry_urls_for_job(
            make_source(),
            CrawlJobType.URL_CRAWL,
            {"urls": ["https://t.example.com/politics/abc12345"]},
        )
        assert [u.url_type for u in urls] == [UrlType.ARTICLE]

    def test_section_crawl_params_override_source(self) -> None:
        urls = entry_urls_for_job(
            make_source(),
            CrawlJobType.SECTION_CRAWL,
            {"section_urls": ["https://t.example.com/sports"]},
        )
        assert [u.url for u in urls] == ["https://t.example.com/sports"]

    def test_retry_failed_has_no_entry_urls(self) -> None:
        assert entry_urls_for_job(make_source(), CrawlJobType.RETRY_FAILED, {}) == []

    def test_section_crawl_without_sections_rejected(self) -> None:
        source = make_source()
        source.section_urls = []
        with pytest.raises(JobParamsError):
            entry_urls_for_job(source, CrawlJobType.SECTION_CRAWL, {})
