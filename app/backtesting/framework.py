"""
Backtesting framework (Section 9).

IMPORTANT — read before using: this module provides the *methodology* and
evaluation machinery only. It does not contain researched data about
$COAI, $SIREN, $M, $LAB, or any other real token. Populating
HistoricalCase records with real reconstructed snapshots (24h/12h/6h/3h/1h/
30m/10m before each token's actual move) requires pulling real historical
on-chain and social data — something this sandbox cannot do (no network
access) and something that must not be fabricated. Treat every
HistoricalCase in tests/fixtures as synthetic unless a data pipeline has
actually populated it from a real source.

Bias controls implemented here per spec:
- train_test_split(): time-ordered split, never random shuffle — prevents
  the model from training on data that's chronologically after test data
- No function in this module accepts "future" data relative to the
  evaluation timestamp it's given — each HistoricalCase's checkpoints are
  strictly pre-move
- evaluate_against_baseline() always runs a naive baseline (e.g. "alert on
  every token above $20k liquidity") alongside the scoring engine so the
  model's lift over doing nothing clever is visible, not assumed
"""
from dataclasses import dataclass, field

from app.scoring.engine import ScoringInput, score_token


@dataclass
class Checkpoint:
    """One reconstructed snapshot at a fixed offset before the move."""
    minutes_before_move: int
    scoring_input: ScoringInput
    # Explains any derived metric (e.g. price_change_1h_pct) that could NOT
    # be computed for this checkpoint and why — e.g. "no adjacent earlier
    # checkpoint available". Empty when every derivable metric was
    # actually derived. Populated by app.backtesting.loader, not guessed.
    unavailable_metrics: dict[str, str] = field(default_factory=dict)


@dataclass
class HistoricalCase:
    label: str  # e.g. "SYNTHETIC-RUNNER-01" — never a real ticker unless backed by real data
    outcome: str  # "runner" | "failed" | "flat" | "dumped" | "rugged" | "fake_volume"
    max_drawdown_pct: float | None
    checkpoints: list[Checkpoint] = field(default_factory=list)
    # Case-level reasons this case is missing checkpoints entirely (e.g.
    # "no snapshot at 30 minutes before move") — distinct from a
    # per-checkpoint unavailable_metrics gap.
    missing_checkpoints: list[int] = field(default_factory=list)


@dataclass
class CaseEvaluation:
    label: str
    outcome: str
    would_have_alerted: bool
    earliest_alert_minutes_before_move: int | None
    scores_by_checkpoint: dict[int, int]


def evaluate_case(case: HistoricalCase, threshold: int = 55) -> CaseEvaluation:
    scores_by_checkpoint: dict[int, int] = {}
    earliest_alert: int | None = None

    # Iterate from furthest-out checkpoint to closest, so "earliest" alert
    # really is the earliest — never peek at a later (closer-to-move)
    # checkpoint when evaluating an earlier one.
    for cp in sorted(case.checkpoints, key=lambda c: -c.minutes_before_move):
        breakdown = score_token(cp.scoring_input)
        scores_by_checkpoint[cp.minutes_before_move] = breakdown.total
        if breakdown.total >= threshold and earliest_alert is None:
            earliest_alert = cp.minutes_before_move

    return CaseEvaluation(
        label=case.label,
        outcome=case.outcome,
        would_have_alerted=earliest_alert is not None,
        earliest_alert_minutes_before_move=earliest_alert,
        scores_by_checkpoint=scores_by_checkpoint,
    )


def train_test_split(cases: list[HistoricalCase], split_index: int) -> tuple[list[HistoricalCase], list[HistoricalCase]]:
    """
    Time-ordered split — `cases` must already be sorted chronologically by
    the caller (e.g. by move date). Never shuffles, to avoid leaking
    future-period patterns into the training set.
    """
    return cases[:split_index], cases[split_index:]


def evaluate_against_baseline(
    cases: list[HistoricalCase], threshold: int = 55, baseline_liquidity_floor: float = 20_000
) -> dict:
    """
    Compares the scoring engine's true/false positive rate on `runner`
    cases against a naive baseline (alert on anything above a liquidity
    floor, regardless of any other signal).
    """
    model_hits = 0
    model_false_positives = 0
    baseline_hits = 0
    baseline_false_positives = 0
    total_runners = sum(1 for c in cases if c.outcome == "runner")
    total_non_runners = sum(1 for c in cases if c.outcome != "runner")

    for case in cases:
        evaluation = evaluate_case(case, threshold=threshold)
        if evaluation.would_have_alerted:
            if case.outcome == "runner":
                model_hits += 1
            else:
                model_false_positives += 1

        last_checkpoint = min(case.checkpoints, key=lambda c: c.minutes_before_move, default=None)
        baseline_fires = (
            last_checkpoint is not None
            and (last_checkpoint.scoring_input.liquidity_usd or 0) >= baseline_liquidity_floor
        )
        if baseline_fires:
            if case.outcome == "runner":
                baseline_hits += 1
            else:
                baseline_false_positives += 1

    return {
        "total_cases": len(cases),
        "total_runners": total_runners,
        "total_non_runners": total_non_runners,
        "model": {
            "recall": model_hits / total_runners if total_runners else None,
            "false_positive_count": model_false_positives,
        },
        "baseline": {
            "recall": baseline_hits / total_runners if total_runners else None,
            "false_positive_count": baseline_false_positives,
        },
    }
