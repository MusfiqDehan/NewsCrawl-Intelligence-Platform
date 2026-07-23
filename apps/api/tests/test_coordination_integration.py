"""Redis coordination integration tests — require the local stack (make dev).

Every test uses uniquely named streams/keys so runs never interfere with the
real queues or each other.
"""

import asyncio
import json
import time
import uuid
from collections.abc import AsyncIterator

import pytest
from newscrawl_api.config import get_settings
from newscrawl_api.coordination import (
    ControlAction,
    ControlListener,
    ControlSignal,
    DomainRateLimiter,
    GracefulShutdown,
    Heartbeat,
    StreamQueue,
)
from newscrawl_api.coordination.control import publish_signal
from newscrawl_contracts.enums import WorkerType
from newscrawl_contracts.streams import DELAYED_JOBS_KEY, HEARTBEAT_KEY, STREAM_DEAD_LETTER
from redis.asyncio import Redis

pytestmark = pytest.mark.integration


@pytest.fixture
async def redis() -> AsyncIterator[Redis]:
    client = Redis.from_url(get_settings().redis_url, decode_responses=True)
    yield client
    await client.aclose()


@pytest.fixture
def stream() -> str:
    return f"test:stream:{uuid.uuid4().hex[:8]}"


@pytest.fixture
async def queue(redis: Redis, stream: str) -> AsyncIterator[StreamQueue]:
    q = StreamQueue(
        redis,
        group="test-group",
        consumer="test-consumer",
        max_attempts=2,
        retry_delay_seconds=0.05,
    )
    await q.ensure_group(stream)
    yield q
    await redis.delete(stream)


class TestStreamQueue:
    async def test_publish_consume_ack(self, queue: StreamQueue, stream: str) -> None:
        await queue.publish(stream, {"n": 1})
        await queue.publish(stream, {"n": 2})

        messages = await queue.consume(stream, count=10, block_ms=100)
        assert [m.payload["n"] for m in messages] == [1, 2]
        assert all(m.attempt == 1 for m in messages)

        for message in messages:
            await queue.ack(message)
        assert await queue.pending_count(stream) == 0

    async def test_unacked_messages_stay_pending(self, queue: StreamQueue, stream: str) -> None:
        await queue.publish(stream, {"n": 1})
        await queue.consume(stream, count=1, block_ms=100)
        assert await queue.pending_count(stream) == 1

    async def test_retry_schedules_delayed_and_pump_requeues(
        self, queue: StreamQueue, stream: str, redis: Redis
    ) -> None:
        await queue.publish(stream, {"n": 42})
        [message] = await queue.consume(stream, count=1, block_ms=100)

        scheduled = await queue.retry(message, error="transient failure")
        assert scheduled is True
        assert await queue.pending_count(stream) == 0  # original was acked

        await asyncio.sleep(0.1)  # let the delay elapse
        moved = await queue.pump_delayed()
        assert moved == 1

        [retried] = await queue.consume(stream, count=1, block_ms=100)
        assert retried.payload == {"n": 42}
        assert retried.attempt == 2
        await queue.ack(retried)

    async def test_exhausted_retries_dead_letter(
        self, queue: StreamQueue, stream: str, redis: Redis
    ) -> None:
        before = await redis.xlen(STREAM_DEAD_LETTER)
        await queue.publish(stream, {"n": 7}, attempt=2)  # already at max_attempts
        [message] = await queue.consume(stream, count=1, block_ms=100)

        scheduled = await queue.retry(message, error="permanent failure")
        assert scheduled is False

        from typing import cast

        entries = cast("list[tuple[str, dict[str, str]]]", await redis.xrange(STREAM_DEAD_LETTER))
        assert await redis.xlen(STREAM_DEAD_LETTER) == before + 1
        last_id, last = entries[-1]
        assert json.loads(last["payload"]) == {"n": 7}
        assert last["origin_stream"] == stream
        assert last["error"] == "permanent failure"
        # Cleanup our entry
        await redis.xdel(STREAM_DEAD_LETTER, str(last_id))

    async def test_claim_stale_recovers_dead_consumer_messages(
        self, redis: Redis, stream: str
    ) -> None:
        dead = StreamQueue(redis, group="test-group", consumer="dead-consumer", stale_claim_ms=0)
        await dead.ensure_group(stream)
        await dead.publish(stream, {"n": 9})
        await dead.consume(stream, count=1, block_ms=100)  # claimed, never acked

        survivor = StreamQueue(redis, group="test-group", consumer="survivor", stale_claim_ms=0)
        [claimed] = await survivor.claim_stale(stream)
        assert claimed.payload == {"n": 9}
        await survivor.ack(claimed)
        await redis.delete(stream)


