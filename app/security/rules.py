"""
Deterministic, rule-based security filtering (Section 8). Runs before any
AI analysis or scoring, on every token that passes initial discovery — per
Section 13, first-stage filtering must be deterministic and cheap.

Input is the raw dict shape returned by GoPlus's token_security API
(see adapters/goplus.py). Each field is documented at
https://docs.gopluslabs.io/reference/token-security-api — this module
does not invent fields not present in that API.
"""
from dataclasses import dataclass, field


@dataclass
class SecurityResult:
    passed_minimum_requirements: bool
    score_penalty: int  # 0-30, subtracted from the overall signal score
    warnings: list[str] = field(default_factory=list)


# Any one of these is an automatic fail — no amount of positive momentum
# offsets a live honeypot or unlimited mint authority.
_HARD_FAIL_FLAGS = {
    "is_honeypot": "Honeypot: token cannot be sold.",
    "cannot_sell_all": "Cannot sell full balance.",
    "trading_cooldown": "Trading cooldown / pause control detected.",
    "is_blacklisted": "Blacklist function present.",
    "is_whitelisted": "Whitelist-restricted trading.",
    "transfer_pausable": "Trading pause control present.",
    "hidden_owner": "Hidden owner privileges detected.",
}

# Each present flag subtracts points but isn't an automatic fail.
_SOFT_PENALTY_FLAGS = {
    "is_mintable": 10,
    "owner_change_balance": 10,
    "is_proxy": 5,
    "can_take_back_ownership": 10,
    "slippage_modifiable": 8,
    "is_anti_whale": 0,  # informational, not a risk
}

_HIGH_TAX_THRESHOLD = 0.10  # 10%+ buy or sell tax


def evaluate_security(goplus_data: dict | None) -> SecurityResult:
    if goplus_data is None:
        # No data = cannot confirm safety. Fail closed, not open.
        return SecurityResult(
            passed_minimum_requirements=False,
            score_penalty=30,
            warnings=["Security data unavailable — failing closed until it can be verified."],
        )

    warnings: list[str] = []
    penalty = 0
    hard_fail = False

    for field_name, message in _HARD_FAIL_FLAGS.items():
        if str(goplus_data.get(field_name, "0")) == "1":
            hard_fail = True
            warnings.append(message)

    for field_name, points in _SOFT_PENALTY_FLAGS.items():
        if str(goplus_data.get(field_name, "0")) == "1" and points > 0:
            penalty += points
            warnings.append(f"{field_name.replace('_', ' ')} detected.")

    try:
        buy_tax = float(goplus_data.get("buy_tax", 0) or 0)
        sell_tax = float(goplus_data.get("sell_tax", 0) or 0)
        if buy_tax >= _HIGH_TAX_THRESHOLD or sell_tax >= _HIGH_TAX_THRESHOLD:
            penalty += 15
            warnings.append(f"High tax: buy {buy_tax:.0%}, sell {sell_tax:.0%}.")
    except (TypeError, ValueError):
        pass

    try:
        lp_holders = goplus_data.get("lp_holders") or []
        locked_pct = sum(
            float(h.get("percent", 0)) for h in lp_holders if h.get("is_locked") == 1
        )
        if locked_pct < 0.5:
            penalty += 15
            warnings.append(f"Liquidity lock/burn only covers {locked_pct:.0%} of LP.")
    except (TypeError, ValueError):
        pass

    try:
        top_holder_pct = float(goplus_data.get("holder_percent_top10", 0) or 0)
        if top_holder_pct > 0.5:
            penalty += 10
            warnings.append(f"Top 10 holders control {top_holder_pct:.0%} of supply.")
    except (TypeError, ValueError):
        pass

    penalty = min(penalty, 30)
    return SecurityResult(
        passed_minimum_requirements=not hard_fail,
        score_penalty=30 if hard_fail else penalty,
        warnings=warnings,
    )


def evaluate_security_check(check) -> SecurityResult:
    """
    Wraps evaluate_security() for a GoPlusAdapter.SecurityCheckResult
    (see adapters/goplus.py) instead of a bare dict. FAILED and
    UNAVAILABLE both fail closed — a provider outage must never be
    silently treated as "this token is safe".
    """
    from app.adapters.base import DataStatus  # local import avoids a cycle at module load time

    if check.status in (DataStatus.FAILED, DataStatus.UNAVAILABLE):
        return SecurityResult(
            passed_minimum_requirements=False,
            score_penalty=30,
            warnings=[f"Security data unavailable ({check.status.value}): {check.error or 'no reason given'}."],
        )
    return evaluate_security(check.raw)
