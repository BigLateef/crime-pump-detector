"""
Bridges the DB-backed HistoricalSnapshot rows to the pure evaluation
framework in app/backtesting/framework.py (which never touches a
database, by design — that's what makes its no-lookahead guarantees easy
to test).

Hard rules enforced here, not just documented:
- require_verified=True (the default) refuses to load any DEMO/ESTIMATED/
  UNAVAILABLE row — a "real" backtest result can never be built from demo
  data, even by accident.
- split filtering happens at load time (train vs test), never mixed
  unless the caller explicitly asks for split=None (used only for
  displaying raw dataset stats, never for a performance number).
- Cases are grouped by (dataset_id, chain, token_address, outcome) — not
  just (chain, token_address) — so the same token appearing in two
  different datasets, or recorded under two different outcomes, becomes
  two separate cases rather than one merged (and potentially
  contradictory) one.
- price_change_1h_pct and volume_accel_ratio are computed from adjacent
  checkpoints (see _derive_adjacent_metrics below) — never guessed, and
  never left silently None without an explanation attached to the
  checkpoint's `unavailable_metrics`.
"""
from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.backtesting.framework import Checkpoint, HistoricalCase
from app.backtesting.schema import REQUIRED_MINUTES_BEFORE_MOVE
from app.models.historical_snapshot import HistoricalSnapshot
from app.scoring.engine import ScoringInput


class DatasetIntegrityError(Exception):
    pass


def _base_scoring_input(snap: HistoricalSnapshot) -> ScoringInput:
    """Fields derivable from a single snapshot row, independent of any
    adjacent checkpoint."""
    buys, sells = snap.buy_count or 0, snap.sell_count or 0
    imbalance = ((buys - sells) / (buys + sells)) if (buys + sells) > 0 else None

    return ScoringInput(
        buy_sell_imbalance=imbalance,
        unique_buyers_1h=snap.unique_buyers,
        liquidity_usd=snap.liquidity,
        top10_holder_pct=snap.top_holder_concentration,
        holder_count=snap.holder_count,
        deployer_selling_detected="deployer_selling" in (snap.security_flags or []),
        security_score_penalty=30 if (snap.security_flags and "hard_fail" in snap.security_flags) else 0,
        security_passed_minimum="hard_fail" not in (snap.security_flags or []),
    )


def _derive_adjacent_metrics(
    current: HistoricalSnapshot, previous: HistoricalSnapshot | None
) -> tuple[float | None, float | None, dict[str, str]]:
    """
    Computes (price_change_1h_pct, volume_accel_ratio, unavailable_metrics)
    for `current` using the immediately preceding chronological checkpoint
    in the same case, if one exists.

    price_change_1h_pct: the fixed research offsets (24h/12h/6h/3h/1h/30m/
    10m before the move) are never exactly 60 minutes apart from each
    other, so there is no pair of adjacent checkpoints that spans a true
    trailing 60-minute window. Rather than silently mislabel a
    non-1h-window change as a 1h change, this computes the observed
    percent change over the actual elapsed gap and linearly extrapolates
    it to what it would be over 60 minutes (assuming a constant rate
    across that gap). This is a real derived figure from two real data
    points, not a fabricated one — but it IS an extrapolation, and that
    assumption is worth remembering when reading results.

    volume_accel_ratio: current.volume_1h / previous.volume_1h needs no
    extrapolation since volume_1h is already a trailing-1h figure at each
    checkpoint, so a ratio between two checkpoints' volume_1h values is a
    direct, non-extrapolated acceleration measure.
    """
    unavailable: dict[str, str] = {}

    if previous is None:
        unavailable["price_change_1h_pct"] = "No earlier checkpoint in this case to compare against."
        unavailable["volume_accel_ratio"] = "No earlier checkpoint in this case to compare against."
        return None, None, unavailable

    gap_minutes = previous.minutes_before_major_move - current.minutes_before_major_move
    if gap_minutes <= 0:
        # Should be unreachable if checkpoints were sorted correctly by the
        # caller, but fail closed rather than divide by zero or go negative.
        unavailable["price_change_1h_pct"] = "Adjacent checkpoint ordering is invalid (non-positive time gap)."
        unavailable["volume_accel_ratio"] = "Adjacent checkpoint ordering is invalid (non-positive time gap)."
        return None, None, unavailable

    price_change_1h_pct = None
    if current.price is not None and previous.price is not None and previous.price > 0:
        raw_change_pct = (current.price - previous.price) / previous.price * 100
        price_change_1h_pct = raw_change_pct * (60 / gap_minutes)
    else:
        unavailable["price_change_1h_pct"] = (
            f"Missing price on this checkpoint or its adjacent checkpoint "
            f"({previous.minutes_before_major_move}m before move)."
        )

    volume_accel_ratio = None
    if current.volume_1h is not None and previous.volume_1h is not None and previous.volume_1h > 0:
        volume_accel_ratio = current.volume_1h / previous.volume_1h
    else:
        unavailable["volume_accel_ratio"] = (
            f"Missing volume_1h on this checkpoint or its adjacent checkpoint "
            f"({previous.minutes_before_major_move}m before move)."
        )

    return price_change_1h_pct, volume_accel_ratio, unavailable