class TestHeartbeat:
    async def test_beat_registers_and_stop_deregisters(self, redis: Redis) -> None:
        hb = Heartbeat(redis, worker_type=WorkerType.CRAWLER, worker_id=f"t-{uuid.uuid4().hex}")
        await hb.start()
        try:
            workers = await Heartbeat.list_workers(redis)
            me = next(w for w in workers if w.worker_id == hb.worker_id)
            assert me.worker_type == WorkerType.CRAWLER
            assert me.age_seconds < 5
        finally:
            await hb.stop()
        workers = await Heartbeat.list_workers(redis)
        assert all(w.worker_id != hb.worker_id for w in workers)

    async def test_reap_stale_removes_dead_workers(self, redis: Redis) -> None:
        worker_id = f"t-{uuid.uuid4().hex}"
        await redis.hset(
            HEARTBEAT_KEY,
            worker_id,
            json.dumps(
                {
                    "worker_type": "crawler",
                    "status": "running",
                    "hostname": "gone",
                    "pid": 1,
                    "last_beat_at": time.time() - 3600,
                    "meta": {},
                }
            ),
        )
        removed = await Heartbeat.reap_stale(redis, stale_after_seconds=120)
        assert removed >= 1
        assert await redis.hget(HEARTBEAT_KEY, worker_id) is None


class TestDomainRateLimiter:
    async def test_burst_then_throttle(self, redis: Redis) -> None:
        limiter = DomainRateLimiter(redis)
        domain = f"rl-{uuid.uuid4().hex[:8]}.example.com"

        # burst=2 → first two immediate, third throttled
        allowed1, _ = await limiter.acquire(domain, requests_per_second=1.0, burst=2)
        allowed2, _ = await limiter.acquire(domain, requests_per_second=1.0, burst=2)
        allowed3, wait3 = await limiter.acquire(domain, requests_per_second=1.0, burst=2)
        assert (allowed1, allowed2, allowed3) == (True, True, False)
        assert 0 < wait3 <= 1.0

    async def test_tokens_refill_over_time(self, redis: Redis) -> None:
        limiter = DomainRateLimiter(redis)
        domain = f"rl-{uuid.uuid4().hex[:8]}.example.com"

        allowed, _ = await limiter.acquire(domain, requests_per_second=50.0, burst=1)
        assert allowed
        allowed, _ = await limiter.acquire(domain, requests_per_second=50.0, burst=1)
        assert not allowed
        await asyncio.sleep(0.05)  # 50 rps → refills in 20ms
        allowed, _ = await limiter.acquire(domain, requests_per_second=50.0, burst=1)
        assert allowed

    async def test_domains_are_independent(self, redis: Redis) -> None:
        limiter = DomainRateLimiter(redis)
        a, b = (f"rl-{uuid.uuid4().hex[:8]}.example.com" for _ in range(2))
        await limiter.acquire(a, requests_per_second=0.1, burst=1)
        allowed_b, _ = await limiter.acquire(b, requests_per_second=0.1, burst=1)
        assert allowed_b


class TestControlSignals:
    async def test_publish_and_receive(self, redis: Redis) -> None:
        received: list[ControlSignal] = []
        event = asyncio.Event()

        async def handler(signal: ControlSignal) -> None:
            received.append(signal)
            event.set()

        listener = ControlListener(redis, handler)
        await listener.start()
        await asyncio.sleep(0.1)  # let the subscription establish
        try:
            job_id = uuid.uuid4()
            await publish_signal(redis, ControlSignal(action=ControlAction.PAUSE, job_id=job_id))
            await asyncio.wait_for(event.wait(), timeout=2)
        finally:
            await listener.stop()

        assert received[0].action == ControlAction.PAUSE
        assert received[0].job_id == job_id

    async def test_malformed_signal_does_not_kill_listener(self, redis: Redis) -> None:
        received: list[ControlSignal] = []
        event = asyncio.Event()

        async def handler(signal: ControlSignal) -> None:
            received.append(signal)
            event.set()

        listener = ControlListener(redis, handler)
        await listener.start()
        await asyncio.sleep(0.1)
        try:
            from newscrawl_contracts.streams import CONTROL_CHANNEL

            await redis.publish(CONTROL_CHANNEL, "{not json")
            await publish_signal(redis, ControlSignal(action=ControlAction.RESUME))
            await asyncio.wait_for(event.wait(), timeout=2)
        finally:
            await listener.stop()

        assert received[0].action == ControlAction.RESUME


class TestGracefulShutdown:
    async def test_trigger_and_wait(self) -> None:
        shutdown = GracefulShutdown()
        assert await shutdown.wait(timeout=0.01) is False

        shutdown.trigger()
        assert await shutdown.wait(timeout=0.01) is True
        assert shutdown.should_stop


@pytest.fixture(autouse=True)
async def _cleanup_delayed(redis: Redis) -> AsyncIterator[None]:
    """Remove any test envelopes left in the shared delayed zset."""
    yield
    entries = await redis.zrange(DELAYED_JOBS_KEY, 0, -1)
    for entry in entries:
        text = entry if isinstance(entry, str) else str(entry)
        if "test:stream:" in text:
            await redis.zrem(DELAYED_JOBS_KEY, text)
