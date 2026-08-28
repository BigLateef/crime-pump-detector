"""
Delivers signal alerts to configured Discord webhooks. Wallet addresses
are never included — smart-money/insider activity is summarized only as
"early wallets" / "deployer-linked wallets" text (Section 6/12).

Retry policy: exponential backoff, capped attempts, then
permanently_failed so a dead webhook doesn't retry forever and burn
worker time. Called by the scan-triggered flow (workers/scanner.py), not
as a standalone always-on loop — see Section 13 cost notes.
"""
import logging
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import discord_alert_types as alert_types
from app.core.crypto import decrypt_webhook_url
from app.models.discord import DiscordDelivery, DiscordIntegration
from app.models.token import SignalAlert, Token

logger = logging.getLogger("discord_delivery")

_MAX_ATTEMPTS = 5
_BACKOFF_BASE_SECONDS = 30  # 30s, 60s, 120s, 240s, 480s

_COLOR_BY_SIGNAL_LEVEL = {
    "HIGH-CONVICTION": 0x22C55E,
    "EARLY": 0x3B82F6,
    "WATCH": 0xF59E0B,
    "EXIT_DANGER": 0xEF4444,
    "AVOID": 0x6B7280,
}
_ALERT_TYPE_COLOR = {
    alert_types.SECURITY_RISK: 0xEF4444,
    alert_types.LIQUIDITY_WARNING: 0xF59E0B,
    alert_types.DEPLOYER_SELLING: 0xEF4444,
    alert_types.MOMENTUM_FAILURE: 0x6B7280,
    alert_types.MOMENTUM_RECOVERY: 0x22C55E,
    alert_types.SCANNER_FAILURE: 0x6B7280,
}

# Human-readable label for each DataStatus value (app/adapters/base.py) -
# never rendered as a bare string, always through this map, so a demo or
# unavailable/failed reading can never look identical to real data. See
# spec: "Never present non-verified data as verified."
_DATA_STATUS_LABEL = {
    "verified": "✅ VERIFIED (live data)",
    "cached": "✅ CACHED (verified, briefly stale)",
    "demo": "⚠️ DEMO (fictional, not live data)",
    "unavailable": "⚠️ UNAVAILABLE (provider had no data)",
    "failed": "❌ FAILED (provider call errored)",
}


def _data_status_field(payload: dict) -> dict | None:
    status_value = payload.get("data_status")
    if not status_value:
        return None
    label = _DATA_STATUS_LABEL.get(status_value, f"⚠️ UNKNOWN ({status_value})")
    return {"name": "Data status", "value": label, "inline": True}


def _build_signal_detected_embed(delivery: DiscordDelivery, alert: SignalAlert, token: Token) -> dict:
    payload = delivery.payload_json or alert.payload_json or {}
    fields = [
        {"name": "Chain", "value": token.chain, "inline": True},
        {"name": "Score", "value": str(alert.score), "inline": True},
        {"name": "Confidence", "value": alert.confidence, "inline": True},
        {"name": "Why it triggered", "value": payload.get("reasons_summary", "n/a"), "inline": False},
        {"name": "Risk flags", "value": payload.get("risk_summary", "None flagged"), "inline": False},
        {"name": "Invalidation", "value": payload.get("invalidation_summary", "n/a"), "inline": False},
    ]
    data_status_field = _data_status_field(payload)
    if data_status_field:
        fields.append(data_status_field)
    return {
        "title": f"{alert.signal_type} — ${token.symbol or '?'}",
        "color": _COLOR_BY_SIGNAL_LEVEL.get(alert.signal_type, 0x6B7280),
        "fields": fields,
        "footer": {"text": "Research alert only. Not financial advice. Do not chase."},
        "timestamp": alert.detected_at.isoformat() if alert.detected_at else None,
    }


