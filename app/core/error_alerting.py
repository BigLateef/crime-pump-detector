"""
Sends a Discord alert immediately, from inside a global FastAPI exception
handler (see main.py), whenever ANY request anywhere in the app would
otherwise return a 500 with no visibility beyond Render's logs. This is
deliberately a separate, simpler path from the queue-based
DiscordDelivery system in app/workers/discord_delivery.py - that system
is designed to be DB-backed and cron-driven for idempotency/retry
guarantees around real trading signals, which means an alert queued
through it can sit for up to an hour before the next scan cycle's
deliver_pending() call actually sends it. That delay defeats the entire
point here ("know now, don't dig through logs"), so this module sends
directly via httpx instead, synchronously, from within the failing
request itself.

Known, deliberate limitation, stated plainly rather than glossed over:
this still needs ONE piece of data from Postgres - which enabled
DiscordIntegration(s) to notify and their decrypted webhook URL. If the
underlying 500 is itself a full database outage, this lookup will also
fail, and no alert can be sent - that's a real chicken-and-egg limit of
alerting *from inside* the app that just broke. It's wrapped in its own
try/except so a DB-outage 500 still returns a clean response to the
original caller instead of the error handler itself crashing, but no
Discord alert reaches you for that specific class of failure. External
uptime monitoring (e.g. a service pinging /health on a schedule) is the
correct complementary tool for "the whole app/DB is down" - nothing
running inside the app can reliably alert about the app itself being
unable to run code.
"""
import hashlib
import logging

import httpx
from redis.exceptions import RedisError
from sqlalchemy import select

from app.core.config import get_settings
from app.core.crypto import decrypt_webhook_url
from app.core.db import AsyncSessionLocal
from app.core.redis_client import get_redis
from app.models.discord import DiscordIntegration

logger = logging.getLogger("error_alerting")

_COOLDOWN_SECONDS = 300  # 5 min - same bug hitting repeatedly shouldn't spam Discord


async def _in_cooldown(cooldown_key: str) -> bool:
    """Redis-only, no DB dependency - if Redis is also down, fails open
    (treats as not-in-cooldown) since under-alerting during a genuine
    double-outage is worse than a few extra Discord messages."""
    try:
        redis = get_redis()
        key = f"error-alert-cooldown:{cooldown_key}"
        exists = await redis.get(key)
        if exists:
            return True
        await redis.set(key, "1", ex=_COOLDOWN_SECONDS)
        return False
    except RedisError as e:
        logger.warning("error-alert cooldown check degraded: Redis unreachable (%s) - proceeding without dedup", type(e).__name__)
        return False


async def alert_on_unhandled_error(*, method: str, path: str, exc: BaseException) -> None:
    """
    Best-effort, fire-and-forget in spirit (callers should not let a
    failure here affect the response already being sent for the original
    request) - every failure mode inside this function is caught and
    logged, never re-raised, since an error handler that itself raises
    is a much worse outcome than a missed alert.
    """
    settings = get_settings()
    error_type = type(exc).__name__
    # Truncated, type+message only - never the full traceback. A
    # traceback can carry SQL parameter values, request body contents,
    # or connection details; error_type + a short message is enough to
    # tell you something broke and roughly what, without risking a
    # secret ending up in a Discord channel. Full detail still belongs
    # in Render's logs, which this alert should prompt you to go check,
    # not replace.
    message = str(exc)[:300]

    cooldown_key = hashlib.sha256(f"{method}:{path}:{error_type}".encode()).hexdigest()
    if await _in_cooldown(cooldown_key):
        return

    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(DiscordIntegration).where(DiscordIntegration.enabled.is_(True)))
            integrations = result.scalars().all()
    except Exception as e:  # noqa: BLE001 - DB itself may be the thing that's down
        logger.error(
            "cannot send error alert to Discord: failed to look up integrations (%s) - "
            "this may itself be a database outage, which this mechanism cannot alert on; "
            "see this module's docstring",
            type(e).__name__,
        )
        return

    if not integrations:
        return  # nothing configured to notify - not an error, just nothing to do

    embed = {
        "title": f"APPLICATION ERROR — {error_type}",
        "color": 0xEF4444,
        "fields": [
            {"name": "Endpoint", "value": f"{method} {path}"[:200], "inline": False},
            {"name": "Error", "value": message or "(no message)", "inline": False},
        ],
        "footer": {"text": "Check Render logs for the full traceback - this alert is a pointer, not the detail."},
    }

    async with httpx.AsyncClient(timeout=settings.data_request_timeout_seconds) as client:
        for integration in integrations:
            try:
                webhook_url = decrypt_webhook_url(integration.encrypted_webhook_url)
                resp = await client.post(webhook_url, json={"embeds": [embed]})
                if resp.status_code >= 400:
                    logger.warning("error-alert Discord send failed for integration=%s: HTTP %d", integration.id, resp.status_code)
            except Exception as e:  # noqa: BLE001 - one bad integration must not block the others, or crash this handler
                logger.warning("error-alert Discord send raised for integration=%s: %s", integration.id, type(e).__name__)
