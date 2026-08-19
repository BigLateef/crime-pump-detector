"""
Fixed-window rate limiter backed by Redis.

Failure policy (security-reviewed, not just a convenience default):
- fail_open=False (the default): if Redis is unreachable, the request is
  REJECTED with a 503 — "cannot verify the rate limit, so don't allow the
  action." This is the required behavior for authentication, invite
  redemption, admin actions, uploads, and the internal scanner trigger —
  every endpoint where an attacker benefiting from "rate limiting quietly
  turned off" is a real risk.
- fail_open=True: if Redis is unreachable, the request is ALLOWED and the
  outage is logged at ERROR level. Only appropriate for low-risk,
  read-only endpoints where blocking legitimate traffic during a Redis
  blip is worse than the (bounded, read-only) abuse risk. Nothing in this
  codebase currently calls is_rate_limited with fail_open=True — every
  call site rate-limits a write or auth-adjacent action, so every call
  site fails closed. This flag exists so a future read-only endpoint has
  an explicit, reviewed way to opt out rather than silently inheriting
  fail-open behavior by default.

Either way, a Redis outage that affects rate limiting is always logged at
ERROR level — "fail closed" must never mean "fail silently."
"""
import logging

from fastapi import HTTPException, status
from redis.exceptions import RedisError

from app.core.redis_client import get_redis

logger = logging.getLogger("rate_limit")


class RateLimiterUnavailable(HTTPException):
    def __init__(self):
        super().__init__(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="This action is temporarily unavailable. Please try again shortly.",
        )


async def is_rate_limited(key: str, max_requests: int, window_seconds: int = 60, fail_open: bool = False) -> bool:
    try:
        redis = get_redis()
        current = await redis.incr(key)
        if current == 1:
            await redis.expire(key, window_seconds)
        return current > max_requests
    except RedisError as e:
        if fail_open:
            logger.error(
                "rate limiting degraded: Redis unreachable (%s) - FAILING OPEN for key=%s (explicitly allowed for this low-risk endpoint)",
                type(e).__name__, key,
            )
            return False
        logger.error(
            "rate limiting degraded: Redis unreachable (%s) - FAILING CLOSED for key=%s (rejecting the request)",
            type(e).__name__, key,
        )
        raise RateLimiterUnavailable() from e
