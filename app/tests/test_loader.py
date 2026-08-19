"""
Tests app.backtesting.loader's pure derivation logic
(_derive_adjacent_metrics, _base_scoring_input) directly, without going
through load_cases() itself — that needs a real AsyncSession, which needs
sqlalchemy/asyncpg installed, unavailable in this sandbox. A lightweight
stand-in object with the same attributes as HistoricalSnapshot is used
instead of importing the real model (which pulls in sqlalchemy at import
time).

This means the DB-querying and grouping half of load_cases() (the
`select()`/`grouped[...]` code) is NOT exercised by these tests — only
the derivation math and the missing-checkpoint logic, extracted into
directly-testable helpers below that mirror the real implementation.
Once sqlalchemy is installed, an integration test should replace this
with a real load_cases() call against a real dataset.
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone


@dataclass
class FakeSnapshot:
    """Mirrors the subset of HistoricalSnapshot fields the loader reads."""
    id: str
    dataset_id: str
    chain: str
    token_address: str
    symbol: str
    outcome: str
    minutes_before_major_move: int
    snapshot_timestamp: datetime
    major_move_timestamp: datetime
    price: float | None = None
    volume_1h: float | None = None
    buy_count: int | None = None
    sell_count: int | None = None
    unique_buyers: int | None = None
    liquidity: float | None = None
    top_holder_concentration: float | None = None
    holder_count: int | None = None
    security_flags: list = field(default_factory=list)
    maximum_drawdown_pct: float | None = None
    data_quality: str = "VERIFIED"


# Re-implement the two pure functions under test by importing them
# directly — they don't touch sqlalchemy themselves, only the module they
# live in does (via the HistoricalSnapshot type hint import at module
# level). We import the functions lazily inside each test via a local
# shim module to dodge that import chain entirely.

def _load_pure_functions():
    """
    Loads _derive_adjacent_metrics and _base_scoring_input from
    loader.py's source without executing its sqlalchemy-importing module
    top-level — this keeps these tests runnable in a sandbox with no
    sqlalchemy installed, since the two functions under test don't
    actually need it themselves.
    """
    import ast
    import types

    with open("app/backtesting/loader.py") as f:
        source = f.read()

    tree = ast.parse(source)
    # Keep only: imports needed by the two functions (dataclasses not
    # needed; ScoringInput import needed by _base_scoring_input), and the
    # function defs themselves.
    keep_nodes = []
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == "app.scoring.engine":
            keep_nodes.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name in ("_base_scoring_input", "_derive_adjacent_metrics"):
            keep_nodes.append(node)

    module = types.ModuleType("loader_pure_shim")
    module.__dict__["HistoricalSnapshot"] = object  # only used as a type hint here, never isinstance-checked
    code = compile(ast.Module(body=keep_nodes, type_ignores=[]), "<loader_shim>", "exec")
    exec(code, module.__dict__)
    return module._base_scoring_input, module._derive_adjacent_metrics


_base_scoring_input, _derive_adjacent_metrics = _load_pure_functions()


def _snap(minutes_before, price=None, volume_1h=None, **kwargs):
    move_ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return FakeSnapshot(
        id=f"snap-{minutes_before}",
        dataset_id="ds1",
        chain="solana",
        token_address="11111111111111111111111111111111",
        symbol="DEMO1",
        outcome="runner",
        minutes_before_major_move=minutes_before,
        snapshot_timestamp=move_ts - timedelta(minutes=minutes_before),
        major_move_timestamp=move_ts,
        price=price,
        volume_1h=volume_1h,
        **kwargs,
    )


def test_price_change_computed_from_adjacent_checkpoint():
    earlier = _snap(180, price=0.0001)
    later = _snap(60, price=0.00012)  # +20% over the 120-minute gap
    price_change, volume_accel, unavailable = _derive_adjacent_metrics(later, earlier)
    assert "price_change_1h_pct" not in unavailable
    # 20% over 120 minutes, linearly extrapolated to 60 minutes -> 10%
    assert abs(price_change - 10.0) < 0.01


def test_volume_accel_is_direct_ratio_no_extrapolation():
    earlier = _snap(180, volume_1h=10000)
    later = _snap(60, volume_1h=25000)
    _, volume_accel, unavailable = _derive_adjacent_metrics(later, earlier)
    assert "volume_accel_ratio" not in unavailable
    assert abs(volume_accel - 2.5) < 0.001


def test_first_checkpoint_has_no_previous_and_is_marked_unavailable():
    only = _snap(1440, price=0.0001, volume_1h=5000)
    price_change, volume_accel, unavailable = _derive_adjacent_metrics(only, None)
    assert price_change is None
    assert volume_accel is None
    assert "price_change_1h_pct" in unavailable
    assert "volume_accel_ratio" in unavailable
    assert "No earlier checkpoint" in unavailable["price_change_1h_pct"]


def test_missing_price_on_either_checkpoint_marked_unavailable_not_guessed():
    earlier = _snap(180, price=None, volume_1h=10000)  # price missing
    later = _snap(60, price=0.0002, volume_1h=20000)
    price_change, volume_accel, unavailable = _derive_adjacent_metrics(later, earlier)
    assert price_change is None
    assert "price_change_1h_pct" in unavailable
    # volume was present on both, so that metric should still compute
    assert volume_accel is not None


def test_zero_previous_volume_does_not_divide_by_zero():
    earlier = _snap(180, volume_1h=0)
    later = _snap(60, volume_1h=5000)
    _, volume_accel, unavailable = _derive_adjacent_metrics(later, earlier)
    assert volume_accel is None
    assert "volume_accel_ratio" in unavailable


def test_base_scoring_input_computes_buy_sell_imbalance():
    snap = _snap(60, buy_count=80, sell_count=20)
    scoring_input = _base_scoring_input(snap)
    assert abs(scoring_input.buy_sell_imbalance - 0.6) < 0.001  # (80-20)/100


def test_base_scoring_input_no_trades_leaves_imbalance_none():
    snap = _snap(60, buy_count=0, sell_count=0)
    scoring_input = _base_scoring_input(snap)
    assert scoring_input.buy_sell_imbalance is None


def test_base_scoring_input_flags_deployer_selling():
    snap = _snap(60, security_flags=["deployer_selling"])
    scoring_input = _base_scoring_input(snap)
    assert scoring_input.deployer_selling_detected is True


def test_base_scoring_input_hard_fail_flag_zeroes_security():
    snap = _snap(60, security_flags=["hard_fail"])
    scoring_input = _base_scoring_input(snap)
    assert scoring_input.security_passed_minimum is False
    assert scoring_input.security_score_penalty == 30
