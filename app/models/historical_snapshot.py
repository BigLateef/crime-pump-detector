"""
Historical snapshot storage for real backtesting (Section 8/9 of the
original spec). Two tables:

- HistoricalDataset: one row per imported file (CSV/JSON), tracking
  import status, quality, and — critically — whether it's VERIFIED,
  DEMO, ESTIMATED, or UNAVAILABLE-flagged data. Demo and verified data
  are never queried together for a "real" backtest result.
- HistoricalSnapshot: one row per (token, minutes_before_major_move)
  data point, belonging to a dataset.
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.user import gen_uuid

# Only these four values are valid for HistoricalDataset.data_quality /
# HistoricalSnapshot.data_quality — enforced in app/backtesting/validation.py,
# not just documented here.
DATA_QUALITY_VALUES = ("VERIFIED", "DEMO", "ESTIMATED", "UNAVAILABLE")

OUTCOME_TYPES = ("runner", "failed", "flat", "dumped", "rugged", "fake_volume")

DATASET_SPLITS = ("train", "test", "unassigned")


class HistoricalDataset(Base):
    __tablename__ = "historical_datasets"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    data_quality: Mapped[str] = mapped_column(String(20), nullable=False)  # one of DATA_QUALITY_VALUES
    uploaded_by: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("users.id"))
    source_filename: Mapped[str | None] = mapped_column(String(300), nullable=True)
    importer_version: Mapped[str] = mapped_column(String(20), default="1.0.0")

    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|validated|imported|failed
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    valid_row_count: Mapped[int] = mapped_column(Integer, default=0)
    error_row_count: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_row_count: Mapped[int] = mapped_column(Integer, default=0)
    validation_errors: Mapped[list] = mapped_column(JSON, default=list)  # list of {row, field, message}

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    imported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class HistoricalSnapshot(Base):
    __tablename__ = "historical_snapshots"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    dataset_id: Mapped[str] = mapped_column(UUID(as_uuid=False), ForeignKey("historical_datasets.id"), index=True)

    token_address: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    chain: Mapped[str] = mapped_column(String(30), nullable=False)
    symbol: Mapped[str] = mapped_column(String(30), nullable=True)

    snapshot_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)  # UTC
    minutes_before_major_move: Mapped[int] = mapped_column(Integer, nullable=False)

    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    market_cap: Mapped[float | None] = mapped_column(Float, nullable=True)
    liquidity: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume_1m: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume_5m: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume_15m: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume_1h: Mapped[float | None] = mapped_column(Float, nullable=True)
    buy_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sell_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    unique_buyers: Mapped[int | None] = mapped_column(Integer, nullable=True)
    unique_sellers: Mapped[int | None] = mapped_column(Integer, nullable=True)
    holder_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    top_holder_concentration: Mapped[float | None] = mapped_column(Float, nullable=True)  # 0..1
    deployer_balance: Mapped[float | None] = mapped_column(Float, nullable=True)  # % of supply, 0..1
    security_flags: Mapped[list] = mapped_column(JSON, default=list)  # e.g. ["is_mintable","high_tax"]

    source: Mapped[str] = mapped_column(String(200), nullable=False)  # required for every VERIFIED record
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    data_quality: Mapped[str] = mapped_column(String(20), nullable=False)  # one of DATA_QUALITY_VALUES
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    # Case-level fields (repeated per snapshot row for query simplicity —
    # every row for the same token_address+chain+outcome shares these)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)  # one of OUTCOME_TYPES
    major_move_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)  # UTC
    maximum_drawdown_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    maximum_gain_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    dataset_split: Mapped[str] = mapped_column(String(20), default="unassigned")  # one of DATASET_SPLITS

    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
