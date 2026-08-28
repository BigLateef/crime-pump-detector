from app.scoring.engine import ScoringInput, score_token


def test_strong_signal_scores_high_conviction():
    inp = ScoringInput(
        price_change_1h_pct=35,
        volume_accel_ratio=3.5,
        buy_sell_imbalance=0.4,
        unique_buyers_1h=25,
        fresh_wallet_pct=0.3,
        liquidity_usd=50_000,
        slippage_pct_at_500usd=1.2,
        known_profitable_wallets_buying=3,
        top10_holder_pct=0.2,
        holder_count=300,
        security_score_penalty=0,
        security_passed_minimum=True,
    )
    result = score_token(inp)
    assert result.total >= 75
    assert result.signal_level == "HIGH-CONVICTION"
    assert result.confidence == "high"
    assert any(c.startswith("+") for c in result.components)


def test_weak_signal_scores_avoid():
    inp = ScoringInput(security_score_penalty=0, security_passed_minimum=True)
    result = score_token(inp)
    assert result.total < 35
    assert result.signal_level == "AVOID"


def test_hard_security_fail_forces_avoid_regardless_of_momentum():
    inp = ScoringInput(
        price_change_1h_pct=100,
        volume_accel_ratio=10,
        known_profitable_wallets_buying=5,
        security_score_penalty=30,
        security_passed_minimum=False,
    )
    result = score_token(inp)
    assert result.signal_level == "AVOID"


def test_deployer_selling_forces_exit_danger():
    inp = ScoringInput(
        price_change_1h_pct=50,
        security_passed_minimum=True,
        deployer_selling_detected=True,
    )
    result = score_token(inp)
    assert result.signal_level == "EXIT_DANGER"


def test_score_never_exceeds_100_or_drops_below_0():
    inp = ScoringInput(
        price_change_1h_pct=1000,
        volume_accel_ratio=100,
        buy_sell_imbalance=1,
        unique_buyers_1h=1000,
        fresh_wallet_pct=0,
        liquidity_usd=10_000_000,
        slippage_pct_at_500usd=0,
        known_profitable_wallets_buying=10,
        social_mention_accel_ratio=50,
        top10_holder_pct=0,
        holder_count=100_000,
    )
    result = score_token(inp)
    assert 0 <= result.total <= 100
