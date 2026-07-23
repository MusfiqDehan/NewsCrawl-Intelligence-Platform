"""FastAPI application factory.

The API is the control + query plane only: it creates and controls crawl jobs
and serves processed content. It never executes crawls itself.
"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis

from newscrawl_api.api.v1.router import api_router
from newscrawl_api.config import get_settings
from newscrawl_api.db import dispose_engine, get_engine
from newscrawl_api.observability import (
    MetricsMiddleware,
    configure_logging,
    get_logger,
    platform_gauges_loop,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging("api", settings.log_level)
    log = get_logger()

    app.state.redis = Redis.from_url(settings.redis_url, decode_responses=True)
    get_engine()  # fail fast on malformed database configuration
    gauges_task = asyncio.create_task(platform_gauges_loop(app.state.redis))
    log.info("api_started", env=settings.newscrawl_env)
    try:
        yield
    finally:
        gauges_task.cancel()
        with suppress(asyncio.CancelledError):
            await gauges_task
        await app.state.redis.aclose()
        await dispose_engine()
        log.info("api_stopped")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="NewsCrawl Intelligence Platform API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    app.add_middleware(MetricsMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )
    app.include_router(api_router)
    return app


app = create_app()
