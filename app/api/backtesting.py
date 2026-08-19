"""
Admin-only backtesting API. Upload/validate/import are separate steps on
purpose: `validate` never writes to the database, so an admin can see
exactly what would happen before committing to an import.
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.backtesting.framework import evaluate_against_baseline, evaluate_case
from app.backtesting.importer import import_dataset, parse_csv, parse_json
from app.backtesting.loader import DatasetIntegrityError, load_cases
from app.backtesting.validation import validate_dataset
from app.core.db import get_db
from app.core.deps import require_admin
from app.core.rate_limit import is_rate_limited
from app.models.historical_snapshot import HistoricalDataset
from app.models.user import User

router = APIRouter(prefix="/admin/backtesting", tags=["admin-backtesting"])


# ---------- Schemas ----------

class ValidateRequest(BaseModel):
    file_format: Literal["csv", "json"]
    # Size cap (~5,000,000 chars ≈ 5MB of text) — this is a JSON body field,
    # not a multipart file upload, so the usual "file size limit" is
    # enforced here as a string length limit instead. Rejects oversized
    # payloads before any parsing/regex work touches them.
    content: str = Field(min_length=1, max_length=5_000_000)
    data_quality: Literal["VERIFIED", "DEMO", "ESTIMATED"] = "DEMO"


class ValidationErrorOut(BaseModel):
    row: int
    field: str
    message: str


class ValidationReportOut(BaseModel):
    total_rows: int
    valid_rows: int
    error_rows: int
    duplicate_rows: int
    errors: list[ValidationErrorOut]
    warnings: list[ValidationErrorOut]


class ImportRequest(ValidateRequest):
    name: str
    source_filename: str | None = None


class DatasetOut(BaseModel):
    id: str
    name: str
    data_quality: str
    status: str
    row_count: int
    valid_row_count: int
    error_row_count: int
    duplicate_row_count: int
    created_at: datetime
    imported_at: datetime | None

    class Config:
        from_attributes = True


class DatasetQualityOut(BaseModel):
    dataset_id: str
    total_rows: int
    valid_rows: int
    invalid_rows: int
    duplicate_rows: int
    missing_field_counts: dict[str, int]
    suspicious_value_count: int
    verified_rows: int
    demo_rows: int
    estimated_rows: int
    unavailable_rows: int
    earliest_snapshot: datetime | None
    latest_snapshot: datetime | None
    distinct_tokens: int
    outcome_distribution: dict[str, int]
    sources: list[str]
    data_freshness_hours: float | None  # hours since the most recent snapshot in this dataset
    validation_status: str  # "clean" | "has_errors" | "has_warnings_only"


class RunBacktestRequest(BaseModel):
    dataset_ids: list[str] | None = None
    split: str = "test"  # "train" | "test" | "all"
    threshold: int = 55
    require_verified: bool = True


class CaseResultOut(BaseModel):
    label: str
    outcome: str
    would_have_alerted: bool
    earliest_alert_minutes_before_move: int | None


class BacktestResultOut(BaseModel):
    summary: dict
    cases: list[CaseResultOut]


# ---------- Endpoints ----------

@router.post("/validate", response_model=ValidationReportOut)
async def validate_upload(body: ValidateRequest, admin: User = Depends(require_admin)):
    # Fail-closed: an upload endpoint accepting up to 5MB of text per
    # request is exactly the kind of thing worth rate-limiting even
    # behind admin auth - if Redis can't confirm the limit, reject rather
    # than risk unbounded parsing work.
    await is_rate_limited(f"backtesting-validate:{admin.id}", max_requests=20, window_seconds=60)

    try:
        rows = parse_csv(body.content) if body.file_format == "csv" else parse_json(body.content)
    except (ValueError, Exception) as e:  # noqa: BLE001 — surface parse errors to the admin plainly
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Could not parse file: {e}")

    if body.data_quality == "DEMO":
        for row in rows:
            row["data_quality"] = "DEMO"

    report = validate_dataset(rows)
    return ValidationReportOut(
        total_rows=report.total_rows,
        valid_rows=report.valid_rows,
        error_rows=report.error_rows,
        duplicate_rows=report.duplicate_rows,
        errors=[ValidationErrorOut(row=e.row_index, field=e.field, message=e.message) for e in report.errors],
        warnings=[ValidationErrorOut(row=w.row_index, field=w.field, message=w.message) for w in report.warnings],
    )


@router.post("/import", response_model=DatasetOut, status_code=status.HTTP_201_CREATED)
async def import_upload(
    body: ImportRequest, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
):
    await is_rate_limited(f"backtesting-import:{admin.id}", max_requests=10, window_seconds=60)

    if body.data_quality == "VERIFIED":
        # Extra guard beyond row-level validation: refuse a VERIFIED import
        # outright if literally no source is present anywhere in the file,
        # rather than importing zero valid rows silently.
        try:
            rows = parse_csv(body.content) if body.file_format == "csv" else parse_json(body.content)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Could not parse file: {e}")
        if not any(r.get("source") for r in rows):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "A VERIFIED dataset requires a source on every row — none were found.",
            )

    dataset = await import_dataset(
        db,
        name=body.name,
        raw_text=body.content,
        file_format=body.file_format,
        data_quality=body.data_quality,
        uploaded_by=admin.id,
        source_filename=body.source_filename,
    )
    return dataset


@router.get("/datasets", response_model=list[DatasetOut])
async def list_datasets(admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(HistoricalDataset).order_by(HistoricalDataset.created_at.desc()))
    return result.scalars().all()


@router.get("/datasets/{dataset_id}", response_model=DatasetOut)
async def get_dataset(
    dataset_id: str, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(HistoricalDataset).where(HistoricalDataset.id == dataset_id))
    dataset = result.scalar_one_or_none()
    if dataset is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dataset not found.")
    return dataset


@router.get("/datasets/{dataset_id}/quality", response_model=DatasetQualityOut)
async def get_dataset_quality(
    dataset_id: str, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
):
    """
    Computes quality metrics live from the imported HistoricalSnapshot
    rows (not just the summary counters stored on HistoricalDataset at
    import time) — so this reflects the dataset's actual current content,
    including rows from re-imports or partial imports.
    """
    from app.models.historical_snapshot import HistoricalSnapshot

    dataset = (
        await db.execute(select(HistoricalDataset).where(HistoricalDataset.id == dataset_id))
    ).scalar_one_or_none()
    if dataset is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dataset not found.")

    rows = (
        (await db.execute(select(HistoricalSnapshot).where(HistoricalSnapshot.dataset_id == dataset_id)))
        .scalars()
        .all()
    )

    quality_counts = {"VERIFIED": 0, "DEMO": 0, "ESTIMATED": 0, "UNAVAILABLE": 0}
    for r in rows:
        if r.data_quality in quality_counts:
            quality_counts[r.data_quality] += 1

    # Field-level "missing" tally across optional fields worth watching —
    # required fields can't be missing on an imported row (validation.py
    # already rejects those before import), so this only tracks the
    # optional ones that most affect scoring quality.
    watched_fields = [
        "liquidity", "volume_1h", "unique_buyers", "unique_sellers",
        "holder_count", "top_holder_concentration", "deployer_balance",
    ]
    missing_field_counts = {f: sum(1 for r in rows if getattr(r, f) is None) for f in watched_fields}

    # Suspicious-value re-check (same rules as validation.py's warnings,
    # applied to what actually landed in the DB rather than re-trusting
    # the import-time snapshot of warnings).
    suspicious_value_count = 0
    for r in rows:
        if r.unique_buyers is not None and r.buy_count is not None and r.unique_buyers > r.buy_count:
            suspicious_value_count += 1
        elif r.top_holder_concentration is not None and r.top_holder_concentration > 1:
            suspicious_value_count += 1

    timestamps = [r.snapshot_timestamp for r in rows if r.snapshot_timestamp is not None]
    earliest = min(timestamps) if timestamps else None
    latest = max(timestamps) if timestamps else None

    freshness_hours = None
    if latest is not None:
        now = datetime.now(latest.tzinfo) if latest.tzinfo else datetime.utcnow()
        freshness_hours = (now - latest).total_seconds() / 3600

    outcome_distribution: dict[str, int] = {}
    for r in rows:
        outcome_distribution[r.outcome] = outcome_distribution.get(r.outcome, 0) + 1

    distinct_tokens = len({(r.chain, r.token_address) for r in rows})
    sources = sorted({r.source for r in rows if r.source})

    if dataset.error_row_count > 0:
        validation_status = "has_errors"
    elif suspicious_value_count > 0:
        validation_status = "has_warnings_only"
    else:
        validation_status = "clean"

    return DatasetQualityOut(
        dataset_id=dataset_id,
        total_rows=dataset.row_count,
        valid_rows=dataset.valid_row_count,
        invalid_rows=dataset.error_row_count,
        duplicate_rows=dataset.duplicate_row_count,
        missing_field_counts=missing_field_counts,
        suspicious_value_count=suspicious_value_count,
        verified_rows=quality_counts["VERIFIED"],
        demo_rows=quality_counts["DEMO"],
        estimated_rows=quality_counts["ESTIMATED"],
        unavailable_rows=quality_counts["UNAVAILABLE"],
        earliest_snapshot=earliest,
        latest_snapshot=latest,
        distinct_tokens=distinct_tokens,
        outcome_distribution=outcome_distribution,
        sources=sources,
        data_freshness_hours=freshness_hours,
        validation_status=validation_status,
    )


@router.post("/run", response_model=BacktestResultOut)
async def run_backtest(
    body: RunBacktestRequest, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
):
    try:
        cases = await load_cases(
            db,
            dataset_ids=body.dataset_ids,
            split=None if body.split == "all" else body.split,
            require_verified=body.require_verified,
        )
    except DatasetIntegrityError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))

    if not cases:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "No matching cases found. Import a VERIFIED dataset with the requested split, "
            "or pass require_verified=false to test against demo data explicitly.",
        )

    summary = evaluate_against_baseline(cases, threshold=body.threshold)
    case_results = [evaluate_case(c, threshold=body.threshold) for c in cases]

    return BacktestResultOut(
        summary=summary,
        cases=[
            CaseResultOut(
                label=r.label,
                outcome=r.outcome,
                would_have_alerted=r.would_have_alerted,
                earliest_alert_minutes_before_move=r.earliest_alert_minutes_before_move,
            )
            for r in case_results
        ],
    )


@router.get("/export")
async def export_results(
    dataset_id: str = Query(...),
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Exports the raw snapshot rows for one dataset as JSON — meant for
    taking results out to a spreadsheet, not a full report generator.
    """
    from app.models.historical_snapshot import HistoricalSnapshot

    result = await db.execute(select(HistoricalSnapshot).where(HistoricalSnapshot.dataset_id == dataset_id))
    rows = result.scalars().all()
    return {
        "dataset_id": dataset_id,
        "row_count": len(rows),
        "rows": [
            {
                "token_address": r.token_address,
                "chain": r.chain,
                "symbol": r.symbol,
                "minutes_before_major_move": r.minutes_before_major_move,
                "outcome": r.outcome,
                "data_quality": r.data_quality,
                "dataset_split": r.dataset_split,
            }
            for r in rows
        ],
    }
