"""Playwright fallback policy — when plain HTTP is not enough.

Two routes into the browser:
  1. ``source.requires_browser`` — every page fetch for the source goes
     through Playwright (e.g. Kaler Kantho behind a Cloudflare JS challenge).
  2. Runtime detection — an article fetched over plain HTTP whose extraction
     is unusable (client-side rendered body) is retried once via the browser.

Cost control:
  - one named browser context per source → cookie/challenge-clearance reuse
  - images, media, fonts and known ad/analytics hosts are aborted before the
    network request is issued
  - navigation stops at ``domcontentloaded`` — article text does not need
    the full load event
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from playwright.async_api import Request as PlaywrightRequest

# Resource types that never contribute to article text.
BLOCKED_RESOURCE_TYPES: frozenset[str] = frozenset({"image", "media", "font"})

# Ad/analytics/tracker hosts — aborted regardless of resource type.
BLOCKED_URL_SUBSTRINGS: tuple[str, ...] = (
    "doubleclick.net",
    "googlesyndication.com",
    "googleadservices.com",
    "google-analytics.com",
    "googletagmanager.com",
    "googletagservices.com",
    "adsafeprotected.com",
    "amazon-adsystem.com",
    "facebook.net",
    "facebook.com/tr",
    "adnxs.com",
    "taboola.com",
    "outbrain.com",
    "criteo.com",
    "criteo.net",
    "scorecardresearch.com",
    "chartbeat.com",
    "hotjar.com",
    "quantserve.com",
    "pubmatic.com",
    "rubiconproject.com",
    "moatads.com",
    "onesignal.com",
)


def should_abort_request(request: PlaywrightRequest) -> bool:
    """PLAYWRIGHT_ABORT_REQUEST predicate: True → abort before hitting the network."""
    if request.resource_type in BLOCKED_RESOURCE_TYPES:
        return True
    url = request.url
    return any(fragment in url for fragment in BLOCKED_URL_SUBSTRINGS)


def browser_request_meta(source_slug: str) -> dict[str, Any]:
    """Request.meta fragment that routes a request through scrapy-playwright.

    The context is named after the source so all of a source's browser
    fetches share cookies — a solved anti-bot challenge stays solved for
    the rest of the pass.
    """
    return {
        "playwright": True,
        "playwright_context": source_slug,
        "playwright_page_goto_kwargs": {"wait_until": "domcontentloaded"},
    }
