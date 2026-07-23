"""Per-domain politeness rate limiter (distributed token bucket).

All crawl workers share one budget per domain, so adding workers never
increases pressure on a news site. Implemented as an atomic Lua token
bucket: tokens refill at `rate` per second up to `burst`.
"""

from newscrawl_contracts.streams import RATE_LIMIT_PREFIX
from redis.asyncio import Redis

# KEYS[1] = bucket key
# ARGV = rate (tokens/sec), burst (max tokens), now (float seconds)
# Returns {allowed (0/1), wait_seconds (float as string)}
_BUCKET_SCRIPT_LUA = """
local key = KEYS[1]
local rate = tonumber(ARGV[1])
local burst = tonumber(ARGV[2])
local now = tonumber(ARGV[3])

local data = redis.call('HMGET', key, 'tokens', 'ts')
local tokens = tonumber(data[1])
local ts = tonumber(data[2])
if tokens == nil then
  tokens = burst
  ts = now
end

tokens = math.min(burst, tokens + (now - ts) * rate)

local allowed = 0
local wait = 0.0
if tokens >= 1 then
  tokens = tokens - 1
  allowed = 1
else
  wait = (1 - tokens) / rate
end

redis.call('HSET', key, 'tokens', tokens, 'ts', now)
redis.call('EXPIRE', key, math.ceil(burst / rate) + 60)
return {allowed, tostring(wait)}
"""


class DomainRateLimiter:
    def __init__(self, redis: Redis) -> None:
        self.redis = redis
        self._script = redis.register_script(_BUCKET_SCRIPT_LUA)

    async def acquire(
        self, domain: str, *, requests_per_second: float = 0.5, burst: int = 2
    ) -> tuple[bool, float]:
        """Try to take one request token for a domain.

        Returns (allowed, wait_seconds). When not allowed, the caller should
        wait `wait_seconds` before retrying.
        """
        import time

        allowed, wait = await self._script(
            keys=[f"{RATE_LIMIT_PREFIX}{domain}"],
            args=[requests_per_second, burst, time.time()],
        )
        return bool(int(allowed)), float(wait)

    async def wait_time(self, domain: str, *, requests_per_second: float = 0.5) -> float:
        """Peek at the current wait without consuming a token."""
        import time

        data = await self.redis.hmget(f"{RATE_LIMIT_PREFIX}{domain}", "tokens", "ts")
        tokens_raw, ts_raw = data
        if tokens_raw is None or ts_raw is None:
            return 0.0
        tokens = min(float(tokens_raw) + (time.time() - float(ts_raw)) * requests_per_second, 1.0)
        if tokens >= 1:
            return 0.0
        return (1 - tokens) / requests_per_second
