from app.backtesting.validation import validate_dataset, validate_row, validate_address

VALID_ROW = {
    "token_address": "11111111111111111111111111111111",
    "chain": "solana",
    "symbol": "DEMO1",
    "snapshot_timestamp": "2026-01-01T00:00:00Z",
    "minutes_before_major_move": "60",
    "price": "0.0001",
    "source": "Test source",
    "data_quality": "DEMO",
    "outcome": "runner",
    "major_move_timestamp": "2026-01-01T01:00:00Z",
}


def test_valid_row_passes():
    clean, errors, warnings = validate_row(dict(VALID_ROW), 0)
    assert errors == []
    assert clean is not None
    assert clean["minutes_before_major_move"] == 60


def test_missing_required_field_rejected():
    row = dict(VALID_ROW)
    del row["price"]
    clean, errors, _ = validate_row(row, 0)
    assert clean is None
    assert any(e.field == "price" for e in errors)


def test_negative_value_rejected():
    row = dict(VALID_ROW)
    row["price"] = "-5"
    clean, errors, _ = validate_row(row, 0)
    assert clean is None
    assert any(e.field == "price" for e in errors)


def test_invalid_minutes_before_move_rejected():
    row = dict(VALID_ROW)
    row["minutes_before_major_move"] = "45"  # not one of the 7 required offsets
    clean, errors, _ = validate_row(row, 0)
    assert clean is None
    assert any(e.field == "minutes_before_major_move" for e in errors)


def test_verified_without_source_rejected():
    row = dict(VALID_ROW)
    row["data_quality"] = "VERIFIED"
    row["source"] = ""
    clean, errors, _ = validate_row(row, 0)
    assert clean is None
    assert any(e.field == "source" for e in errors)


def test_future_data_leakage_rejected():
    row = dict(VALID_ROW)
    row["snapshot_timestamp"] = "2026-01-01T02:00:00Z"  # after major_move_timestamp
    clean, errors, _ = validate_row(row, 0)
    assert clean is None
    assert any(e.field == "snapshot_timestamp" for e in errors)


def test_invalid_solana_address_rejected():
    row = dict(VALID_ROW)
    row["token_address"] = "not-a-real-address!!!"
    clean, errors, _ = validate_row(row, 0)
    assert clean is None
    assert any(e.field == "token_address" for e in errors)


def test_valid_ethereum_address_format():
    assert validate_address("ethereum", "0x" + "a" * 40) is True
    assert validate_address("ethereum", "not-hex") is False


def test_duplicate_rows_flagged_within_dataset():
    rows = [dict(VALID_ROW), dict(VALID_ROW)]
    report = validate_dataset(rows)
    assert report.valid_rows == 1
    assert report.duplicate_rows == 1


def test_suspicious_unique_buyers_exceeding_buy_count_warns_not_rejects():
    row = dict(VALID_ROW)
    row["buy_count"] = "5"
    row["unique_buyers"] = "50"
    clean, errors, warnings = validate_row(row, 0)
    assert clean is not None  # not rejected
    assert any(w.field == "unique_buyers" for w in warnings)


def test_dataset_report_counts_are_consistent():
    rows = [dict(VALID_ROW) for _ in range(3)]
    rows[1]["minutes_before_major_move"] = "999"  # invalid
    report = validate_dataset(rows)
    assert report.total_rows == 3
    assert report.error_rows == 1
    assert report.valid_rows + report.duplicate_rows == 2
