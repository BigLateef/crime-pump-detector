"""
Called by an external scheduler (cron-job.org, GitHub Actions cron, etc.)
on an interval, instead of running an always-on worker process. Protected
by a shared secret header, not JWT auth, since the caller is a cron
service, not a logged-in user.

POST /internal/scanner/run is the canonical endpoint. POST /internal/scan
is kept as a deprecated alias (same handler) since it was the original
path from an earlier phase and may already be configured in a scheduler
somewhere - removing it outright would silently break that scheduler.
"""
import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_db
from app.core.rate_limit import is_rate_limited
from app.workers.discord_delivery import deliver_pending
from app.workers.scanner import run_scan_batch
from app.workers.scanner_lock import ScannerLockUnavailable, acquire_lock, get_status, record_failure, record_success, release_lock

logger = logging.getLogger("internal_api")

router = APIRouter(prefix="/internal", tags=["internal"])


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _require_scan_secret(x_scan_secret: str | None) -> None:
    settings = get_settings()
    # Constant-shape rejection: same error regardless of *why* it's
    # invalid (missing, wrong, or the trigger secret itself unset) - never
    # reveals which case applies, same principle as the invite validator.
    if not x_scan_secret or x_scan_secret != settings.scan_trigger_secret:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid scan trigger secret.")


async def _run_scanner(db: AsyncSession) -> dict:
    try:
        run_id = await acquire_lock()
    except ScannerLockUnavailable:
        # Redis is down - refuse to run rather than risk two overlapping
        # scans double-writing metrics/alerts with no way to dedupe them.
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Scanner lock unavailable (Redis unreachable) - refusing to start a run rather than risk an overlapping scan.",
        )

    if run_id is None:
        return {"status": "skipped", "reason": "A scan is already in progress."}

    try:
        stats = await run_scan_batch(db)
        delivery_stats = await deliver_pending(db)
        stats["discord_delivery"] = delivery_stats
        await record_success(stats)
        return {"status": "ok", "stats": stats}
    except Exception as e:  # noqa: BLE001 - always record the failure, then re-raise
        logger.exception("scan batch failed")
        await record_failure(f"{type(e).__name__}: {e}")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Scan batch failed - see server logs.")
    finally:
        await release_lock(run_id)


@router.post("/scanner/run")
async def trigger_scanner_run(
    request: Request,
    x_scan_secret: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    # Fail-closed, keyed by IP rather than identity (the caller has no
    # identity yet at this point - that's what the secret check is for).
    # This slows down brute-force guessing of SCAN_TRIGGER_SECRET; it does
    # NOT throttle legitimate scan frequency, since the run-lock already
    # handles that far more precisely.
    await is_rate_limited(f"scanner-trigger:{_client_ip(request)}", max_requests=30, window_seconds=60)
    _require_scan_secret(x_scan_secret)
    return await _run_scanner(db)


@router.post("/scan", deprecated=True)
async def trigger_scan_legacy(
    request: Request,
    x_scan_secret: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Deprecated alias for POST /internal/scanner/run - kept so an
    already-configured scheduler doesn't silently break."""
    await is_rate_limited(f"scanner-trigger:{_client_ip(request)}", max_requests=30, window_seconds=60)
    _require_scan_secret(x_scan_secret)
    return await _run_scanner(db)


@router.get("/scanner/status")
async def scanner_status(x_scan_secret: str | None = Header(default=None)):
    """
    Same shared-secret gate as the run endpoint, not JWT auth - this is
    operational telemetry a scheduler or ops dashboard checks, not
    something a logged-in user needs. (The frontend's own
    /admin/health page uses the JWT-authed /health/ready and
    /data-sources/status instead; this endpoint is for external
    monitoring tooling.)
    """
    _require_scan_secret(x_scan_secret)
    return await get_status()
