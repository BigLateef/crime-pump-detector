from app.security.rules import evaluate_security


def test_missing_data_fails_closed():
    result = evaluate_security(None)
    assert result.passed_minimum_requirements is False
    assert result.score_penalty == 30


def test_honeypot_is_hard_fail():
    result = evaluate_security({"is_honeypot": "1"})
    assert result.passed_minimum_requirements is False
    assert result.score_penalty == 30
    assert any("Honeypot" in w for w in result.warnings)


def test_clean_token_passes_with_no_penalty():
    result = evaluate_security(
        {
            "is_honeypot": "0",
            "is_mintable": "0",
            "buy_tax": "0",
            "sell_tax": "0",
            "lp_holders": [{"percent": "0.9", "is_locked": 1}],
            "holder_percent_top10": "0.2",
        }
    )
    assert result.passed_minimum_requirements is True
    assert result.score_penalty == 0


def test_high_tax_penalized_but_not_hard_fail():
    result = evaluate_security(
        {
            "is_honeypot": "0",
            "buy_tax": "0.15",
            "sell_tax": "0.15",
            "lp_holders": [{"percent": "0.9", "is_locked": 1}],
            "holder_percent_top10": "0.1",
        }
    )
    assert result.passed_minimum_requirements is True
    assert result.score_penalty > 0


def test_unlocked_liquidity_penalized():
    result = evaluate_security(
        {
            "is_honeypot": "0",
            "lp_holders": [{"percent": "1.0", "is_locked": 0}],
            "holder_percent_top10": "0.1",
        }
    )
    assert result.passed_minimum_requirements is True
    assert result.score_penalty >= 15
