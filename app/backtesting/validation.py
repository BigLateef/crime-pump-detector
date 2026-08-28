"""
Row-level and dataset-level validation for historical snapshot imports.
Nothing here fabricates or fills a missing value — a row either passes
with the fields it has (rest stay None) or is rejected with a specific
reason. Every VERIFIED row must carry a `source`; every row's
`minutes_before_major_move` must be one of the seven required offsets so
snapshots line up across tokens for a fair comparison.
"""
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.backtesting.schema import FIELDS, REQUIRED_MINUTES_BEFORE_MOVE

_ADDRESS_PATTERNS = {
    "ethereum": re.compile(r"^0x[a-fA-F0-9]{40}$"),
    "base": re.compile(r"^0x[a-fA-F0-9]{40}$"),
    "bnb": re.compile(r"^0x[a-fA-F0-9]{40}$"),
    "solana": re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$"),  # base58, excludes 0/O/I/l
}


@dataclass
class RowError:
    row_index: int
    field: str
    message: str


@dataclass
class ValidationReport:
    total_rows: int
    valid_rows: int
    error_rows: int
    duplicate_rows: int
    errors: list[RowError] = field(default_factory=list)
    warnings: list[RowError] = field(default_factory=list)  # suspicious-but-not-rejected
    clean_records: list[dict] = field(default_factory=list)


def _parse_datetime_utc(value: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (ValueError, AttributeError):
        return None


def validate_address(chain: str, address: str) -> bool:
    pattern = _ADDRESS_PATTERNS.get(chain)
    if pattern is None:
        return False
    return bool(pattern.match(address))


def validate_row(row: dict, row_index: int) -> tuple[dict | None, list[RowError], list[RowError]]:
    """Returns (clean_record_or_None, errors, warnings)."""
    errors: list[RowError] = []
    warnings: list[RowError] = []
    clean: dict = {}

    for spec in FIELDS:
        raw = row.get(spec.name)
        is_empty = raw is None or raw == ""

        if spec.required and is_empty:
            errors.append(RowError(row_index, spec.name, "Required field is missing."))
            continue
        if is_empty:
            clean[spec.name] = None
            continue

        if spec.kind == "enum":
            if spec.enum_values and raw not in spec.enum_values:
                errors.append(RowError(row_index, spec.name, f"Must be one of {spec.enum_values}, got {raw!r}."))
                continue
            clean[spec.name] = raw

        elif spec.kind in ("float", "int"):
            try:
                value = float(raw) if spec.kind == "float" else int(raw)
            except (TypeError, ValueError):
                errors.append(RowError(row_index, spec.name, f"Expected a {spec.kind}, got {raw!r}."))
                continue
            if not spec.allow_negative and value < 0:
                errors.append(RowError(row_index, spec.name, f"Negative value not allowed: {value}."))
                continue
            clean[spec.name] = value

        elif spec.kind == "datetime":
            dt = _parse_datetime_utc(str(raw))
            if dt is None:
                errors.append(RowError(row_index, spec.name, f"Could not parse as UTC ISO-8601: {raw!r}."))
                continue
            clean[spec.name] = dt

        elif spec.kind == "list":
            if isinstance(raw, list):
                clean[spec.name] = raw
            elif isinstance(raw, str):
                clean[spec.name] = [v.strip() for v in raw.split(";") if v.strip()]
            else:
                errors.append(RowError(row_index, spec.name, "security_flags must be a list or ';'-separated string."))
                continue

        else:  # str
            clean[spec.name] = str(raw)

    if errors:
        return None, errors, warnings

    # Cross-field checks that need more than one field at once.
    if clean.get("chain") and clean.get("token_address"):
        if not validate_address(clean["chain"], clean["token_address"]):
            errors.append(RowError(row_index, "token_address", f"Doesn't look like a valid {clean['chain']} address."))
            return None, errors, warnings

    if clean.get("minutes_before_major_move") not in REQUIRED_MINUTES_BEFORE_MOVE:
        errors.append(
            RowError(
                row_index,
                "minutes_before_major_move",
                f"Must be one of {REQUIRED_MINUTES_BEFORE_MOVE} (24h/12h/6h/3h/1h/30m/10m before the move).",
            )
        )
        return None, errors, warnings

    if clean.get("data_quality") == "VERIFIED" and not clean.get("source"):
        errors.append(RowError(row_index, "source", "VERIFIED rows must have a source."))
        return None, errors, warnings

    # snapshot_timestamp must actually be before major_move_timestamp —
    # this is the core future-data-leakage guard at the row level.
    ts, move_ts = clean.get("snapshot_timestamp"), clean.get("major_move_timestamp")
    if ts and move_ts and ts >= move_ts:
        errors.append(
            RowError(row_index, "snapshot_timestamp", "Must be strictly before major_move_timestamp (no future data).")
        )
        return None, errors, warnings

    # Suspicious-but-not-rejected checks (Section: "flag suspicious or
    # inconsistent values").
    if clean.get("buy_count") is not None and clean.get("unique_buyers") is not None:
        if clean["unique_buyers"] > clean["buy_count"]:
            warnings.append(RowError(row_index, "unique_buyers", "unique_buyers exceeds buy_count — inconsistent."))
    if clean.get("top_holder_concentration") is not None and clean["top_holder_concentration"] > 1:
        warnings.append(RowError(row_index, "top_holder_concentration", "Expected a 0..1 fraction, got >1."))
    if clean.get("liquidity") is not None and clean.get("market_cap") is not None:
        if clean["market_cap"] > 0 and clean["liquidity"] / clean["market_cap"] > 5:
            warnings.append(RowError(row_index, "liquidity", "Liquidity far exceeds market cap — double-check the source."))

    return clean, errors, warnings


def validate_dataset(rows: list[dict]) -> ValidationReport:
    report = ValidationReport(total_rows=len(rows), valid_rows=0, error_rows=0, duplicate_rows=0)
    seen_keys: set[tuple] = set()

    for i, row in enumerate(rows):
        clean, errors, warnings = validate_row(row, i)
        report.warnings.extend(warnings)

        if errors:
            report.errors.extend(errors)
            report.error_rows += 1
            continue

        dedup_key = (clean["chain"], clean["token_address"].lower(), clean["snapshot_timestamp"].isoformat())
        if dedup_key in seen_keys:
            report.errors.append(RowError(i, "token_address", "Duplicate token/timestamp record."))
            report.duplicate_rows += 1
            continue
        seen_keys.add(dedup_key)

        report.clean_records.append(clean)
        report.valid_rows += 1

    return report
