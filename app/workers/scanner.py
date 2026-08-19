"""
Shared scanner: one scan pass covers every user's watchlist/preferences at
once — never a worker per user or per token (Section 13 hard requirement).

Cost-control behavior implemented here:
- MAX_TOKENS_PER_BATCH caps work per invocation
- Per-token alert cooldown via Redis (ALERT_COOLDOWN_MINUTES) prevents
  re-alerting the same token every scan
- Security + scoring (deterministic, cheap) run before anything gated
  behind ENABLE_AI_ANALYSIS / ENABLE_SOCIAL_ANALYSIS
- Triggered externally by a cron ping to /internal/scan rather than an
  always-on loop, so idle time costs nothing

This function is intentionally invocation-based (call it once, it does one
batch and returns) so it can be driven by an external scheduler
(cron-job.org, GitHub Actions cron, etc.) exactly like the pattern used in
the dreamDEX bot project — see HANDOFF.md.
"""
import hashlib
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from redis.exceptions import RedisError

from app.adapters.factory import get_chain_adapter, get_security_adapter
from app.core import discord_alert_types as alert_types
from app.core.config import get_settings
from app.core.redis_client import get_redis
from app.models.discord import DiscordDelivery, DiscordIntegration
from app.models.token import SignalAlert, Token, TokenMetric
from app.scoring.engine import ScoringInput, score_token
from app.security.rules import evaluate_security, evaluate_security_check

logger = logging.getLogger("scanner")

_CHAINS = ["solana", "base", "ethereum", "bnb"]


def _fingerprint(token_id: str, signal_type: str, score: int) -> str:
    # Bucket score to the nearest 5 so near-identical re-scores of the same
    # token within a cooldown window still count as duplicates.
    bucket = round(score / 5) * 5
    raw = f"{token_id}:{signal_type}:{bucket}"
    return hashlib.sha256(raw.encode()).hexdigest()


