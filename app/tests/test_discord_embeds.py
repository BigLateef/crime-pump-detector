"""
Tests:
- Data status labeling: demo/unavailable/failed data is always visually
  distinct from verified/cached, never silently rendered the same way -
  "Never present non-verified data as verified" from the spec.
- Discord secrets never appear in what actually gets sent: the embed
  builders only ever read from delivery.payload_json / alert data, never
  from the integration's decrypted webhook URL, and DiscordIntegrationOut
  (the admin API schema) has no field that could leak one either.
- Wallet addresses are never included in a built embed - scoring's own
  reasons_summary text (see app/scoring/engine.py) describes wallet
  confirmations in aggregate ("2 independent early wallets confirmed"),
  never by address, so this is really confirming the embed builder
  doesn't add anything beyond what's already in that summary text.

NOT EXECUTED in this sandbox: needs sqlalchemy/httpx, unavailable
offline. Syntax-checked only, same as the rest of this test suite.
"""
from datetime import datetime, timezone
from types import SimpleNamespace

from app.core import discord_alert_types as alert_types
from app.workers.discord_delivery import (
    _build_scanner_failure_embed,
    _build_security_risk_embed,
    _build_signal_detected_embed,
    _data_status_field,
)


def _fake_delivery(**overrides):
    defaults = dict(payload_json={}, alert_type=alert_types.SIGNAL_DETECTED)
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_demo_data_status_is_labeled_and_visually_flagged():
    field = _data_status_field({"data_status": "demo"})
    assert field is not None
    assert "DEMO" in field["value"]
    # Must carry a visual warning marker, not just the word "demo" in
    # plain text sitting next to real data with no distinction.
    assert "⚠️" in field["value"]


def test_unavailable_data_is_never_labeled_verified():
    field = _data_status_field({"data_status": "unavailable"})
    assert field is not None
    assert "VERIFIED" not in field["value"]
    assert "UNAVAILABLE" in field["value"]
    assert "⚠️" in field["value"]


def test_failed_data_status_is_clearly_flagged():
    field = _data_status_field({"data_status": "failed"})
    assert field is not None
    assert "FAILED" in field["value"]
    assert "❌" in field["value"]


def test_verified_and_demo_labels_are_never_identical():
    verified = _data_status_field({"data_status": "verified"})["value"]
    demo = _data_status_field({"data_status": "demo"})["value"]
    cached = _data_status_field({"data_status": "cached"})["value"]
    unavailable = _data_status_field({"data_status": "unavailable"})["value"]
    failed = _data_status_field({"data_status": "failed"})["value"]
    labels = [verified, demo, cached, unavailable, failed]
    assert len(set(labels)) == len(labels)  # every status renders distinctly


def test_missing_data_status_produces_no_field_rather_than_a_false_default():
    # If payload_json has no data_status at all, the field must be
    # omitted entirely - defaulting to "verified" (or anything else)
    # when the status is simply unknown would itself be a false claim.
    assert _data_status_field({}) is None


def test_security_risk_embed_never_includes_webhook_or_wallet_fields():
    delivery = _fake_delivery(
        alert_type=alert_types.SECURITY_RISK,
        payload_json={"risk_summary": "mint authority not renounced", "chain": "solana", "symbol": "RISK"},
    )
    embed = _build_security_risk_embed(delivery, token=None)
    embed_text = str(embed).lower()
    assert "webhook" not in embed_text
    assert "encrypted_webhook_url" not in embed_text


def test_scanner_failure_embed_never_includes_webhook_fields():
    delivery = _fake_delivery(
        alert_type=alert_types.SCANNER_FAILURE,
        payload_json={"chain": "base", "error_type": "TimeoutError", "error": "adapter timed out after 10s"},
    )
    embed = _build_scanner_failure_embed(delivery)
    embed_text = str(embed).lower()
    assert "webhook" not in embed_text
    assert "api_key" not in embed_text
    assert "apikey" not in embed_text


def test_signal_detected_embed_never_leaks_a_raw_wallet_address():
    # Wallet addresses on Solana/EVM chains are long alphanumeric
    # strings - if scoring's reasons_summary ever included one directly
    # (it shouldn't - see app/scoring/engine.py's own comments on
    # aggregate-only wallet confirmations), this embed builder must not
    # be the thing that surfaces it either, since it only ever passes
    # payload text through, never reaches into raw security/wallet data
    # itself.
    alert = SimpleNamespace(
        signal_type="EARLY",
        score=60,
        confidence="high",
        detected_at=datetime.now(timezone.utc),
        payload_json={
            "reasons_summary": "2 independent early wallets confirmed",
            "risk_summary": "None flagged",
            "invalidation_summary": "n/a",
            "data_status": "verified",
        },
    )
    token = SimpleNamespace(symbol="TEST", chain="solana")
    delivery = _fake_delivery(alert_type=alert_types.SIGNAL_DETECTED, payload_json=alert.payload_json)
    embed = _build_signal_detected_embed(delivery, alert, token)
    embed_text = str(embed)
    # A real base58 Solana wallet address is 32-44 chars with no spaces;
    # confirm nothing that shape appears anywhere the builder produced.
    import re
    assert not re.search(r"\b[1-9A-HJ-NP-Za-km-z]{32,44}\b", embed_text)


def test_discord_integration_out_schema_has_no_webhook_field():
    """Confirms DiscordIntegrationOut - the schema returned by every
    admin Discord API response - literally cannot serialize a webhook
    URL, because the field doesn't exist on it at all. Read via AST-free
    reflection so this test doesn't need the full FastAPI/pydantic app
    import chain to run standalone."""
    from app.api.admin_discord import DiscordIntegrationOut

    field_names = set(DiscordIntegrationOut.model_fields.keys())
    assert "webhook_url" not in field_names
    assert "encrypted_webhook_url" not in field_names
    assert not any("webhook" in f.lower() for f in field_names)
    assert not any("secret" in f.lower() for f in field_names)
    assert not any("key" in f.lower() for f in field_names)
