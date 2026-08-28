"""
Tests:
- alert_on_unhandled_error sends a Discord embed for a real
  DiscordIntegration, with only a truncated error summary (never a full
  traceback or anything secret-shaped).
- The cooldown suppresses a repeat of the exact same (method, path,
  error type) within the window, but not a different one.
- A DB-lookup failure (simulating the "the outage IS the database"
  chicken-and-egg case this module's docstring calls out) is swallowed,
  not re-raised - an error handler that itself raises would be a much
  worse outcome than a missed alert.

NOT EXECUTED in this sandbox: needs httpx/sqlalchemy/redis, unavailable
offline. Syntax-checked only, same as the rest of this test suite.
"""
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.core.error_alerting import _in_cooldown, alert_on_unhandled_error


class _WorkingRedis:
    def __init__(self):
        self.store = {}

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value, ex=None, nx=False):
        if nx and key in self.store:
            return None
        self.store[key] = value
        return True


class _BrokenRedis:
    async def get(self, key):
        from redis.exceptions import ConnectionError as RedisConnectionError
        raise RedisConnectionError("simulated outage")

    async def set(self, key, value, ex=None, nx=False):
        from redis.exceptions import ConnectionError as RedisConnectionError
        raise RedisConnectionError("simulated outage")


@pytest.mark.asyncio
async def test_cooldown_suppresses_repeat_of_same_key():
    redis = _WorkingRedis()
    with patch("app.core.error_alerting.get_redis", return_value=redis):
        first = await _in_cooldown("same-key")
        second = await _in_cooldown("same-key")
        different = await _in_cooldown("different-key")
    assert first is False
    assert second is True
    assert different is False


@pytest.mark.asyncio
async def test_cooldown_fails_open_when_redis_unreachable():
    with patch("app.core.error_alerting.get_redis", return_value=_BrokenRedis()):
        result = await _in_cooldown("any-key")
    assert result is False  # degrades to "not in cooldown", not an exception


@pytest.mark.asyncio
async def test_alert_sends_truncated_summary_never_full_traceback():
    from types import SimpleNamespace

    integration = SimpleNamespace(id="int-1", enabled=True, encrypted_webhook_url="enc-token")
    sent_payloads = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent_payloads.append(request)
        return httpx.Response(200)

    class _FakeResult:
        def scalars(self):
            class _S:
                def all(self_inner):
                    return [integration]
            return _S()

    class _FakeSession:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            return False
        async def execute(self, *a, **k):
            return _FakeResult()

    long_message = "x" * 5000  # simulate an unusually long exception message

    with patch("app.core.error_alerting.get_redis", return_value=_WorkingRedis()), \
         patch("app.core.error_alerting.AsyncSessionLocal", return_value=_FakeSession()), \
         patch("app.core.error_alerting.decrypt_webhook_url", return_value="https://discord.example/webhook"), \
         patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = httpx.Response(200)
        await alert_on_unhandled_error(method="POST", path="/internal/scanner/run", exc=ValueError(long_message))

    assert mock_post.called
    sent_json = mock_post.call_args.kwargs.get("json") or mock_post.call_args[1].get("json")
    embed = sent_json["embeds"][0]
    error_field = next(f for f in embed["fields"] if f["name"] == "Error")
    # Truncated well below the full 5000-char message - never sends the
    # raw exception in full, per this module's own stated policy.
    assert len(error_field["value"]) <= 310


@pytest.mark.asyncio
async def test_alert_swallows_db_lookup_failure_instead_of_raising():
    class _FailingSession:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *a):
            return False
        async def execute(self, *a, **k):
            raise RuntimeError("simulated DB outage")

    with patch("app.core.error_alerting.get_redis", return_value=_WorkingRedis()), \
         patch("app.core.error_alerting.AsyncSessionLocal", return_value=_FailingSession()):
        # Must not raise - an error handler raising during error handling
        # is the one outcome this module is built to avoid.
        await alert_on_unhandled_error(method="GET", path="/tokens", exc=RuntimeError("original error"))
