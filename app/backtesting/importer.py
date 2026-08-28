"""
Imports a validated batch of rows into HistoricalDataset +
HistoricalSnapshot. Validation (app/backtesting/validation.py) is always
run first and its report is what gets stored on the dataset row — this
module's only additional job is checking for duplicates against rows
already in the database (validation.py only catches duplicates within the
same upload).
"""
import csv
import io
import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.backtesting.schema import FIELDS
from app.backtesting.validation import RowError, ValidationReport, validate_dataset
from app.models.historical_snapshot import HistoricalDataset, HistoricalSnapshot

IMPORTER_VERSION = "1.0.0"


def parse_csv(raw_text: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(raw_text))
    return [dict(row) for row in reader]


def parse_json(raw_text: str) -> list[dict]:
    data = json.loads(raw_text)
    if isinstance(data, dict):
        data = data.get("records", data.get("rows", []))
    if not isinstance(data, list):
        raise ValueError("JSON dataset must be a list of records, or an object with a 'records' key.")
    return data


async def check_db_duplicates(db: AsyncSession, report: ValidationReport) -> ValidationReport:
    """Second duplicate pass: same (chain, address, snapshot_timestamp)
    already imported from a *previous* dataset. Removes them from
    clean_records and adds a RowError so the importer report is honest
    about why the count dropped."""
    kept: list[dict] = []
    for i, record in enumerate(report.clean_records):
        existing = await db.execute(
            select(HistoricalSnapshot.id).where(
                HistoricalSnapshot.chain == record["chain"],
                HistoricalSnapshot.token_address == record["token_address"],
                HistoricalSnapshot.snapshot_timestamp == record["snapshot_timestamp"],
            )
        )
        if existing.scalar_one_or_none() is not None:
            report.errors.append(
                RowError(i, "token_address", "Already imported in a previous dataset (same token + timestamp).")
            )
            report.duplicate_rows += 1
            report.valid_rows -= 1
            continue
        kept.append(record)
    report.clean_records = kept
    return report


async def import_dataset(
    db: AsyncSession,
    name: str,
    raw_text: str,
    file_format: str,  # "csv" | "json"
    data_quality: str,
    uploaded_by: str,
    source_filename: str | None = None,
    commit: bool = True,
) -> HistoricalDataset:
    rows = parse_csv(raw_text) if file_format == "csv" else parse_json(raw_text)

    # DEMO datasets are validated the same way, but every row is force-
    # tagged data_quality=DEMO regardless of what the file says, so a demo
    # upload can never accidentally count as verified.
    if data_quality == "DEMO":
        for row in rows:
            row["data_quality"] = "DEMO"

    report = validate_dataset(rows)
    report = await check_db_duplicates(db, report)

    dataset = HistoricalDataset(
        name=name,
        data_quality=data_quality,
        uploaded_by=uploaded_by,
        source_filename=source_filename,
        importer_version=IMPORTER_VERSION,
        status="validated" if report.error_rows == 0 else "validated_with_errors",
        row_count=report.total_rows,
        valid_row_count=report.valid_rows,
        error_row_count=report.error_rows,
        duplicate_row_count=report.duplicate_rows,
        validation_errors=[
            {"row": e.row_index, "field": e.field, "message": e.message} for e in report.errors
        ],
    )
    db.add(dataset)
    await db.flush()

    from datetime import datetime, timezone

    for record in report.clean_records:
        db.add(
            HistoricalSnapshot(
                dataset_id=dataset.id,
                token_address=record["token_address"],
                chain=record["chain"],
                symbol=record.get("symbol"),
                snapshot_timestamp=record["snapshot_timestamp"],
                minutes_before_major_move=record["minutes_before_major_move"],
                price=record.get("price"),
                market_cap=record.get("market_cap"),
                liquidity=record.get("liquidity"),
                volume_1m=record.get("volume_1m"),
                volume_5m=record.get("volume_5m"),
                volume_15m=record.get("volume_15m"),
                volume_1h=record.get("volume_1h"),
                buy_count=record.get("buy_count"),
                sell_count=record.get("sell_count"),
                unique_buyers=record.get("unique_buyers"),
                unique_sellers=record.get("unique_sellers"),
                holder_count=record.get("holder_count"),
                top_holder_concentration=record.get("top_holder_concentration"),
                deployer_balance=record.get("deployer_balance"),
                security_flags=record.get("security_flags") or [],
                source=record["source"],
                source_url=record.get("source_url"),
                data_quality=record["data_quality"],
                notes=record.get("notes"),
                outcome=record["outcome"],
                major_move_timestamp=record["major_move_timestamp"],
                maximum_drawdown_pct=record.get("maximum_drawdown_pct"),
                maximum_gain_pct=record.get("maximum_gain_pct"),
                dataset_split=record.get("dataset_split") or "unassigned",
            )
        )

    if report.clean_records:
        dataset.status = "imported"
        dataset.imported_at = datetime.now(timezone.utc)

    if commit:
        await db.commit()
        await db.refresh(dataset)

    return dataset
