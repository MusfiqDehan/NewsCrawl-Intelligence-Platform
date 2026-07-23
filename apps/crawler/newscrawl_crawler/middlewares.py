"""Scrapy downloader middlewares.

DistributedPolitenessMiddleware enforces the *cluster-wide* per-domain
budget through the shared Redis token bucket. Scrapy's own DOWNLOAD_DELAY
only throttles one process; this middleware makes N workers behave like one
polite client.
"""

import asyncio
from urllib.parse import urlsplit

from newscrawl_api.config import get_settings
from newscrawl_api.coordination import DomainRateLimiter
from scrapy import Request, Spider
from scrapy.crawler import Crawler

MAX_POLITENESS_WAIT_SECONDS = 30.0


class DistributedPolitenessMiddleware:
    def __init__(self, requests_per_second: float, burst: int) -> None:
        self.requests_per_second = requests_per_second
        self.burst = burst
        self._limiter: DomainRateLimiter | None = None

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> DistributedPolitenessMiddleware:
        rps = float(crawler.settings.get("POLITENESS_REQUESTS_PER_SECOND", 0.5))
        burst = int(crawler.settings.get("POLITENESS_BURST", 2))
        return cls(rps, burst)

    def _get_limiter(self) -> DomainRateLimiter:
        if self._limiter is None:
            from redis.asyncio import Redis

            redis = Redis.from_url(get_settings().redis_url, decode_responses=True)
            self._limiter = DomainRateLimiter(redis)
        return self._limiter

    async def process_request(self, request: Request, spider: Spider) -> None:
        # Per-spider rate config wins over the middleware default.
        rps = float(request.meta.get("politeness_rps", self.requests_per_second))
        domain = urlsplit(request.url).hostname or ""
        if not domain:
            return
        limiter = self._get_limiter()
        waited = 0.0
        while True:
            allowed, wait = await limiter.acquire(domain, requests_per_second=rps, burst=self.burst)
            if allowed:
                return
            if waited >= MAX_POLITENESS_WAIT_SECONDS:
                # Give up throttling rather than deadlocking the downloader;
                # the site still gets protected by Scrapy's own delay.
                return
            sleep_for = min(wait, MAX_POLITENESS_WAIT_SECONDS - waited) or 0.1
            await asyncio.sleep(sleep_for)
            waited += sleep_for