async def _duplicate_alert_exists(db: AsyncSession, token_id: str, fingerprint: str, cooldown_minutes: int) -> bool:
    """
    The durable, database-backed half of duplicate prevention — see the
    Redis-outage note in the module docstring and in _in_cooldown().
    Queries for any alert with the exact same fingerprint for this token
    detected within the cooldown window. Works identically whether Redis
    is healthy, degraded, or fully down, because it never touches Redis.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=cooldown_minutes)
    result = await db.execute(
        select(SignalAlert.id)
        .where(
            SignalAlert.token_id == token_id,
            SignalAlert.signal_fingerprint == fingerprint,
            SignalAlert.detected_at >= cutoff,
        )
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


async def _in_cooldown(token_id: str, cooldown_minutes: int) -> bool:
    """
    If Redis is unreachable, treats the token as NOT in cooldown rather
    than raising and aborting the whole scan batch — the tradeoff is a
    possible duplicate alert during a Redis outage, which is recoverable,
    versus the scanner going fully dark, which isn't. Logged loudly either
    way so a Redis outage that also disables dedup is visible.
    """
    key = f"alert-cooldown:{token_id}"
    try:
        redis = get_redis()
        exists = await redis.get(key)
        if exists:
            return True
        await redis.set(key, "1", ex=cooldown_minutes * 60)
        return False
    except RedisError as e:
        logger.warning("cooldown check degraded: Redis unreachable (%s) for token=%s - proceeding without dedup", type(e).__name__, token_id)
        return False


async def run_scan_batch(db: AsyncSession) -> dict:
    """One scan batch across all chains. Returns summary stats for the
    system health dashboard (Section 13)."""
    settings = get_settings()
    adapter = get_chain_adapter()
    security_adapter = get_security_adapter()

    stats = {"tokens_scanned": 0, "alerts_created": 0, "skipped_cooldown": 0, "skipped_security": 0}

    per_chain_limit = max(1, settings.max_tokens_per_batch // len(_CHAINS))

    for chain in _CHAINS:
        try:
            snapshots = await adapter.discover_new_pairs(chain, limit=per_chain_limit)
        except NotImplementedError:
            # Real adapter for this chain isn't wired for discovery yet —
            # documented gap, not silently skipped. See adapters/dexscreener.py.
            logger.info("discovery not implemented for adapter=%s chain=%s", adapter.name, chain)
            continue
        except Exception as e:  # noqa: BLE001
            # A real failure (adapter timeout, malformed response, rate
            # limit, etc.) - as opposed to NotImplementedError above,
            # which is an expected/documented gap. Log it, alert on it
            # (SCANNER_FAILURE), and move on to the next chain rather
            # than letting one chain's failure abort the whole batch -
            # other chains' scans are independent and should still run.
            logger.warning("scan failed for chain=%s: %s", chain, e, exc_info=True)
            await _create_scanner_failure_delivery(db, chain, e)
            continue

        for snap in snapshots:
            stats["tokens_scanned"] += 1

            result = await db.execute(
                select(Token).where(Token.chain == snap.chain, Token.address == snap.address)
            )
            token = result.scalar_one_or_none()
            if token is None:
                token = Token(
                    chain=snap.chain,
                    address=snap.address,
                    name=snap.name,
                    symbol=snap.symbol,
                    pair_address=snap.pair_address,
                    dex=snap.dex,
                )
                db.add(token)
                await db.flush()

            db.add(
                TokenMetric(
                    token_id=token.id,
                    price=snap.price,
                    market_cap=snap.market_cap,
                    liquidity=snap.liquidity,
                    volume=snap.volume_24h,
                    buys=snap.buys_24h,
                    sells=snap.sells_24h,
                    unique_buyers=snap.unique_buyers_24h,
                    unique_sellers=snap.unique_sellers_24h,
                    holder_count=snap.holder_count,
                    data_status=snap.status.value,
                )
            )

            # Never score or alert on data we couldn't actually get — a
            # FAILED/UNAVAILABLE snapshot is stored (so freshness gaps are
            # visible) but never treated as safe-to-ignore or fabricated.
            from app.adapters.base import DataStatus as _DS

            if snap.status in (_DS.FAILED, _DS.UNAVAILABLE):
                continue

            # Security: deterministic first-stage filter (Section 8/13).
            # In live mode with GOPLUS_ENABLED, this calls the real adapter;
            # otherwise it fails closed via evaluate_security(None), never
            # assuming a token is safe just because no checker ran.
            if security_adapter is not None:
                check = await security_adapter.get_contract_security(token.chain, token.address)
                security = evaluate_security_check(check)
            else:
                security = evaluate_security(None)
            if not security.passed_minimum_requirements:
                stats["skipped_security"] += 1
                await _create_security_risk_delivery(db, token, security)
                continue

            buys = snap.buys_24h or 0
            sells = snap.sells_24h or 0
            imbalance = ((buys - sells) / (buys + sells)) if (buys + sells) > 0 else None

            scoring_input = ScoringInput(
                price_change_1h_pct=None,  # requires >=2 metric points; populated on later scans
                volume_accel_ratio=None,
                buy_sell_imbalance=imbalance,
                unique_buyers_1h=snap.unique_buyers_24h,
                liquidity_usd=snap.liquidity,
                top10_holder_pct=None,
                holder_count=snap.holder_count,
                security_score_penalty=security.score_penalty,
                security_passed_minimum=security.passed_minimum_requirements,
            )
            breakdown = score_token(scoring_input)

            confirming_categories = sum(1 for c in breakdown.components if c.startswith("+"))
            # Valid-signal floor is WATCH (score>=35 per scoring/engine.py),
            # not a hardcoded 55 - the old value here was actually the
            # EARLY floor, which silently prevented any WATCH-level
            # SignalAlert from ever being created. That's a structural
            # blocker for "send a Discord alert for every valid signal,
            # including WATCH" (spec requirement) - it has to be fixed
            # here, upstream of Discord delivery entirely, or WATCH
            # alerts can never exist no matter how Discord is configured.
            # AVOID is still excluded (mirrors scoring.engine.should_alert's
            # own semantics) since it means "nothing worth alerting on",
            # not a valid signal. Per-integration score/chain/type
            # filtering for what actually reaches Discord still happens
            # later, in _create_discord_deliveries.
            if breakdown.signal_level == "AVOID" or confirming_categories < 2:
                continue

            fingerprint = _fingerprint(token.id, breakdown.signal_level, breakdown.total)

            # Redis cooldown is a fast pre-check, not the source of truth —
            # it fails OPEN on its own (see _in_cooldown), so on its own it
            # cannot be trusted to prevent duplicates during a Redis outage.
            if await _in_cooldown(token.id, settings.alert_cooldown_minutes):
                stats["skipped_cooldown"] += 1
                continue

            # Durable, Redis-independent check: does an alert with this
            # exact fingerprint already exist for this token within the
            # cooldown window? This is the actual duplicate-prevention
            # guarantee — it works identically whether Redis is healthy,
            # degraded, or fully down, because it never touches Redis.
            if await _duplicate_alert_exists(db, token.id, fingerprint, settings.alert_cooldown_minutes):
                stats["skipped_cooldown"] += 1
                continue

            alert = SignalAlert(
                token_id=token.id,
                signal_type=breakdown.signal_level,
                signal_fingerprint=fingerprint,
                score=breakdown.total,
                confidence=breakdown.confidence,
                payload_json={
                    "reasons_summary": "; ".join(c for c in breakdown.components if c.startswith("+")) or "n/a",
                    "risk_summary": "; ".join(security.warnings) or "None flagged",
                    "invalidation_summary": "Liquidity drops >30%, deployer sells, or momentum reverses.",
                    "data_source": snap.data_source,
                    "data_status": snap.status.value,
                },
                detected_at=datetime.now(timezone.utc),
                expires_at=datetime.now(timezone.utc) + timedelta(hours=6),
            )
            db.add(alert)
            await db.flush()  # populate alert.id before creating deliveries
            stats["alerts_created"] += 1

            deliveries_created = await _create_discord_deliveries(db, alert, token)
            stats["discord_deliveries_created"] = stats.get("discord_deliveries_created", 0) + deliveries_created

    await db.commit()
    return stats


async def _discord_delivery_in_cooldown(token_id: str, alert_type: str, cooldown_minutes: int) -> bool:
    """
    Discord-delivery-specific cooldown, separate from the scanner's
    signal-creation cooldown (_in_cooldown above, which governs whether a
    SignalAlert gets created at all - a decision Discord delivery doesn't
    get to revisit). This one exists because DISCORD_ALERT_ALL_SIGNALS
    can let WATCH-level SignalAlerts be created far more often than the
    old EARLY-floor gate did; without a second cooldown at the delivery
    layer, a token oscillating right at the WATCH/AVOID boundary could
    re-trigger a fresh Discord message on every single scan pass even
    though _duplicate_alert_exists lets each of those SignalAlerts
    through as legitimately "new" (different fingerprint bucket).

    Same fail-open policy as _in_cooldown: a Redis outage degrades to "no
    dedup" rather than blocking delivery entirely, logged loudly either
    way. Keyed by (token, alert_type) rather than just token, since a
    SECURITY_RISK and a SIGNAL_DETECTED alert for the same token are
    different concerns and shouldn't suppress each other.
    """
    key = f"discord-alert-cooldown:{alert_type}:{token_id}"
    try:
        redis = get_redis()
        exists = await redis.get(key)
        if exists:
            return True
        await redis.set(key, "1", ex=cooldown_minutes * 60)
        return False
    except RedisError as e:
        logger.warning(
            "discord cooldown check degraded: Redis unreachable (%s) for token=%s alert_type=%s - proceeding without dedup",
            type(e).__name__, token_id, alert_type,
        )
        return False


async def _insert_discord_delivery(
    db: AsyncSession,
    *,
    integration_id: str,
    alert_type: str,
    fingerprint: str,
    payload_json: dict,
    signal_alert_id: str | None = None,
    token_id: str | None = None,
) -> bool:
    """
    Shared insert path for every Discord alert type. Returns True if a
    new delivery row was created, False if one already existed (either
    per the pre-check or because a concurrent insert won the race - both
    are the expected, safe "already handled" outcome, not an error).

    Idempotency: the query-then-insert pre-check below has a TOCTOU race
    under true concurrency, same as the pre-existing SIGNAL_DETECTED path
    always had - the Redis scanner lock already prevents overlapping
    scan runs, so this is a defense-in-depth pre-filter, not the actual
    safety guarantee. The real guarantee is the DB-level UniqueConstraint
    on (fingerprint, discord_integration_id) (models/discord.py +
    migration 0003), enforced via the SAVEPOINT/IntegrityError handling
    below exactly as the original SIGNAL_DETECTED-only version did.
    """
    existing = await db.execute(
        select(DiscordDelivery.id).where(
            DiscordDelivery.fingerprint == fingerprint,
            DiscordDelivery.discord_integration_id == integration_id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        return False

    try:
        async with db.begin_nested():
            db.add(
                DiscordDelivery(
                    signal_alert_id=signal_alert_id,
                    token_id=token_id,
                    alert_type=alert_type,
                    fingerprint=fingerprint,
                    payload_json=payload_json,
                    discord_integration_id=integration_id,
                    status="pending",
                )
            )
            await db.flush()
    except IntegrityError:
        return False

    return True


async def _create_discord_deliveries(db: AsyncSession, alert: SignalAlert, token: Token) -> int:
    """
    Creates one DiscordDelivery row (status=pending, alert_type=
    SIGNAL_DETECTED) per enabled DiscordIntegration whose
    allowed_chains/alert_types match this alert, and whose minimum_score
    the alert clears - unless settings.discord_alert_all_signals is True,
    in which case the score check is skipped entirely and every matching
    integration gets a delivery regardless of score (spec requirement:
    "ignore minimum score filtering for Discord delivery" when that flag
    is set). Actual sending happens later via
    app.workers.discord_delivery.deliver(), driven by whatever process
    walks pending deliveries (see HANDOFF.md — currently invoked
    on-demand, not via a dedicated always-on worker, per the low-cost
    architecture).
    """
    settings = get_settings()
    result = await db.execute(select(DiscordIntegration).where(DiscordIntegration.enabled.is_(True)))
    integrations = result.scalars().all()

    created = 0
    for integration in integrations:
        if not settings.discord_alert_all_signals and alert.score < integration.minimum_score:
            continue
        if integration.allowed_chains and token.chain not in integration.allowed_chains:
            continue
        if integration.alert_types and alert.signal_type not in integration.alert_types:
            continue

        if await _discord_delivery_in_cooldown(token.id, alert_types.SIGNAL_DETECTED, settings.discord_alert_cooldown_minutes):
            continue

        inserted = await _insert_discord_delivery(
            db,
            integration_id=integration.id,
            alert_type=alert_types.SIGNAL_DETECTED,
            fingerprint=alert.signal_fingerprint,
            payload_json=alert.payload_json,
            signal_alert_id=alert.id,
            token_id=token.id,
        )
        if inserted:
            created += 1

    return created


async def _create_security_risk_delivery(db: AsyncSession, token: Token, security) -> int:
    """
    Emits a SECURITY_RISK Discord alert for a token that failed the
    minimum security requirements - these tokens never reach scoring, so
    without this they were previously dropped with zero visibility
    (only an internal stats counter). No score/classification filtering
    applies here: a security rejection is worth flagging to every
    enabled integration whose chain filter matches, on its own merits,
    independent of DISCORD_ALERT_ALL_SIGNALS (that flag only concerns
    score-based suppression, per the spec's own wording - it never
    mentions security alerts as being score-gated in the first place).

    Fingerprint is a fresh hash per (token, warnings) rather than reusing
    any SignalAlert fingerprint, since no SignalAlert exists for a token
    that failed security - see _insert_discord_delivery for why
    fingerprint (not signal_alert_id) is what actually prevents
    duplicates for alert types like this one.
    """
    settings = get_settings()
    warnings_key = "|".join(sorted(security.warnings))
    fingerprint = hashlib.sha256(f"{token.id}:{alert_types.SECURITY_RISK}:{warnings_key}".encode()).hexdigest()

    result = await db.execute(select(DiscordIntegration).where(DiscordIntegration.enabled.is_(True)))
    integrations = result.scalars().all()

    created = 0
    for integration in integrations:
        if integration.allowed_chains and token.chain not in integration.allowed_chains:
            continue

        if await _discord_delivery_in_cooldown(token.id, alert_types.SECURITY_RISK, settings.discord_alert_cooldown_minutes):
            continue

        payload = {
            "risk_summary": "; ".join(security.warnings) or "Failed minimum security requirements.",
            "chain": token.chain,
            "symbol": token.symbol,
        }
        inserted = await _insert_discord_delivery(
            db,
            integration_id=integration.id,
            alert_type=alert_types.SECURITY_RISK,
            fingerprint=fingerprint,
            payload_json=payload,
            token_id=token.id,
        )
        if inserted:
            created += 1

    return created


async def _create_scanner_failure_delivery(db: AsyncSession, chain: str, error: Exception) -> int:
    """
    Emits a SCANNER_FAILURE Discord alert when a scan pass for a chain
    raises - so an operator finds out from Discord instead of only from
    Render logs. Fingerprinted per (chain, error type, hour) so a
    persistently failing adapter doesn't spam one alert per scan
    invocation, but still re-alerts if the failure continues into a new
    hour.
    """
    settings = get_settings()
    hour_bucket = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H")
    fingerprint = hashlib.sha256(
        f"{alert_types.SCANNER_FAILURE}:{chain}:{type(error).__name__}:{hour_bucket}".encode()
    ).hexdigest()

    result = await db.execute(select(DiscordIntegration).where(DiscordIntegration.enabled.is_(True)))
    integrations = result.scalars().all()

    created = 0
    for integration in integrations:
        if await _discord_delivery_in_cooldown(f"scanner:{chain}", alert_types.SCANNER_FAILURE, settings.discord_alert_cooldown_minutes):
            continue

        payload = {"chain": chain, "error_type": type(error).__name__, "error": str(error)[:300]}
        inserted = await _insert_discord_delivery(
            db,
            integration_id=integration.id,
            alert_type=alert_types.SCANNER_FAILURE,
            fingerprint=fingerprint,
            payload_json=payload,
        )
        if inserted:
            created += 1

    return created
