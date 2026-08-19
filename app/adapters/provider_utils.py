"""
Shared helpers for every live data adapter: a Redis-backed cache keyed by
provider+params, and a retry wrapper with timeout + exponential backoff.
Both are provider-agnostic so DexScreener, GoPlus, or any future adapter
use the same behavior instead of each reinventing it.
"""
import asyncio
import json
import logging
from typing import Awaitable, Callable, TypeVar

import httpx
from redis.exceptions import RedisError

from app.core.config import get_settings
from app.core.redis_client import get_redis

logger = logging.getLogger("adapters.cache")
T = TypeVar("T")


async def cached_fetch(cache_key: str, fetch_fn: Callable[[], Awaitable[dict]], ttl_seconds: int | None = None) -> tuple[dict, bool]:
    """
    Returns (data, from_cache). Cache stores raw provider JSON, not the
    parsed TokenSnapshot, so a TTL expiry always re-derives freshness from
    a real fetch rather than an adapter-side timestamp trick.

    Caching is an optimization, not a correctness requirement — if Redis
    is unreachable, this falls through to a direct (uncached) fetch
    rather than failing the whole request. The write-back to cache is
    also best-effort: a failed `redis.set` after a successful fetch still
    returns real data to the caller, just without caching it this time.
    """
    settings = get_settings()
    ttl = ttl_seconds if ttl_seconds is not None else settings.data_cache_ttl_seconds

    try:
        redis = get_redis()
        cached = await redis.get(cache_key)
        if cached is not None:
            return json.loads(cached), True
    except RedisError as e:
        logger.warning("cache read failed (%s) for key=%s - falling through to a direct fetch", type(e).__name__, cache_key)

    data = await fetch_fn()

    try:
        redis = get_redis()
        await redis.set(cache_key, json.dumps(data), ex=ttl)
    except RedisError as e:
        logger.warning("cache write failed (%s) for key=%s - continuing without caching this result", type(e).__name__, cache_key)

    return data, False


async def fetch_with_retries(
    fetch_fn: Callable[[], Awaitable[httpx.Response]],
    max_retries: int | None = None,
    timeout_seconds: float | None = None,
) -> httpx.Response:
    """
    Retries on timeout, connection error, and 429/5xx responses, with
    exponential backoff (0.5s, 1s, 2s, ...). Raises the last exception (or
    returns the last non-retryable response) once retries are exhausted —
    callers must not treat a raised exception here as "no data", only as
    "provider unreachable"; see adapters/base.py DataStatus for how that
    gets surfaced to the rest of the app.
    """
    settings = get_settings()
    retries = max_retries if max_retries is not None else settings.data_max_retries
    last_exc: Exception | None = None

    for attempt in range(retries + 1):
        try:
            resp = await fetch_fn()
            if resp.status_code == 429 or resp.status_code >= 500:
                if attempt < retries:
                    await asyncio.sleep(0.5 * (2**attempt))
                    continue
            return resp
        except (httpx.TimeoutException, httpx.ConnectError) as e:
            last_exc = e
            logger.warning("provider fetch attempt %d failed: %s", attempt + 1, type(e).__name__)
            if attempt < retries:
                await asyncio.sleep(0.5 * (2**attempt))
                continue
            raise

    if last_exc:
        raise last_exc
    raise RuntimeError("fetch_with_retries exhausted without a response or exception")
