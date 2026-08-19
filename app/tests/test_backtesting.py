from app.backtesting.framework import Checkpoint, HistoricalCase, evaluate_case, train_test_split
from app.scoring.engine import ScoringInput


def _weak_input():
    return ScoringInput(security_passed_minimum=True)


def _strong_input():
    return ScoringInput(
        price_change_1h_pct=40,
        volume_accel_ratio=4,
        buy_sell_imbalance=0.5,
        unique_buyers_1h=30,
        liquidity_usd=60_000,
        known_profitable_wallets_buying=3,
        security_passed_minimum=True,
    )


def test_synthetic_runner_case_triggers_alert_before_move():
    case = HistoricalCase(
        label="SYNTHETIC-RUNNER-01",
        outcome="runner",
        max_drawdown_pct=15.0,
        checkpoints=[
            Checkpoint(minutes_before_move=60, scoring_input=_weak_input()),
            Checkpoint(minutes_before_move=30, scoring_input=_strong_input()),
            Checkpoint(minutes_before_move=10, scoring_input=_strong_input()),
        ],
    )
    result = evaluate_case(case, threshold=55)
    assert result.would_have_alerted is True
    assert result.earliest_alert_minutes_before_move == 30


def test_synthetic_flat_case_never_alerts():
    case = HistoricalCase(
        label="SYNTHETIC-FLAT-01",
        outcome="flat",
        max_drawdown_pct=5.0,
        checkpoints=[
            Checkpoint(minutes_before_move=30, scoring_input=_weak_input()),
            Checkpoint(minutes_before_move=10, scoring_input=_weak_input()),
        ],
    )
    result = evaluate_case(case, threshold=55)
    assert result.would_have_alerted is False


def test_train_test_split_is_time_ordered_not_shuffled():
    cases = [
        HistoricalCase(label=f"CASE-{i}", outcome="flat", max_drawdown_pct=None, checkpoints=[])
        for i in range(10)
    ]
    train, test = train_test_split(cases, split_index=7)
    assert [c.label for c in train] == [f"CASE-{i}" for i in range(7)]
    assert [c.label for c in test] == [f"CASE-{i}" for i in range(7, 10)]
