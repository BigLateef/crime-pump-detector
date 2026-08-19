from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.user import gen_uuid


class PaperTrade(Base):
    """
    Simulated position only. No wallet connection, no real order
    execution — Section 14 is explicit that this must never place a real
    trade.
    """

    __tablename__ = "paper_trades"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"), index=True)
    token_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("tokens.id"), index=True)
    signal_alert_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), ForeignKey("signal_alerts.id"), nullable=True)

    status: Mapped[str] = mapped_column(String(20), default="open")  # open|closed|expired

    entry_price: Mapped[float] = mapped_column(Float)
    entry_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    simulated_entry_delay_seconds: Mapped[int] = mapped_column(Integer, default=0)
    simulated_slippage_pct: Mapped[float] = mapped_column(Float, default=0.0)
    simulated_fees_pct: Mapped[float] = mapped_column(Float, default=0.0)  # DEX fee + gas, combined estimate

    stop_loss_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    take_profit_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_holding_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    exit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    exit_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    exit_reason: Mapped[str | None] = mapped_column(String(30), nullable=True)  # stop_loss|take_profit|time_limit|manual

    position_size_usd: Mapped[float] = mapped_column(Float, default=100.0)
    realized_return_pct: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
