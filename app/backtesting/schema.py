"""
The one source of truth for what a historical snapshot record must
contain. Both the CSV template and the JSON template are generated from
this list, so they can never drift out of sync with each other or with
the validator.
"""
from dataclasses import dataclass


@dataclass
class FieldSpec:
    name: str
    required: bool
    kind: str  # "str" | "float" | "int" | "datetime" | "list" | "enum"
    enum_values: tuple[str, ...] | None = None
    allow_negative: bool = True
    description: str = ""


FIELDS: list[FieldSpec] = [
    FieldSpec("token_address", True, "str", description="Contract address, format validated per chain."),
    FieldSpec("chain", True, "enum", enum_values=("solana", "base", "ethereum", "bnb"), description=""),
    FieldSpec("symbol", True, "str", description="Ticker as displayed at the time, e.g. DEMO1."),
    FieldSpec("snapshot_timestamp", True, "datetime", description="UTC ISO-8601, e.g. 2026-01-01T00:00:00Z."),
    FieldSpec("minutes_before_major_move", True, "int", allow_negative=False, description="One of 1440,720,360,180,60,30,10 — see validator."),
    FieldSpec("price", True, "float", allow_negative=False),
    FieldSpec("market_cap", False, "float", allow_negative=False),
    FieldSpec("liquidity", False, "float", allow_negative=False),
    FieldSpec("volume_1m", False, "float", allow_negative=False),
    FieldSpec("volume_5m", False, "float", allow_negative=False),
    FieldSpec("volume_15m", False, "float", allow_negative=False),
    FieldSpec("volume_1h", False, "float", allow_negative=False),
    FieldSpec("buy_count", False, "int", allow_negative=False),
    FieldSpec("sell_count", False, "int", allow_negative=False),
    FieldSpec("unique_buyers", False, "int", allow_negative=False),
    FieldSpec("unique_sellers", False, "int", allow_negative=False),
    FieldSpec("holder_count", False, "int", allow_negative=False),
    FieldSpec("top_holder_concentration", False, "float", allow_negative=False, description="0..1"),
    FieldSpec("deployer_balance", False, "float", allow_negative=False, description="0..1, % of supply"),
    FieldSpec("security_flags", False, "list", description="Semicolon-separated in CSV, array in JSON."),
    FieldSpec("source", True, "str", description="Required for every VERIFIED record — e.g. 'DexScreener chart, manually read'."),
    FieldSpec("source_url", False, "str"),
    FieldSpec(
        "data_quality", True, "enum",
        enum_values=("VERIFIED", "DEMO", "ESTIMATED", "UNAVAILABLE"),
        description="VERIFIED needs a real source; DEMO is fictional and never counted in real results.",
    ),
    FieldSpec("notes", False, "str"),
    # Case-level fields, repeated on every row for the same token+outcome:
    FieldSpec("outcome", True, "enum", enum_values=("runner", "failed", "flat", "dumped", "rugged", "fake_volume")),
    FieldSpec("major_move_timestamp", True, "datetime", description="UTC ISO-8601."),
    FieldSpec("maximum_drawdown_pct", False, "float", allow_negative=False),
    FieldSpec("maximum_gain_pct", False, "float", allow_negative=False),
    FieldSpec("dataset_split", False, "enum", enum_values=("train", "test", "unassigned")),
]

REQUIRED_MINUTES_BEFORE_MOVE = (1440, 720, 360, 180, 60, 30, 10)  # 24h,12h,6h,3h,1h,30m,10m

CSV_HEADER = ",".join(f.name for f in FIELDS)

JSON_TEMPLATE_EXAMPLE = [
    {f.name: (f.enum_values[0] if f.kind == "enum" and f.enum_values else None) for f in FIELDS}
]
