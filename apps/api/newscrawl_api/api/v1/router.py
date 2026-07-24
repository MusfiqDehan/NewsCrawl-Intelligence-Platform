from fastapi import APIRouter

from newscrawl_api.api.v1 import articles, auth, crawl_jobs, ops, public, sources, stats, workers

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(ops.router)
api_router.include_router(auth.router)
api_router.include_router(sources.router)
api_router.include_router(crawl_jobs.router)
api_router.include_router(workers.router)
api_router.include_router(articles.router)
api_router.include_router(public.router)
api_router.include_router(stats.router)