def _build_security_risk_embed(delivery: DiscordDelivery, token: Token | None) -> dict:
    payload = delivery.payload_json or {}
    symbol = payload.get("symbol") or (token.symbol if token else None) or "?"
    chain = payload.get("chain") or (token.chain if token else "unknown")
    return {
        "title": f"SECURITY RISK — ${symbol}",
        "color": _ALERT_TYPE_COLOR[alert_types.SECURITY_RISK],
        "fields": [
            {"name": "Chain", "value": chain, "inline": True},
            {"name": "Risk flags", "value": payload.get("risk_summary", "Failed minimum security requirements."), "inline": False},
        ],
        "footer": {"text": "This token did not clear minimum security requirements and was not scored."},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _build_scanner_failure_embed(delivery: DiscordDelivery) -> dict:
    payload = delivery.payload_json or {}
    return {
        "title": "SCANNER FAILURE",
        "color": _ALERT_TYPE_COLOR[alert_types.SCANNER_FAILURE],
        "fields": [
            {"name": "Chain", "value": payload.get("chain", "unknown"), "inline": True},
            {"name": "Error type", "value": payload.get("error_type", "unknown"), "inline": True},
            {"name": "Detail", "value": payload.get("error", "n/a")[:500], "inline": False},
        ],
        "footer": {"text": "Operational alert - the scan for this chain did not complete."},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _build_generic_unimplemented_embed(delivery: DiscordDelivery) -> dict:
    """
    Fallback for alert_type values that are defined (see
    app/core/discord_alert_types.py) but have no detection logic wired
    up yet - LIQUIDITY_WARNING, DEPLOYER_SELLING, MOMENTUM_FAILURE,
    MOMENTUM_RECOVERY. Nothing in this codebase currently creates
    deliveries of these types, so this path should never actually run;
    it exists so that IF one somehow got created (e.g. a future partial
    implementation), delivery fails safely with a labeled placeholder
    instead of crashing on a KeyError.
    """
    payload = delivery.payload_json or {}
    return {
        "title": f"{delivery.alert_type} (unimplemented detection)",
        "color": _ALERT_TYPE_COLOR.get(delivery.alert_type, 0x6B7280),
        "fields": [{"name": "Payload", "value": str(payload)[:500] or "n/a", "inline": False}],
        "footer": {"text": "This alert type has no detection logic implemented yet."},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


async def deliver(db: AsyncSession, delivery_id: str) -> None:
    result = await db.execute(select(DiscordDelivery).where(DiscordDelivery.id == delivery_id))
    delivery = result.scalar_one_or_none()
    if delivery is None or delivery.status in ("sent", "permanently_failed"):
        return

    integration = (
        await db.execute(select(DiscordIntegration).where(DiscordIntegration.id == delivery.discord_integration_id))
    ).scalar_one_or_none()
    if integration is None or not integration.enabled:
        delivery.status = "permanently_failed"
        delivery.last_error = "Integration no longer exists / disabled."
        await db.commit()
        return

    # Every alert type after this point builds its own embed from
    # whatever data it actually has - SIGNAL_DETECTED requires a real
    # SignalAlert (fail permanently if it's gone, same as before);
    # SECURITY_RISK/SCANNER_FAILURE never had one to begin with, so their
    # embeds are built entirely from delivery.payload_json instead.
    alert: SignalAlert | None = None
    token: Token | None = None
    if delivery.signal_alert_id is not None:
        alert = (
            await db.execute(select(SignalAlert).where(SignalAlert.id == delivery.signal_alert_id))
        ).scalar_one_or_none()
        if alert is None:
            delivery.status = "permanently_failed"
            delivery.last_error = "Linked signal alert no longer exists."
            await db.commit()
            return
        token = (await db.execute(select(Token).where(Token.id == alert.token_id))).scalar_one_or_none()
    elif delivery.token_id is not None:
        token = (await db.execute(select(Token).where(Token.id == delivery.token_id))).scalar_one_or_none()

    if delivery.alert_type == alert_types.SIGNAL_DETECTED:
        embed = _build_signal_detected_embed(delivery, alert, token)
    elif delivery.alert_type == alert_types.SECURITY_RISK:
        embed = _build_security_risk_embed(delivery, token)
    elif delivery.alert_type == alert_types.SCANNER_FAILURE:
        embed = _build_scanner_failure_embed(delivery)
    else:
        embed = _build_generic_unimplemented_embed(delivery)

    delivery.attempt_count += 1
    try:
        webhook_url = decrypt_webhook_url(integration.encrypted_webhook_url)
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(webhook_url, json={"embeds": [embed]})
            resp.raise_for_status()
        delivery.status = "sent"
        delivery.sent_at = datetime.now(timezone.utc)
        delivery.next_retry_at = None
    except Exception as e:  # noqa: BLE001
        # Never log the webhook URL itself, only the error type/message.
        logger.warning("discord delivery failed", extra={"delivery_id": delivery.id, "error": str(e)})
        delivery.last_error = str(e)[:500]
        if delivery.attempt_count >= _MAX_ATTEMPTS:
            delivery.status = "permanently_failed"
            delivery.next_retry_at = None
        else:
            delivery.status = "failed"
            delivery.next_retry_at = datetime.now(timezone.utc) + timedelta(
                seconds=_backoff_seconds(delivery.attempt_count)
            )

    await db.commit()


async def deliver_pending(db: AsyncSession, limit: int = 50) -> dict:
    """
    Walks pending deliveries (status=pending, or status=failed whose
    next_retry_at has arrived) and attempts each one. Called from the
    same cron-triggered scan invocation as the scanner itself
    (app/api/internal.py) — deliberately not a separate always-on worker,
    per the low-cost architecture. `limit` bounds work per invocation the
    same way MAX_TOKENS_PER_BATCH bounds the scanner.
    """
    from datetime import datetime, timezone as _timezone

    now = datetime.now(_timezone.utc)
    result = await db.execute(
        select(DiscordDelivery.id).where(
            (DiscordDelivery.status == "pending")
            | ((DiscordDelivery.status == "failed") & (DiscordDelivery.next_retry_at <= now))
        ).limit(limit)
    )
    delivery_ids = [row[0] for row in result.all()]

    sent = failed = 0
    for delivery_id in delivery_ids:
        await deliver(db, delivery_id)
        refreshed = await db.execute(select(DiscordDelivery.status).where(DiscordDelivery.id == delivery_id))
        status_value = refreshed.scalar_one_or_none()
        if status_value == "sent":
            sent += 1
        elif status_value in ("failed", "permanently_failed"):
            failed += 1

    return {"attempted": len(delivery_ids), "sent": sent, "failed": failed}
