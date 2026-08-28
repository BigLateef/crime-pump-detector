from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, JSON, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.user import gen_uuid


class DiscordIntegration(Base):
    __tablename__ = "discord_integrations"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # Fernet-encrypted (app.core.crypto). Never returned by any API response
    # — see schemas/discord.py, which deliberately omits this field.
    encrypted_webhook_url: Mapped[str] = mapped_column(String(500), nullable=False)
    channel_label: Mapped[str] = mapped_column(String(100), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    minimum_score: Mapped[int] = mapped_column(Integer, default=55)
    allowed_chains: Mapped[list] = mapped_column(JSON, default=list)  # empty list = all chains
    alert_types: Mapped[list] = mapped_column(JSON, default=list)  # e.g. ["EARLY","HIGH-CONVICTION"]
    created_by: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )


class DiscordDelivery(Base):
    __tablename__ = "discord_deliveries"
    __table_args__ = (
        # The real, DB-enforced idempotency guarantee: no two rows can
        # ever exist for the same (fingerprint, integration) pair, even
        # under concurrent inserts racing past the application-level
        # existence check in app/workers/scanner.py's
        # _create_discord_deliveries / _create_typed_discord_delivery.
        # fingerprint (not signal_alert_id) is the canonical key here
        # because several alert_types (SECURITY_RISK, SCANNER_FAILURE)
        # have no SignalAlert row to key off of - see migration 0003.
        UniqueConstraint("fingerprint", "discord_integration_id", name="uq_discord_delivery_fingerprint_integration"),
    )

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    # Nullable: only SIGNAL_DETECTED (and any future signal-linked type)
    # populates this. SECURITY_RISK / SCANNER_FAILURE / etc. fire before
    # or without a SignalAlert ever being created - that's the whole
    # point of a security-risk alert firing when scoring never happened.
    signal_alert_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("signal_alerts.id"), nullable=True
    )
    # One of: SIGNAL_DETECTED | SECURITY_RISK | LIQUIDITY_WARNING |
    # DEPLOYER_SELLING | MOMENTUM_FAILURE | MOMENTUM_RECOVERY |
    # SCANNER_FAILURE - see app/core/discord_alert_types.py.
    alert_type: Mapped[str] = mapped_column(String(30))
    # Populated for token-scoped alert types (SECURITY_RISK etc.) that
    # need to reach the token without going through a SignalAlert.
    token_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("tokens.id"), nullable=True)
    # Dedup key for every alert_type uniformly - for SIGNAL_DETECTED this
    # is the same value as the linked SignalAlert.signal_fingerprint; for
    # types with no SignalAlert it's computed directly (see scanner.py).
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    # This delivery's own embed content. For SIGNAL_DETECTED this
    # duplicates what's already in the linked SignalAlert.payload_json
    # (kept for delivery-time snapshot stability - if the alert's
    # payload changes later, a not-yet-sent delivery still sends what
    # was true when it was created); for other types it's the only copy.
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
    discord_integration_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("discord_integrations.id")
    )
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|sent|failed|permanently_failed
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    discord_message_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
