"""
Transparent scoring engine (Section 10). Every point is attributable to a
named reason — no black-box weighting. Deterministic and cheap: this is
the "first-stage filter" that Section 13 requires AI analysis to happen
only after passing.

Positive scoring (max 90):
  on-chain momentum          25
  quality of new buyers      15
  liquidity/execution        15
  smart-money confirmation   15
  narrative/social           10
  holder distribution        10

Negative scoring (subtracted after positives, floor 0):
  contract risk               up to 30  (from security.rules.evaluate_security)
  manipulation/wash trading   up to 30
  insider/deployer risk       up to 30
"""
from dataclasses import dataclass, field

SIGNAL_LEVELS = ("AVOID", "WATCH", "EARLY", "HIGH-CONVICTION", "EXIT_DANGER")


@dataclass
class ScoringInput:
    # Momentum (Section 5) — precomputed by the caller from token_metrics
    # history. None fields simply score 0 for that component rather than
    # erroring, since not every timeframe will have data for a brand-new
    # token.
    price_change_1h_pct: float | None = None
    volume_accel_ratio: float | None = None  # current-hour vol / prior-hour vol
    buy_sell_imbalance: float | None = None  # (buys - sells) / (buys + sells), -1..1
    unique_buyers_1h: int | None = None
    volume_to_liquidity_ratio: float | None = None

    # Buyer quality / smart money
    known_profitable_wallets_buying: int = 0
    fresh_wallet_pct: float | None = None  # 0..1, high = more red flag than green

    # Liquidity / execution
    liquidity_usd: float | None = None
    slippage_pct_at_500usd: float | None = None

    # Narrative/social — only populated when ENABLE_SOCIAL_ANALYSIS=true
    social_mention_accel_ratio: float | None = None

    # Holder distribution
    top10_holder_pct: float | None = None
    holder_count: int | None = None

    # Manipulation / insider signals
    wash_trading_suspected: bool = False
    bundled_insider_buys_detected: bool = False
    deployer_selling_detected: bool = False

    # From security.rules.evaluate_security
    security_score_penalty: int = 0
    security_passed_minimum: bool = True


@dataclass
class ScoreBreakdown:
    total: int
    signal_level: str
    confidence: str
    components: list[str] = field(default_factory=list)  # human-readable "+N: reason" / "-N: reason"


