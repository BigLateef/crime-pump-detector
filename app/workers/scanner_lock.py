"""
Operational state for the shared scanner: a run-lock so two overlapping
cron pings can't both execute a scan batch at once, and last-success/
last-failure/freshness tracking so `/internal/scanner/status` (and the
frontend's system health page) can show real data instead of guessing.

All state lives in Redis, not the database — this is operational
telemetry, not user data, and Redis being momentarily unavailable should
degrade the scanner (see below), not take down the rest of the app.
"""
import json
import logging
import uuid
from datetime import datetime, timezone

from redis.exceptions import RedisError

from app.core.redis_client import get_redis

logger = logging.getLogger("scanner_lock")

_LOCK_KEY = "scanner:lock"
_LOCK_TTL_SECONDS = 600  # safety net: a crashed run can't hold the lock forever
_STATUS_KEY = "scanner:status"


class ScannerLockUnavailable(Exception):
    """Raised when Redis itself can't be reached to even attempt a lock.
    The caller should refuse to run a scan in this case — running without
    a lock risks two overlapping scans double-writing metrics/alerts,
    which is worse than skipping a scan cycle."""


async def acquire_lock() -> str | None:
    """
    Returns a run ID if the lock was acquired, None if another run already
    holds it. Uses SET NX EX (atomic) rather than a check-then-set to
    avoid a race between two concurrent cron pings.
    """
    run_id = str(uuid.uuid4())
    try:
        redis = get_redis()
        acquired = await redis.set(_LOCK_KEY, run_id, nx=True, ex=_LOCK_TTL_SECONDS)
        return run_id if acquired else None
    except RedisError as e:
        logger.error("cannot acquire scanner lock: Redis unreachable (%s)", type(e).__name__)
        raise ScannerLockUnavailable(str(e)) from e


async def release_lock(run_id: str) -> None:
    try:
        redis = get_redis()
        # Only release if we still hold it (best-effort check-and-delete;
        # a true Lua-script CAS isn't worth the complexity here since the
        # TTL safety net already bounds the worst case).
        current = await redis.get(_LOCK_KEY)
        if current == run_id:
            await redis.delete(_LOCK_KEY)
    except RedisError as e:
        logger.warning("could not release scanner lock cleanly (%s) - TTL will expire it", type(e).__name__)


async def record_success(stats: dict) -> None:
    await _record("success", stats=stats)


async def record_failure(error: str) -> None:
    await _record("failure", error=error)


async def _record(kind: str, stats: dict | None = None, error: str | None = None) -> None:
    now = datetime.now(timezone.utc).isoformat()
    try:
        redis = get_redis()
        existing_raw = await redis.get(_STATUS_KEY)
        status = json.loads(existing_raw) if existing_raw else {}
        if kind == "success":
            status["last_success_at"] = now
            status["last_success_stats"] = stats
        else:
            status["last_failure_at"] = now
            status["last_failure_error"] = error
        status["last_run_at"] = now
        await redis.set(_STATUS_KEY, json.dumps(status))
    except RedisError as e:
        logger.warning("could not record scanner status (%s) - status endpoint will be stale", type(e).__name__)


async def get_status() -> dict:
    try:
        redis = get_redis()
        raw = await redis.get(_STATUS_KEY)
        status = json.loads(raw) if raw else {}
    except RedisError as e:
        logger.warning("could not read scanner status (%s)", type(e).__name__)
        status = {}

    freshness_hours = None
    if status.get("last_success_at"):
        last = datetime.fromisoformat(status["last_success_at"])
        freshness_hours = (datetime.now(timezone.utc) - last).total_seconds() / 3600

    return {
        "last_run_at": status.get("last_run_at"),
        "last_success_at": status.get("last_success_at"),
        "last_success_stats": status.get("last_success_stats"),
        "last_failure_at": status.get("last_failure_at"),
        "last_failure_error": status.get("last_failure_error"),
        "data_freshness_hours": freshness_hours,
    }