async def load_cases(
    db: AsyncSession,
    dataset_ids: list[str] | None = None,
    split: str | None = "test",  # "train" | "test" | None (None = all, stats-only use)
    require_verified: bool = True,
    require_complete_checkpoints: bool = False,
) -> list[HistoricalCase]:
    """
    require_complete_checkpoints: when True, raises DatasetIntegrityError
    if any case is missing one of the 7 required offsets
    (REQUIRED_MINUTES_BEFORE_MOVE) rather than silently evaluating a
    partial case. Default False so partial cases still load (with their
    gaps recorded on HistoricalCase.missing_checkpoints) — the API layer
    decides whether a partial case should count.
    """
    stmt = select(HistoricalSnapshot)
    if dataset_ids:
        stmt = stmt.where(HistoricalSnapshot.dataset_id.in_(dataset_ids))
    if split is not None:
        stmt = stmt.where(HistoricalSnapshot.dataset_split == split)

    rows = (await db.execute(stmt)).scalars().all()

    if require_verified:
        non_verified = [r for r in rows if r.data_quality != "VERIFIED"]
        if non_verified:
            raise DatasetIntegrityError(
                f"{len(non_verified)} snapshot(s) are not VERIFIED (found: "
                f"{sorted(set(r.data_quality for r in non_verified))}). "
                "Refusing to build a 'real' backtest case set from demo/estimated/unavailable data. "
                "Pass require_verified=False explicitly if you intend to evaluate demo data only."
            )

    # Leakage guard: every checkpoint's snapshot_timestamp must be strictly
    # before that same row's major_move_timestamp. Already enforced at
    # import time (validation.py), re-checked here since this is the last
    # place before a score gets computed.
    for r in rows:
        ts = r.snapshot_timestamp if r.snapshot_timestamp.tzinfo else r.snapshot_timestamp.replace(tzinfo=timezone.utc)
        move_ts = r.major_move_timestamp if r.major_move_timestamp.tzinfo else r.major_move_timestamp.replace(tzinfo=timezone.utc)
        if ts >= move_ts:
            raise DatasetIntegrityError(
                f"Snapshot {r.id} is not strictly before its major_move_timestamp — "
                "this would leak future data into the evaluation."
            )

    # Group by (dataset_id, chain, token_address, outcome) — see module
    # docstring for why outcome is part of the key.
    grouped: dict[tuple[str, str, str, str], list[HistoricalSnapshot]] = defaultdict(list)
    for r in rows:
        grouped[(r.dataset_id, r.chain, r.token_address, r.outcome)].append(r)

    cases: list[HistoricalCase] = []
    for (dataset_id, chain, address, outcome), snaps in grouped.items():
        # Chronological order: most-minutes-before-move (earliest in time)
        # first, so "previous" in _derive_adjacent_metrics is always the
        # earlier real data point, never a later (leaking) one.
        snaps_sorted = sorted(snaps, key=lambda s: -s.minutes_before_major_move)

        present_offsets = {s.minutes_before_major_move for s in snaps_sorted}
        missing = sorted(set(REQUIRED_MINUTES_BEFORE_MOVE) - present_offsets, reverse=True)

        if require_complete_checkpoints and missing:
            raise DatasetIntegrityError(
                f"Case {chain}:{address} (dataset {dataset_id}, outcome={outcome}) is missing "
                f"required checkpoint(s) at {missing} minutes-before-move — cannot evaluate with "
                f"require_complete_checkpoints=True."
            )

        drawdown = next((s.maximum_drawdown_pct for s in snaps_sorted if s.maximum_drawdown_pct is not None), None)

        checkpoints: list[Checkpoint] = []
        previous: HistoricalSnapshot | None = None
        for snap in snaps_sorted:
            scoring_input = _base_scoring_input(snap)
            price_change_1h_pct, volume_accel_ratio, unavailable = _derive_adjacent_metrics(snap, previous)
            scoring_input.price_change_1h_pct = price_change_1h_pct
            scoring_input.volume_accel_ratio = volume_accel_ratio

            checkpoints.append(
                Checkpoint(
                    minutes_before_move=snap.minutes_before_major_move,
                    scoring_input=scoring_input,
                    unavailable_metrics=unavailable,
                )
            )
            previous = snap

        symbol = snaps_sorted[0].symbol or "?"
        cases.append(
            HistoricalCase(
                label=f"{symbol} ({chain}:{address[:8]}…, {outcome})",
                outcome=outcome,
                max_drawdown_pct=drawdown,
                checkpoints=checkpoints,
                missing_checkpoints=missing,
            )
        )

    return cases
