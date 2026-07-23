"""Worker heartbeats: liveness registry in a Redis hash.

Each worker periodically writes a JSON blob keyed by worker id; anything
whose heartbeat is older than the staleness threshold is considered dead.
The API reads this hash for the operations dashboard.
"""

import asyncio
import json
import os
import socket
import time
from dataclasses import dataclass
from typing import Any, cast

from newscrawl_contracts.enums import WorkerStatus, WorkerType
from newscrawl_contracts.streams import HEARTBEAT_KEY
from redis.asyncio import Redis

from newscrawl_api.observability import get_logger

log = get_logger("heartbeat")


@dataclass(frozen=True)
class WorkerInfo:
    worker_id: str
    worker_type: WorkerType
    status: WorkerStatus
    hostname: str
    pid: int
    last_beat_at: float
    meta: dict[str, Any]

    @property
    def age_seconds(self) -> float:
        return time.time() - self.last_beat_at


class Heartbeat:
    def __init__(
        self,
        redis: Redis,
        *,
        worker_type: WorkerType,
        worker_id: str | None = None,
        interval_seconds: float = 15.0,
    ) -> None:
        self.redis = redis
        self.worker_type = worker_type
        self.hostname = socket.gethostname()
        self.pid = os.getpid()
        self.worker_id = worker_id or f"{worker_type.value}-{self.hostname}-{self.pid}"
        self.interval_seconds = interval_seconds
        self.status = WorkerStatus.STARTING
        self.meta: dict[str, Any] = {}
        self._task: asyncio.Task[None] | None = None

    async def beat(self) -> None:
        await self.redis.hset(
            HEARTBEAT_KEY,
            self.worker_id,
            json.dumps(
                {
                    "worker_type": self.worker_type.value,
                    "status": self.status.value,
                    "hostname": self.hostname,
                    "pid": self.pid,
                    "last_beat_at": time.time(),
                    "meta": self.meta,
                }
            ),
        )

    async def start(self) -> None:
        """Set status running and start beating in the background."""
        self.status = WorkerStatus.RUNNING
        await self.beat()

        async def loop() -> None:
            while True:
                await asyncio.sleep(self.interval_seconds)
                try:
                    await self.beat()
                except Exception as exc:
                    log.warning("heartbeat_failed", worker_id=self.worker_id, error=repr(exc))

        self._task = asyncio.get_running_loop().create_task(loop())

    async def stop(self, *, deregister: bool = True) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None
        self.status = WorkerStatus.STOPPED
        if deregister:
            await self.redis.hdel(HEARTBEAT_KEY, self.worker_id)
        else:
            await self.beat()

    # ── Registry queries (used by the API) ───────────────────────────────────

    @staticmethod
    async def list_workers(redis: Redis, *, stale_after_seconds: float = 60.0) -> list[WorkerInfo]:
        # decode_responses=True → str keys/values (stubs say bytes|str)
        raw = cast("dict[str, str]", await redis.hgetall(HEARTBEAT_KEY))
        workers: list[WorkerInfo] = []
        for worker_id, blob in raw.items():
            data = json.loads(blob)
            info = WorkerInfo(
                worker_id=worker_id,
                worker_type=WorkerType(data["worker_type"]),
                status=WorkerStatus(data["status"]),
                hostname=data["hostname"],
                pid=data["pid"],
                last_beat_at=data["last_beat_at"],
                meta=data.get("meta", {}),
            )
            workers.append(info)
        return sorted(workers, key=lambda w: w.worker_id)

    @staticmethod
    async def reap_stale(redis: Redis, *, stale_after_seconds: float = 120.0) -> int:
        """Remove workers that stopped beating (crashed without cleanup)."""
        workers = await Heartbeat.list_workers(redis)
        removed = 0
        for worker in workers:
            if worker.age_seconds > stale_after_seconds:
                await redis.hdel(HEARTBEAT_KEY, worker.worker_id)
                removed += 1
        return removed
