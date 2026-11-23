"""Per-key fixed-window API limits backed by Redis."""

from dataclasses import dataclass

from redis import Redis

_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return {count, redis.call('TTL', KEYS[1])}
"""


@dataclass(frozen=True)
class RateDecision:
    allowed: bool
    remaining: int
    retry_after: int


class RedisRateLimiter:
    def __init__(self, client: Redis, limit: int = 60, window_seconds: int = 60):
        if limit < 1 or window_seconds < 1:
            raise ValueError("Rate limit and window must be positive")
        self.client = client
        self.limit = limit
        self.window_seconds = window_seconds

    def check(self, key_id: str) -> RateDecision:
        # Only internal key IDs are used; raw credentials never reach Redis.
        count, ttl = self.client.eval(_SCRIPT, 1, f"bharatos:rate:{key_id}", self.window_seconds)
        return RateDecision(
            allowed=count <= self.limit,
            remaining=max(0, self.limit - count),
            retry_after=max(1, ttl),
        )