def score_token(inp: ScoringInput) -> ScoreBreakdown:
    components: list[str] = []
    total = 0

    # --- On-chain momentum (25) ---
    momentum_pts = 0
    if inp.price_change_1h_pct is not None and inp.price_change_1h_pct > 20:
        momentum_pts += 10
        components.append(f"+10: 1h price change {inp.price_change_1h_pct:.0f}%")
    if inp.volume_accel_ratio is not None and inp.volume_accel_ratio > 2:
        momentum_pts += 10
        components.append(f"+10: volume accelerating {inp.volume_accel_ratio:.1f}x hour-over-hour")
    if inp.buy_sell_imbalance is not None and inp.buy_sell_imbalance > 0.2:
        momentum_pts += 5
        components.append(f"+5: buy/sell imbalance {inp.buy_sell_imbalance:+.2f} favors buyers")
    momentum_pts = min(momentum_pts, 25)
    total += momentum_pts

    # --- Quality of new buyers (15) ---
    buyer_pts = 0
    if inp.unique_buyers_1h is not None and inp.unique_buyers_1h >= 10:
        buyer_pts += 8
        components.append(f"+8: {inp.unique_buyers_1h} unique buyers in the last hour")
    if inp.fresh_wallet_pct is not None and inp.fresh_wallet_pct < 0.6:
        buyer_pts += 7
        components.append(f"+7: fresh-wallet share is only {inp.fresh_wallet_pct:.0%} (diverse buyers)")
    buyer_pts = min(buyer_pts, 15)
    total += buyer_pts

    # --- Liquidity / execution quality (15) ---
    liq_pts = 0
    if inp.liquidity_usd is not None and inp.liquidity_usd >= 20_000:
        liq_pts += 8
        components.append(f"+8: liquidity ${inp.liquidity_usd:,.0f} clears the $20k floor")
    if inp.slippage_pct_at_500usd is not None and inp.slippage_pct_at_500usd < 3:
        liq_pts += 7
        components.append(f"+7: est. slippage {inp.slippage_pct_at_500usd:.1f}% on a $500 trade")
    liq_pts = min(liq_pts, 15)
    total += liq_pts

    # --- Smart-money confirmation (15) ---
    sm_pts = 0
    if inp.known_profitable_wallets_buying >= 2:
        sm_pts = 15
        components.append(f"+15: {inp.known_profitable_wallets_buying} independent early wallets confirmed")
    elif inp.known_profitable_wallets_buying == 1:
        sm_pts = 7
        components.append("+7: one early wallet confirmed (needs a second for full confirmation)")
    total += sm_pts

    # --- Narrative/social (10) ---
    social_pts = 0
    if inp.social_mention_accel_ratio is not None and inp.social_mention_accel_ratio > 3:
        social_pts = 10
        components.append(f"+10: social mentions accelerating {inp.social_mention_accel_ratio:.1f}x")
    total += social_pts

    # --- Holder distribution / supply safety (10) ---
    holder_pts = 0
    if inp.top10_holder_pct is not None and inp.top10_holder_pct < 0.35:
        holder_pts += 5
        components.append(f"+5: top 10 holders control only {inp.top10_holder_pct:.0%}")
    if inp.holder_count is not None and inp.holder_count >= 100:
        holder_pts += 5
        components.append(f"+5: {inp.holder_count} holders")
    holder_pts = min(holder_pts, 10)
    total += holder_pts

    # --- Negative scoring ---
    if inp.security_score_penalty > 0:
        components.append(f"-{inp.security_score_penalty}: contract risk (security scan)")
        total -= inp.security_score_penalty

    manipulation_penalty = 0
    if inp.wash_trading_suspected:
        manipulation_penalty += 20
        components.append("-20: wash trading suspected")
    if inp.bundled_insider_buys_detected:
        manipulation_penalty += 10
        components.append("-10: bundled insider buys detected")
    manipulation_penalty = min(manipulation_penalty, 30)
    total -= manipulation_penalty

    insider_penalty = 0
    if inp.deployer_selling_detected:
        insider_penalty = 30
        components.append("-30: deployer-linked selling detected")
    total -= insider_penalty

    total = max(0, min(100, total))

    # --- Signal level ---
    if not inp.security_passed_minimum or inp.deployer_selling_detected:
        level = "EXIT_DANGER" if inp.deployer_selling_detected else "AVOID"
    elif total >= 75:
        level = "HIGH-CONVICTION"
    elif total >= 55:
        level = "EARLY"
    elif total >= 35:
        level = "WATCH"
    else:
        level = "AVOID"

    # --- Confidence: how many independent categories actually confirmed ---
    confirming_categories = sum(
        [
            momentum_pts > 0,
            buyer_pts > 0,
            sm_pts > 0,
            liq_pts > 0,
            social_pts > 0,
            holder_pts > 0,
        ]
    )
    if confirming_categories >= 4:
        confidence = "high"
    elif confirming_categories >= 2:
        confidence = "medium"
    else:
        confidence = "low"

    return ScoreBreakdown(total=total, signal_level=level, confidence=confidence, components=components)


def should_alert(breakdown: ScoreBreakdown, threshold: int, confirming_categories: int) -> bool:
    """
    Gate from Section 10: alert only when the score crosses threshold AND
    at least two independent categories confirmed. Duplicate suppression
    and liquidity-vs-position-size checks happen at the worker level
    (Section 12/13), not here, since they need live cooldown/liquidity
    state this pure function doesn't have.
    """
    return breakdown.total >= threshold and confirming_categories >= 2 and breakdown.signal_level not in (
        "AVOID",
    )
