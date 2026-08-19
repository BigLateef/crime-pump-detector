"""
Tests:
- scanner_lock.py: the scanner must never run without acquiring its lock,
  and must refuse (not silently proceed) if Redis is unreachable when
  trying to acquire it.
- scanner.py's _duplicate_alert_exists: the durable, DB-level half of
  duplicate-alert prevention, independent of Redis.
- Discord delivery idempotency: _create_discord_deliveries and
  _create_security_risk_delivery never create a second delivery row for
  the same (fingerprint, integration) pair - across every alert_type,
  not just SIGNAL_DETECTED.
- DISCORD_ALERT_ALL_SIGNALS: verifies the score gate is genuinely
  bypassed when the flag is on, and genuinely enforced when it's off.

NOT EXECUTED in this sandbox: needs `redis` + `sqlalchemy` + a real (or
mocked) async DB session, none available offline. Syntax-checked only.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from app.core.config import get_settings
from app.models.discord import DiscordDelivery, DiscordIntegration
from app.models.token import SignalAlert, Token
from app.workers.scanner import (
    _create_discord_deliveries,
    _create_security_risk_delivery,
    _discord_delivery_in_cooldown,
    _duplicate_alert_exists,
)
from app.workers.scanner_lock import ScannerLockUnavailable, acquire_lock


class _BrokenRedis:
    async def set(self, *args, **kwargs):
        raise RedisConnectionError("connection refused")

    async def get(self, *args, **kwargs):
        raise RedisConnectionError("connection refused")


class _WorkingRedis:
    def __init__(self):
        self.store = {}

    async def set(self, key, value, nx=False, ex=None):
        if nx and key in self.store:
            return None
        self.store[key] = value
        return True

    async def get(self, key):
        return self.store.get(key)

    async def delete(self, key):
        self.store.pop(key, None)


@pytest.mark.asyncio
async def test_scanner_lock_raises_when_redis_unreachable():
    """The scanner must never run without its lock - if Redis can't even
    be reached to attempt acquiring one, acquire_lock must raise rather
    than silently returning a run ID."""
    with patch("app.workers.scanner_lock.get_redis", return_value=_BrokenRedis()):
        with pytest.raises(ScannerLockUnavailable):
            await acquire_lock()


@pytest.mark.asyncio
async def test_scanner_lock_prevents_concurrent_acquisition():
    redis = _WorkingRedis()
    with patch("app.workers.scanner_lock.get_redis", return_value=redis):
        first = await acquire_lock()
        assert first is not None
        second = await acquire_lock()
        assert second is None  # already held


@pytest.mark.asyncio
async def test_duplicate_alert_exists_finds_recent_matching_fingerprint(db_session):
    token = Token(chain="solana", address="addr-dup-test", symbol="DUP")
    db_session.add(token)
    await db_session.flush()

    existing = SignalAlert(
        token_id=token.id,
        signal_type="EARLY",
        signal_fingerprint="abc123",
        score=60,
        confidence="medium",
        payload_json={},
        detected_at=datetime.now(timezone.utc) - timedelta(minutes=5),
    )
    db_session.add(existing)
    await db_session.commit()

    assert await _duplicate_alert_exists(db_session, token.id, "abc123", cooldown_minutes=30) is True
    assert await _duplicate_alert_exists(db_session, token.id, "different-fingerprint", cooldown_minutes=30) is False


@pytest.mark.asyncio
async def test_duplicate_alert_exists_ignores_alerts_outside_cooldown_window(db_session):
    token = Token(chain="solana", address="addr-old-test", symbol="OLD")
    db_session.add(token)
    await db_session.flush()

    old_alert = SignalAlert(
        token_id=token.id,
        signal_type="EARLY",
        signal_fingerprint="abc123",
        score=60,
        confidence="medium",
        payload_json={},
        detected_at=datetime.now(timezone.utc) - timedelta(hours=5),  # well outside a 30-min cooldown
    )
    db_session.add(old_alert)
    await db_session.commit()

    assert await _duplicate_alert_exists(db_session, token.id, "abc123", cooldown_minutes=30) is False


@pytest.mark.asyncio
async def test_discord_delivery_creation_is_idempotent(db_session):
    """Calling _create_discord_deliveries twice for the same alert must
    not create two delivery rows for the same (fingerprint, integration)
    pair - this is the DB-level idempotency guarantee independent of
    Redis. Also doubles as the "cron retry does not create a duplicate
    delivery" case from the spec: a cron-triggered retry calling the
    scan/delivery path again for the same already-processed alert is
    exactly this same call-it-twice scenario."""
    from sqlalchemy import select

    token = Token(chain="solana", address="addr-idempotent", symbol="IDEM")
    db_session.add(token)
    await db_session.flush()

    integration = DiscordIntegration(
        name="test-channel",
        encrypted_webhook_url="encrypted-placeholder",
        enabled=True,
        minimum_score=0,
        allowed_chains=[],
        alert_types=[],
        created_by="admin-1",
    )
    db_session.add(integration)
    await db_session.flush()

    alert = SignalAlert(
        token_id=token.id,
        signal_type="EARLY",
        signal_fingerprint="fp-idempotent",
        score=60,
        confidence="medium",
        payload_json={},
        detected_at=datetime.now(timezone.utc),
    )
    db_session.add(alert)
    await db_session.flush()

    # _create_discord_deliveries now also checks a Redis-backed delivery
    # cooldown (_discord_delivery_in_cooldown) before inserting - patch a
    # real working fake here so the test exercises that path
    # deterministically instead of relying on the fail-open-on-
    # unreachable-Redis behavior to happen to make both assertions pass.
    with patch("app.workers.scanner.get_redis", return_value=_WorkingRedis()):
        first_count = await _create_discord_deliveries(db_session, alert, token)
        await db_session.commit()
        second_count = await _create_discord_deliveries(db_session, alert, token)
        await db_session.commit()

    assert first_count == 1
    assert second_count == 0  # already exists - not duplicated

    result = await db_session.execute(
        select(DiscordDelivery).where(DiscordDelivery.signal_alert_id == alert.id)
    )
    assert len(result.scalars().all()) == 1


@pytest.mark.asyncio
async def test_discord_delivery_unique_constraint_rejects_direct_duplicate_insert(db_session):
    """
    Bypasses the application-level existence check entirely and inserts
    the same (fingerprint, discord_integration_id) pair twice directly,
    to prove the DB constraint itself - not just the application logic
    in front of it - is what actually prevents the duplicate. This is
    the test that would catch a regression if someone removed the
    UniqueConstraint from the model or migration 0003. Uses two
    different signal_alert_ids on purpose: fingerprint (not
    signal_alert_id) is the real uniqueness key as of migration 0003,
    since several alert_types have no signal_alert_id at all.
    """
    from sqlalchemy.exc import IntegrityError

    token = Token(chain="solana", address="addr-concurrent-test", symbol="CONC")
    db_session.add(token)
    await db_session.flush()

    integration = DiscordIntegration(
        name="test-channel-2", encrypted_webhook_url="encrypted-placeholder",
        enabled=True, minimum_score=0, allowed_chains=[], alert_types=[],
        created_by="admin-1",
    )
    db_session.add(integration)
    await db_session.flush()

    alert_a = SignalAlert(
        token_id=token.id, signal_type="EARLY", signal_fingerprint="fp-concurrent-a",
        score=60, confidence="medium", payload_json={},
        detected_at=datetime.now(timezone.utc),
    )
    alert_b = SignalAlert(
        token_id=token.id, signal_type="EARLY", signal_fingerprint="fp-concurrent-b",
        score=60, confidence="medium", payload_json={},
        detected_at=datetime.now(timezone.utc),
    )
    db_session.add_all([alert_a, alert_b])
    await db_session.flush()

    db_session.add(DiscordDelivery(
        signal_alert_id=alert_a.id, discord_integration_id=integration.id,
        alert_type="SIGNAL_DETECTED", fingerprint="collide-me", payload_json={}, status="pending",
    ))
    await db_session.commit()

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            # Different signal_alert_id, but the SAME fingerprint+integration
            # - this must still collide, proving fingerprint (not
            # signal_alert_id) is what the constraint actually keys on.
            db_session.add(DiscordDelivery(
                signal_alert_id=alert_b.id, discord_integration_id=integration.id,
                alert_type="SIGNAL_DETECTED", fingerprint="collide-me", payload_json={}, status="pending",
            ))
            await db_session.flush()


@pytest.mark.asyncio
async def test_create_discord_deliveries_survives_a_simulated_race(db_session):
    """
    Simulates the race directly: pre-inserts a delivery row for (alert,
    integration) - as if a concurrent call already won - then calls
    _create_discord_deliveries again and confirms it returns 0 created
    (caught via IntegrityError, not raised to the caller) rather than
    crashing the scan batch.
    """
    token = Token(chain="solana", address="addr-race-test", symbol="RACE")
    db_session.add(token)
    await db_session.flush()

    integration = DiscordIntegration(
        name="test-channel-3", encrypted_webhook_url="encrypted-placeholder",
        enabled=True, minimum_score=0, allowed_chains=[], alert_types=[],
        created_by="admin-1",
    )
    db_session.add(integration)
    await db_session.flush()

    alert = SignalAlert(
        token_id=token.id, signal_type="EARLY", signal_fingerprint="fp-race",
        score=60, confidence="medium", payload_json={},
        detected_at=datetime.now(timezone.utc),
    )
    db_session.add(alert)
    await db_session.flush()

    # Simulate the "someone else already inserted it" half of the race by
    # inserting directly, bypassing _create_discord_deliveries' own
    # existence check. fingerprint must match what _create_discord_deliveries
    # itself would compute (alert.signal_fingerprint) for this to actually
    # simulate the same-row collision rather than an unrelated row.
    db_session.add(DiscordDelivery(
        signal_alert_id=alert.id, discord_integration_id=integration.id,
        alert_type="SIGNAL_DETECTED", fingerprint=alert.signal_fingerprint, payload_json={}, status="pending",
    ))
    await db_session.commit()

    # Now call the real function - its own existence check should already
    # catch this (the common, non-racy path), so this also covers that
    # fast path returning 0 rather than raising.
    with patch("app.workers.scanner.get_redis", return_value=_WorkingRedis()):
        created = await _create_discord_deliveries(db_session, alert, token)
    assert created == 0


@pytest.mark.asyncio
async def test_discord_delivery_cooldown_suppresses_repeat_within_window():
    """_discord_delivery_in_cooldown must return True on the second call
    for the same (token, alert_type) within the cooldown window, and
    False for a different alert_type on the same token (cooldowns are
    per alert_type, not just per token - a SECURITY_RISK alert
    shouldn't suppress an unrelated SIGNAL_DETECTED one)."""
    redis = _WorkingRedis()
    with patch("app.workers.scanner.get_redis", return_value=redis):
        first = await _discord_delivery_in_cooldown("token-1", "SIGNAL_DETECTED", cooldown_minutes=30)
        second = await _discord_delivery_in_cooldown("token-1", "SIGNAL_DETECTED", cooldown_minutes=30)
        different_type = await _discord_delivery_in_cooldown("token-1", "SECURITY_RISK", cooldown_minutes=30)

    assert first is False  # not in cooldown yet
    assert second is True  # now in cooldown
    assert different_type is False  # different alert_type, independent cooldown


@pytest.mark.asyncio
async def test_discord_delivery_cooldown_fails_open_when_redis_unreachable():
    """A Redis outage must degrade to 'not in cooldown' (fail open),
    same policy as _in_cooldown for signal creation - losing the
    Discord-delivery dedup layer is preferable to silently dropping
    real alerts because of an infrastructure blip. The DB-level
    fingerprint constraint is still the actual duplicate-prevention
    guarantee regardless."""
    with patch("app.workers.scanner.get_redis", return_value=_BrokenRedis()):
        result = await _discord_delivery_in_cooldown("token-1", "SIGNAL_DETECTED", cooldown_minutes=30)
    assert result is False


@pytest.mark.asyncio
async def test_high_score_valid_signal_is_delivered_with_score_filtering_on(db_session):
    """Baseline: with DISCORD_ALERT_ALL_SIGNALS off (default), a signal
    scoring above an integration's minimum_score is still delivered -
    confirms the default/legacy path wasn't broken by the all-signals
    feature."""
    settings = get_settings()
    with patch.object(settings, "discord_alert_all_signals", False):
        token = Token(chain="solana", address="addr-highscore", symbol="HIGH")
        db_session.add(token)
        await db_session.flush()

        integration = DiscordIntegration(
            name="high-score-channel", encrypted_webhook_url="encrypted-placeholder",
            enabled=True, minimum_score=55, allowed_chains=[], alert_types=[],
            created_by="admin-1",
        )
        db_session.add(integration)
        await db_session.flush()

        alert = SignalAlert(
            token_id=token.id, signal_type="EARLY", signal_fingerprint="fp-high",
            score=80, confidence="high", payload_json={},
            detected_at=datetime.now(timezone.utc),
        )
        db_session.add(alert)
        await db_session.flush()

        with patch("app.workers.scanner.get_redis", return_value=_WorkingRedis()):
            created = await _create_discord_deliveries(db_session, alert, token)
        assert created == 1


@pytest.mark.asyncio
async def test_low_score_signal_respects_threshold_when_all_signals_off(db_session):
    """DISCORD_ALERT_ALL_SIGNALS=false must respect the score threshold:
    a WATCH-level signal below an integration's minimum_score gets no
    delivery to that integration."""
    settings = get_settings()
    with patch.object(settings, "discord_alert_all_signals", False):
        token = Token(chain="solana", address="addr-lowscore-off", symbol="LOWOFF")
        db_session.add(token)
        await db_session.flush()

        integration = DiscordIntegration(
            name="strict-channel", encrypted_webhook_url="encrypted-placeholder",
            enabled=True, minimum_score=55, allowed_chains=[], alert_types=[],
            created_by="admin-1",
        )
        db_session.add(integration)
        await db_session.flush()

        alert = SignalAlert(
            token_id=token.id, signal_type="WATCH", signal_fingerprint="fp-low-off",
            score=40, confidence="low", payload_json={},
            detected_at=datetime.now(timezone.utc),
        )
        db_session.add(alert)
        await db_session.flush()

        with patch("app.workers.scanner.get_redis", return_value=_WorkingRedis()):
            created = await _create_discord_deliveries(db_session, alert, token)
        assert created == 0


@pytest.mark.asyncio
async def test_low_score_signal_is_delivered_when_all_signals_on(db_session):
    """DISCORD_ALERT_ALL_SIGNALS=true must ignore the score threshold
    entirely: the exact same WATCH-level, below-minimum_score signal as
    the test above IS delivered once the flag is on."""
    settings = get_settings()
    with patch.object(settings, "discord_alert_all_signals", True):
        token = Token(chain="solana", address="addr-lowscore-on", symbol="LOWON")
        db_session.add(token)
        await db_session.flush()

        integration = DiscordIntegration(
            name="strict-channel-2", encrypted_webhook_url="encrypted-placeholder",
            enabled=True, minimum_score=55, allowed_chains=[], alert_types=[],
            created_by="admin-1",
        )
        db_session.add(integration)
        await db_session.flush()

        alert = SignalAlert(
            token_id=token.id, signal_type="WATCH", signal_fingerprint="fp-low-on",
            score=40, confidence="low", payload_json={},
            detected_at=datetime.now(timezone.utc),
        )
        db_session.add(alert)
        await db_session.flush()

        with patch("app.workers.scanner.get_redis", return_value=_WorkingRedis()):
            created = await _create_discord_deliveries(db_session, alert, token)
        assert created == 1


@pytest.mark.asyncio
async def test_security_risk_delivery_creates_one_row_per_enabled_integration(db_session):
    """A token failing minimum security requirements must produce a
    SECURITY_RISK delivery for each enabled, chain-matching integration
    - this is the alert type that previously didn't exist at all (the
    token was just silently dropped with a stats counter increment)."""
    from types import SimpleNamespace

    token = Token(chain="solana", address="addr-secrisk", symbol="RISK")
    db_session.add(token)
    await db_session.flush()

    integration = DiscordIntegration(
        name="security-channel", encrypted_webhook_url="encrypted-placeholder",
        enabled=True, minimum_score=0, allowed_chains=[], alert_types=[],
        created_by="admin-1",
    )
    db_session.add(integration)
    await db_session.flush()

    security = SimpleNamespace(passed_minimum_requirements=False, warnings=["mint authority not renounced"])

    with patch("app.workers.scanner.get_redis", return_value=_WorkingRedis()):
        created = await _create_security_risk_delivery(db_session, token, security)
    assert created == 1

    from sqlalchemy import select
    result = await db_session.execute(
        select(DiscordDelivery).where(DiscordDelivery.token_id == token.id)
    )
    rows = result.scalars().all()
    assert len(rows) == 1
    assert rows[0].alert_type == "SECURITY_RISK"
    assert rows[0].signal_alert_id is None  # no SignalAlert exists for a security-failed token
    assert "mint authority not renounced" in rows[0].payload_json["risk_summary"]
