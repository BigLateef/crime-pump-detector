"""
Paper trading simulation. Every number here is a documented assumption,
not a real fill — the point of Section 14 is realistic friction, not a
frictionless backtest.
"""
from dataclasses import dataclass

# Conservative default assumptions — deliberately not tuned to make the
# strategy look good. Override per-chain when real fee data is wired in.
DEFAULT_ENTRY_DELAY_SECONDS = 12  # time between alert and a human acting on it
DEFAULT_SLIPPAGE_PCT = 2.5
DEFAULT_DEX_FEE_PCT = 0.3
DEFAULT_GAS_FEE_PCT = 0.5  # expressed as % of position size, chain-dependent in reality


@dataclass
class SimulatedEntry:
    effective_entry_price: float
    total_friction_pct: float


def simulate_entry(alert_price: float) -> SimulatedEntry:
    friction_pct = DEFAULT_SLIPPAGE_PCT + DEFAULT_DEX_FEE_PCT + DEFAULT_GAS_FEE_PCT
    effective_price = alert_price * (1 + friction_pct / 100)
    return SimulatedEntry(effective_entry_price=effective_price, total_friction_pct=friction_pct)


def evaluate_exit(
    entry_price: float,
    current_price: float,
    stop_loss_pct: float | None,
    take_profit_pct: float | None,
    minutes_held: int,
    max_holding_minutes: int | None,
) -> tuple[bool, str | None]:
    """Returns (should_exit, reason)."""
    change_pct = (current_price - entry_price) / entry_price * 100

    if stop_loss_pct is not None and change_pct <= -abs(stop_loss_pct):
        return True, "stop_loss"
    if take_profit_pct is not None and change_pct >= abs(take_profit_pct):
        return True, "take_profit"
    if max_holding_minutes is not None and minutes_held >= max_holding_minutes:
        return True, "time_limit"
    return False, None


def realized_return_pct(entry_price: float, exit_price: float, exit_fee_pct: float = DEFAULT_DEX_FEE_PCT) -> float:
    gross_pct = (exit_price - entry_price) / entry_price * 100
    return gross_pct - exit_fee_pct
