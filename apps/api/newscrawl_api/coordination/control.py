"""Control signals: API → workers pub/sub (pause / resume / cancel).

Workers subscribe to the control channel and react without polling the
database. Signals are advisory — the database job status remains the
source of truth; the pub/sub channel only makes reaction immediate.
"""

import asyncio
import contextlib
import json
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum

from newscrawl_contracts.streams import CONTROL_CHANNEL
from redis.asyncio import Redis

from newscrawl_api.observability import get_logger

log = get_logger("control")


class ControlAction(StrEnum):
    PAUSE = "pause"
    RESUME = "resume"
    CANCEL = "cancel"
    SHUTDOWN = "shutdown"  # drain and exit (targeted at a worker or all)


@dataclass(frozen=True)
class ControlSignal:
    action: ControlAction
    job_id: uuid.UUID | None = None
    source_id: uuid.UUID | None = None
    worker_id: str | None = None

    def to_json(self) -> str:
        return json.dumps(
            {
                "action": self.action.value,
                "job_id": str(self.job_id) if self.job_id else None,
                "source_id": str(self.source_id) if self.source_id else None,
                "worker_id": self.worker_id,
            }
        )

    @classmethod
    def from_json(cls, raw: str) -> ControlSignal:
        data = json.loads(raw)
        return cls(
            action=ControlAction(data["action"]),
            job_id=uuid.UUID(data["job_id"]) if data.get("job_id") else None,
            source_id=uuid.UUID(data["source_id"]) if data.get("source_id") else None,
            worker_id=data.get("worker_id"),
        )


async def publish_signal(redis: Redis, signal: ControlSignal) -> None:
    await redis.publish(CONTROL_CHANNEL, signal.to_json())


Handler = Callable[[ControlSignal], Awaitable[None]]


class ControlListener:
    """Background pub/sub subscriber dispatching signals to a handler."""

    def __init__(self, redis: Redis, handler: Handler) -> None:
        self.redis = redis
        self.handler = handler
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        pubsub = self.redis.pubsub()
        await pubsub.subscribe(CONTROL_CHANNEL)

        async def listen() -> None:
            try:
                async for message in pubsub.listen():
                    if message["type"] != "message":
                        continue
                    try:
                        signal = ControlSignal.from_json(message["data"])
                    except (ValueError, KeyError) as exc:
                        log.warning("malformed_control_signal", error=repr(exc))
                        continue
                    try:
                        await self.handler(signal)
                    except Exception as exc:
                        log.error("control_handler_failed", error=repr(exc))
            finally:
                await pubsub.aclose()  # type: ignore[no-untyped-call]

        self._task = asyncio.get_running_loop().create_task(listen())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
