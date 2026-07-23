"""Worker and queue visibility for the operations dashboard."""

from typing import Any

from fastapi import APIRouter
from newscrawl_contracts.streams import (
    DELAYED_JOBS_KEY,
    STREAM_CLEANING,
    STREAM_DEAD_LETTER,
    STREAM_EMBEDDING,
    STREAM_LLM,
)
from pydantic import BaseModel

from newscrawl_api.api.deps import CurrentUser, RedisDep
from newscrawl_api.coordination import Heartbeat

router = APIRouter(tags=["workers"])

STALE_AFTER_SECONDS = 60.0


class WorkerResponse(BaseModel):
    worker_id: str
    worker_type: str
    status: str
    hostname: str
    pid: int
    last_beat_age_seconds: float
    alive: bool
    meta: dict[str, Any]


class QueueDepthResponse(BaseModel):
    streams: dict[str, int]
    delayed: int
    dead_letter: int


@router.get("/workers", response_model=list[WorkerResponse])
async def list_workers(redis: RedisDep, _user: CurrentUser) -> list[WorkerResponse]:
    workers = await Heartbeat.list_workers(redis)
    return [
        WorkerResponse(
            worker_id=w.worker_id,
            worker_type=w.worker_type.value,
            status=w.status.value,
            hostname=w.hostname,
            pid=w.pid,
            last_beat_age_seconds=round(w.age_seconds, 1),
            alive=w.age_seconds < STALE_AFTER_SECONDS,
            meta=w.meta,
        )
        for w in workers
    ]


@router.get("/queues", response_model=QueueDepthResponse)
async def queue_depths(redis: RedisDep, _user: CurrentUser) -> QueueDepthResponse:
    streams: dict[str, int] = {}
    for stream in (STREAM_CLEANING, STREAM_LLM, STREAM_EMBEDDING):
        streams[stream] = int(await redis.xlen(stream))
    return QueueDepthResponse(
        streams=streams,
        delayed=int(await redis.zcard(DELAYED_JOBS_KEY)),
        dead_letter=int(await redis.xlen(STREAM_DEAD_LETTER)),
    )
