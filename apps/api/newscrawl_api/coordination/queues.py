"""Redis Streams queue abstraction with consumer groups.

Semantics:
- publish: XADD a JSON payload to a stream.
- consume: XREADGROUP with a consumer group; messages must be acked.
- retry: failed messages are re-enqueued through a sorted-set delay queue
  (score = due timestamp) and moved back onto their stream by pump_delayed.
- dead-letter: after max_attempts the message lands on the dead-letter
  stream with failure metadata, for inspection and manual replay.
- claim_stale: XAUTOCLAIM recovers messages whose consumer died mid-flight.
"""

import json
import time
import uuid
from dataclasses import dataclass
from typing import Any, cast

from newscrawl_contracts.streams import DELAYED_JOBS_KEY, STREAM_DEAD_LETTER
from redis.asyncio import Redis
from redis.exceptions import ResponseError

PAYLOAD_FIELD = "payload"
ATTEMPT_FIELD = "attempt"

# redis-py's type stubs return bytes|str unions; clients here always use
# decode_responses=True, so responses are str-keyed.
StreamEntries = list[tuple[str, dict[str, str]]]


@dataclass(frozen=True)
class QueueMessage:
    """One in-flight stream entry. Ack (or retry/dead-letter) when done."""

    stream: str
    message_id: str
    payload: dict[str, Any]
    attempt: int


class StreamQueue:
    def __init__(
        self,
        redis: Redis,
        *,
        group: str,
        consumer: str,
        max_attempts: int = 3,
        retry_delay_seconds: float = 30.0,
        stale_claim_ms: int = 300_000,
    ) -> None:
        self.redis = redis
        self.group = group
        self.consumer = consumer
        self.max_attempts = max_attempts
        self.retry_delay_seconds = retry_delay_seconds
        self.stale_claim_ms = stale_claim_ms

    # ── Setup ────────────────────────────────────────────────────────────────

    async def ensure_group(self, stream: str) -> None:
        """Create the consumer group (and stream) if missing; idempotent."""
        try:
            await self.redis.xgroup_create(stream, self.group, id="0", mkstream=True)
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    # ── Producing ────────────────────────────────────────────────────────────

    async def publish(self, stream: str, payload: dict[str, Any], *, attempt: int = 1) -> str:
        entry_id = await self.redis.xadd(
            stream, {PAYLOAD_FIELD: json.dumps(payload), ATTEMPT_FIELD: str(attempt)}
        )
        return cast(str, entry_id)

    # ── Consuming ────────────────────────────────────────────────────────────

    async def consume(
        self, stream: str, *, count: int = 10, block_ms: int = 5000
    ) -> list[QueueMessage]:
        response = cast(
            "list[tuple[str, StreamEntries]] | None",
            await self.redis.xreadgroup(
                self.group, self.consumer, {stream: ">"}, count=count, block=block_ms
            ),
        )
        messages: list[QueueMessage] = []
        for _stream_name, entries in response or []:
            for message_id, fields in entries:
                messages.append(self._to_message(stream, message_id, fields))
        return messages

    async def ack(self, message: QueueMessage) -> None:
        await self.redis.xack(message.stream, self.group, message.message_id)

    async def retry(self, message: QueueMessage, *, error: str) -> bool:
        """Schedule a delayed retry; dead-letter when attempts are exhausted.

        Returns True when a retry was scheduled, False when dead-lettered.
        The original entry is always acked — the retry is a new entry.
        """
        await self.ack(message)
        if message.attempt >= self.max_attempts:
            await self._dead_letter(message, error=error)
            return False
        due_at = time.time() + self.retry_delay_seconds * message.attempt
        envelope = json.dumps(
            {
                "id": uuid.uuid4().hex,  # uniqueness: same payload may retry twice
                "stream": message.stream,
                "payload": message.payload,
                "attempt": message.attempt + 1,
            }
        )
        await self.redis.zadd(DELAYED_JOBS_KEY, {envelope: due_at})
        return True

    async def _dead_letter(self, message: QueueMessage, *, error: str) -> None:
        await self.redis.xadd(
            STREAM_DEAD_LETTER,
            {
                PAYLOAD_FIELD: json.dumps(message.payload),
                "origin_stream": message.stream,
                "attempts": str(message.attempt),
                "error": error[:2000],
                "failed_at": str(time.time()),
            },
        )

    # ── Recovery ─────────────────────────────────────────────────────────────

    async def pump_delayed(self, *, limit: int = 100) -> int:
        """Move due delayed jobs back onto their streams. Run periodically."""
        now = time.time()
        due = cast(
            "list[str]",
            await self.redis.zrangebyscore(DELAYED_JOBS_KEY, "-inf", now, start=0, num=limit),
        )
        moved = 0
        for envelope in due:
            # Only the remover re-enqueues — safe with concurrent pumpers.
            removed = await self.redis.zrem(DELAYED_JOBS_KEY, envelope)
            if not removed:
                continue
            job = json.loads(envelope)
            await self.publish(job["stream"], job["payload"], attempt=job["attempt"])
            moved += 1
        return moved

    async def claim_stale(self, stream: str, *, count: int = 10) -> list[QueueMessage]:
        """Claim messages stuck pending with a dead consumer (XAUTOCLAIM)."""
        response = await self.redis.xautoclaim(
            stream,
            self.group,
            self.consumer,
            min_idle_time=self.stale_claim_ms,
            count=count,
        )
        entries = cast("StreamEntries", response[1])
        return [
            self._to_message(stream, message_id, fields)
            for message_id, fields in entries
            if fields  # tombstones have no fields
        ]

    async def pending_count(self, stream: str) -> int:
        info = await self.redis.xpending(stream, self.group)
        return int(info.get("pending", 0)) if isinstance(info, dict) else 0

    # ── Dead-letter operations ───────────────────────────────────────────────

    async def replay_dead_letters(self, *, count: int = 100) -> int:
        """Move dead-lettered messages back onto their origin streams."""
        entries = cast("StreamEntries", await self.redis.xrange(STREAM_DEAD_LETTER, count=count))
        replayed = 0
        for message_id, fields in entries:
            origin = fields.get("origin_stream")
            payload = fields.get(PAYLOAD_FIELD)
            if origin and payload:
                await self.publish(origin, json.loads(payload), attempt=1)
                replayed += 1
            await self.redis.xdel(STREAM_DEAD_LETTER, message_id)
        return replayed

    # ── Internal ─────────────────────────────────────────────────────────────

    @staticmethod
    def _to_message(stream: str, message_id: str, fields: dict[str, str]) -> QueueMessage:
        return QueueMessage(
            stream=stream,
            message_id=message_id,
            payload=json.loads(fields[PAYLOAD_FIELD]),
            attempt=int(fields.get(ATTEMPT_FIELD, "1")),
        )
