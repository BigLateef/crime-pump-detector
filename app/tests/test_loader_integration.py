"""
Integration tests for app.backtesting.loader.load_cases() against a real
async database session — these exercise the actual SQL grouping,
leakage-guard, and require_verified logic that test_loader.py's pure-
function tests deliberately bypass.

NOT EXECUTED in this sandbox: they need sqlalchemy + asyncpg (or
aiosqlite) installed, and a real database to run migrations against,
neither of which is available offline here. Syntax-checked only via
`python3 -m py_compile`. Run these for real the first time this project
is picked up somewhere with network access — see README.md Quick Start.

Fixtures assume a `db_session` pytest fixture providing a real
AsyncSession against a throwaway test database, which does not exist yet
in this project (conftest.py needs to be added alongside real DB access
— documented as a remaining gap in this phase's final report).
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.backtesting.loader import DatasetIntegrityError, load_cases
from app.models.historical_snapshot import HistoricalDataset, HistoricalSnapshot

MOVE_TS = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _make_snapshot(dataset_id, chain, address, symbol, outcome, minutes_before, data_quality="VERIFIED", split="test", **overrides):
    defaults = dict(
        dataset_id=dataset_id,
        chain=chain,
        token_address=address,
        symbol=symbol,
        snapshot_timestamp=MOVE_TS - timedelta(minutes=minutes_before),
        minutes_before_major_move=minutes_before,
        price=0.0001,
        volume_1h=10000,
        source="test fixture",
        data_quality=data_quality,
        outcome=outcome,
        major_move_timestamp=MOVE_TS,
        dataset_split=split,
    )
    defaults.update(overrides)
    return HistoricalSnapshot(**defaults)


@pytest.mark.asyncio
async def test_load_cases_groups_multiple_tokens_separately(db_session):
    dataset = HistoricalDataset(name="test", data_quality="VERIFIED", uploaded_by="admin-1")
    db_session.add(dataset)
    await db_session.flush()

    db_session.add(_make_snapshot(dataset.id, "solana", "addrA", "TOKA", "runner", 60))
    db_session.add(_make_snapshot(dataset.id, "solana", "addrB", "TOKB", "flat", 60))
    await db_session.commit()

    cases = await load_cases(db_session, dataset_ids=[dataset.id], split="test")
    assert len(cases) == 2
    outcomes = {c.outcome for c in cases}
    assert outcomes == {"runner", "flat"}


@pytest.mark.asyncio
async def test_load_cases_separates_multiple_datasets(db_session):
    ds1 = HistoricalDataset(name="ds1", data_quality="VERIFIED", uploaded_by="admin-1")
    ds2 = HistoricalDataset(name="ds2", data_quality="VERIFIED", uploaded_by="admin-1")
    db_session.add_all([ds1, ds2])
    await db_session.flush()

    db_session.add(_make_snapshot(ds1.id, "solana", "addrA", "TOKA", "runner", 60))
    db_session.add(_make_snapshot(ds2.id, "solana", "addrA", "TOKA", "runner", 60))  # same token, different dataset
    await db_session.commit()

    cases_ds1_only = await load_cases(db_session, dataset_ids=[ds1.id], split="test")
    assert len(cases_ds1_only) == 1

    cases_both = await load_cases(db_session, dataset_ids=[ds1.id, ds2.id], split="test")
    assert len(cases_both) == 2  # not merged into one, per the dataset_id-inclusive grouping key


@pytest.mark.asyncio
async def test_load_cases_rejects_demo_data_by_default(db_session):
    dataset = HistoricalDataset(name="demo-ds", data_quality="DEMO", uploaded_by="admin-1")
    db_session.add(dataset)
    await db_session.flush()
    db_session.add(_make_snapshot(dataset.id, "solana", "addrA", "TOKA", "runner", 60, data_quality="DEMO"))
    await db_session.commit()

    with pytest.raises(DatasetIntegrityError):
        await load_cases(db_session, dataset_ids=[dataset.id], split="test", require_verified=True)

    # Explicit opt-out works.
    cases = await load_cases(db_session, dataset_ids=[dataset.id], split="test", require_verified=False)
    assert len(cases) == 1


@pytest.mark.asyncio
async def test_load_cases_rejects_future_data_leakage(db_session):
    dataset = HistoricalDataset(name="leaky-ds", data_quality="VERIFIED", uploaded_by="admin-1")
    db_session.add(dataset)
    await db_session.flush()
    # snapshot AFTER the move — this should never happen post-validation,
    # but the loader re-checks it as a last line of defense.
    bad_snap = _make_snapshot(dataset.id, "solana", "addrA", "TOKA", "runner", -30)
    bad_snap.snapshot_timestamp = MOVE_TS + timedelta(minutes=30)
    db_session.add(bad_snap)
    await db_session.commit()

    with pytest.raises(DatasetIntegrityError, match="leak"):
        await load_cases(db_session, dataset_ids=[dataset.id], split="test")


@pytest.mark.asyncio
async def test_load_cases_reports_missing_checkpoints_without_raising_by_default(db_session):
    dataset = HistoricalDataset(name="partial-ds", data_quality="VERIFIED", uploaded_by="admin-1")
    db_session.add(dataset)
    await db_session.flush()
    # Only 2 of the 7 required offsets present.
    db_session.add(_make_snapshot(dataset.id, "solana", "addrA", "TOKA", "runner", 1440))
    db_session.add(_make_snapshot(dataset.id, "solana", "addrA", "TOKA", "runner", 60))
    await db_session.commit()

    cases = await load_cases(db_session, dataset_ids=[dataset.id], split="test")
    assert len(cases) == 1
    assert set(cases[0].missing_checkpoints) == {720, 360, 180, 30, 10}


@pytest.mark.asyncio
async def test_load_cases_raises_when_complete_checkpoints_required(db_session):
    dataset = HistoricalDataset(name="partial-ds-2", data_quality="VERIFIED", uploaded_by="admin-1")
    db_session.add(dataset)
    await db_session.flush()
    db_session.add(_make_snapshot(dataset.id, "solana", "addrA", "TOKA", "runner", 60))
    await db_session.commit()

    with pytest.raises(DatasetIntegrityError, match="missing"):
        await load_cases(db_session, dataset_ids=[dataset.id], split="test", require_complete_checkpoints=True)


@pytest.mark.asyncio
async def test_load_cases_covers_failed_and_flat_outcomes(db_session):
    dataset = HistoricalDataset(name="mixed-outcomes", data_quality="VERIFIED", uploaded_by="admin-1")
    db_session.add(dataset)
    await db_session.flush()
    db_session.add(_make_snapshot(dataset.id, "solana", "addrA", "TOKA", "failed", 60))
    db_session.add(_make_snapshot(dataset.id, "solana", "addrB", "TOKB", "flat", 60))
    db_session.add(_make_snapshot(dataset.id, "solana", "addrC", "TOKC", "rugged", 60))
    await db_session.commit()

    cases = await load_cases(db_session, dataset_ids=[dataset.id], split="test")
    outcomes = sorted(c.outcome for c in cases)
    assert outcomes == ["failed", "flat", "rugged"]
