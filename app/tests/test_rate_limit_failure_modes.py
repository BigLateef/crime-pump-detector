"""
Tests app.core.rate_limit.is_rate_limited's failure-mode policy: fails
CLOSED (raises RateLimiterUnavailable, a 503) by default when Redis is
unreachable, and fails OPEN (returns False, logs ERROR) only when the
caller explicitly opts in with fail_open=True.

NOT EXECUTED in this sandbox: `redis` isn't installed offline (this
module imports `redis.exceptions.RedisError` at module load time).
Syntax-checked only via `python3 -m py_compile`. Run for real the first
time this project is picked up somewhere with network access.
"""
from unittest.mock import AsyncMock, patch

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from app.core.rate_limit import RateLimiterUnavailable, is_rate_limited


class _BrokenRedis:
    async def incr(self, key):
        raise RedisConnectionError("connection refused")


class _WorkingRedis:
    def __init__(self):
        self.counts = {}

    async def incr(self, key):
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    async def expire(self, key, seconds):
        pass


@pytest.mark.asyncio
async def test_fails_closed_by_default_on_redis_outage():
    with patch("app.core.rate_limit.get_redis", return_value=_BrokenRedis()):
        with pytest.raises(RateLimiterUnavailable):
            await is_rate_limited("test-key", max_requests=5)


@pytest.mark.asyncio
async def test_fails_open_when_explicitly_requested():
    with patch("app.core.rate_limit.get_redis", return_value=_BrokenRedis()):
        result = await is_rate_limited("test-key", max_requests=5, fail_open=True)
        assert result is False  # "not rate limited" == request allowed through


@pytest.mark.asyncio
async def test_normal_operation_still_rate_limits_correctly():
    redis = _WorkingRedis()
    with patch("app.core.rate_limit.get_redis", return_value=redis):
        for _ in range(3):
            limited = await is_rate_limited("test-key", max_requests=3)
            assert limited is False
        limited = await is_rate_limited("test-key", max_requests=3)
        assert limited is True  # 4th request exceeds max_requests=3


@pytest.mark.asyncio
async def test_outage_is_logged_at_error_level(caplog):
    with patch("app.core.rate_limit.get_redis", return_value=_BrokenRedis()):
        with pytest.raises(RateLimiterUnavailable):
            await is_rate_limited("test-key", max_requests=5)
    assert any(record.levelname == "ERROR" for record in caplog.records)
