from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, JSON, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.user import gen_uuid


class Token(Base):
    __tablename__ = "tokens"
    __table_args__ = (UniqueConstraint("chain", "address", name="uq_token_chain_address"),)

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    chain: Mapped[str] = mapped_column(String(30), nullable=False)  # solana | base | ethereum | bnb
    address: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=True)
    symbol: Mapped[str] = mapped_column(String(30), nullable=True)
    pair_address: Mapped[str | None] = mapped_column(String(100), nullable=True)
    dex: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    last_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )


class TokenMetric(Base):
    __tablename__ = "token_metrics"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    token_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tokens.id"), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)
    price: Mapped[float] = mapped_column(Float, nullable=True)
    market_cap: Mapped[float] = mapped_column(Float, nullable=True)
    liquidity: Mapped[float] = mapped_column(Float, nullable=True)
    volume: Mapped[float] = mapped_column(Float, nullable=True)
    buys: Mapped[int] = mapped_column(Integer, nullable=True)
    sells: Mapped[int] = mapped_column(Integer, nullable=True)
    unique_buyers: Mapped[int] = mapped_column(Integer, nullable=True)
    unique_sellers: Mapped[int] = mapped_column(Integer, nullable=True)
    holder_count: Mapped[int] = mapped_column(Integer, nullable=True)
    security_score: Mapped[int] = mapped_column(Integer, nullable=True)
    # verified | cached | demo | unavailable | failed — see adapters/base.py DataStatus.
    # Lets the frontend show "DEMO DATA" / "stale" badges instead of presenting
    # any of this as live when it isn't.
    data_status: Mapped[str] = mapped_column(String(20), default="demo")


class SignalAlert(Base):
    __tablename__ = "signal_alerts"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    token_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tokens.id"), index=True)
    signal_type: Mapped[str] = mapped_column(String(30))  # WATCH|EARLY|HIGH-CONVICTION|AVOID|EXIT_DANGER
    # Dedup key: hash of (token_id, signal_type, rounded score bucket, time
    # bucket) — used to enforce per-token cooldowns and prevent duplicate
    # alerts, per Section 10/12.
    signal_fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    score: Mapped[int] = mapped_column(Integer)
    confidence: Mapped[str] = mapped_column(String(20))  # low | medium | high
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
