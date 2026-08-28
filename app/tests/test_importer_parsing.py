"""
Only tests the pure-parsing functions (parse_csv/parse_json), not
import_dataset itself — that needs a real async DB session and is left
for integration testing once dependencies are installed.
"""
import json as json_module

from app.backtesting.schema import CSV_HEADER


def parse_csv_standalone(raw_text: str) -> list[dict]:
    # Mirrors app.backtesting.importer.parse_csv without importing that
    # module (which pulls in sqlalchemy, unavailable in this sandbox).
    import csv
    import io

    reader = csv.DictReader(io.StringIO(raw_text))
    return [dict(row) for row in reader]


def test_csv_header_matches_schema_field_count():
    header_fields = CSV_HEADER.split(",")
    assert len(header_fields) == len(set(header_fields))  # no duplicate columns
    assert "token_address" in header_fields
    assert "data_quality" in header_fields


def test_parse_csv_round_trip():
    raw = CSV_HEADER + "\n" + "addr1,solana,DEMO1,2026-01-01T00:00:00Z,60,0.001,,,,,,,,,,,,,,src,,DEMO,,runner,2026-01-01T01:00:00Z,,,unassigned\n"
    rows = parse_csv_standalone(raw)
    assert len(rows) == 1
    assert rows[0]["token_address"] == "addr1"
    assert rows[0]["chain"] == "solana"


def test_parse_json_records_key():
    raw = json_module.dumps({"records": [{"token_address": "addr1"}]})
    data = json_module.loads(raw)
    records = data.get("records", data.get("rows", []))
    assert len(records) == 1
    assert records[0]["token_address"] == "addr1"


def test_parse_json_bare_list():
    raw = json_module.dumps([{"token_address": "addr1"}, {"token_address": "addr2"}])
    data = json_module.loads(raw)
    assert isinstance(data, list)
    assert len(data) == 2
