"""
The seven Discord alert types. This is a separate dimension from
SignalAlert.signal_type (WATCH/EARLY/HIGH-CONVICTION/AVOID/EXIT_DANGER,
which is the scanner's classification of a token) - alert_type instead
describes what *kind* of Discord message this is, several of which have
nothing to do with a scored signal at all (a security rejection, or the
scanner itself crashing, aren't classifications of a token).

Implementation status, stated plainly rather than left to be discovered
later:
  - SIGNAL_DETECTED and SECURITY_RISK are fully wired: real detection
    logic in app/workers/scanner.py drives both, using data the scanner
    already computes every pass.
  - SCANNER_FAILURE is fully wired: fires from run_scan_batch's own
    top-level exception handling.
  - LIQUIDITY_WARNING, DEPLOYER_SELLING, MOMENTUM_FAILURE, and
    MOMENTUM_RECOVERY are defined here (and supported everywhere in the
    delivery/config/schema/frontend layer) but have NO detection logic
    behind them yet. Each requires comparing a token's metrics across
    multiple scan passes over time (a liquidity drop, a
    previously-flagged deployer wallet now selling, a momentum
    reversal/recovery) - none of that historical-comparison machinery
    exists in this codebase today; run_scan_batch only ever looks at one
    snapshot at a time. Wiring these up is a separate, materially larger
    piece of work than "add a Discord alert type" and is deliberately
    left undone rather than faked with placeholder logic that would
    silently never fire or fire on wrong conditions.
"""

SIGNAL_DETECTED = "SIGNAL_DETECTED"
SECURITY_RISK = "SECURITY_RISK"
LIQUIDITY_WARNING = "LIQUIDITY_WARNING"
DEPLOYER_SELLING = "DEPLOYER_SELLING"
MOMENTUM_FAILURE = "MOMENTUM_FAILURE"
MOMENTUM_RECOVERY = "MOMENTUM_RECOVERY"
SCANNER_FAILURE = "SCANNER_FAILURE"

ALL_ALERT_TYPES = (
    SIGNAL_DETECTED,
    SECURITY_RISK,
    LIQUIDITY_WARNING,
    DEPLOYER_SELLING,
    MOMENTUM_FAILURE,
    MOMENTUM_RECOVERY,
    SCANNER_FAILURE,
)

# Alert types currently backed by real detection logic vs. defined-but-unwired.
IMPLEMENTED_ALERT_TYPES = (SIGNAL_DETECTED, SECURITY_RISK, SCANNER_FAILURE)
UNIMPLEMENTED_ALERT_TYPES = tuple(t for t in ALL_ALERT_TYPES if t not in IMPLEMENTED_ALERT_TYPES)
