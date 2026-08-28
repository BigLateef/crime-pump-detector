from redis.asyncio import Redis, from_url
from redis.exceptions import BusyLoadingError, ConnectionError as RedisConnectionError, TimeoutError as RedisTimeoutError

from app.core.config import get_settings

_settings = get_settings()
_redis: Redis | None = None


def get_redis() -> Redis:
    global _redis
    if _redis is None:
        _redis = from_url(
            _settings.redis_url,
            decode_responses=True,
            # Without retry_on_timeout/retry_on_error, a connection that
            # goes idle between scan cycles (e.g. an hourly cron, or a
            # hosting-side idle timeout silently dropping it) fails its
            # *first* command outright instead of transparently retrying
            # once - which looks exactly like "works right after a fresh
            # deploy, degrades intermittently afterward". Per redis-py's
            # own docs, passing either of these without an explicit
            # `retry=` object already gives one real retry
            # (Retry(NoBackoff(), 1)) - no separate Retry() construction
            # needed for that baseline improvement.
            #
            # Deliberately NOT setting health_check_interval here despite
            # it being the more complete fix for a silently-stale
            # connection: redis-py has an open, unresolved bug
            # (github.com/redis/redis-py issue #3745, filed Aug 2025)
            # where combining retry_on_timeout=True with
            # health_check_interval>0 on the async client causes an
            # infinite-recursion crash during connection setup. This
            # module is imported on nearly every request path in this
            # app, so a crash here is a strictly worse failure mode than
            # the intermittent 503 this change is meant to reduce -
            # not worth the risk without confirming redis==5.2.0
            # (this app's pinned version) is unaffected, which wasn't
            # possible to verify from outside a real environment.
            retry_on_timeout=True,
            retry_on_error=[RedisConnectionError, RedisTimeoutError, BusyLoadingError],
            socket_keepalive=True,
        )
    return _redis
