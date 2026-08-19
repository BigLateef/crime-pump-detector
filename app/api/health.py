from fastapi import APIRouter
from sqlalchemy import text

from app.core.config import get_settings
from app.core.db import AsyncSessionLocal
from app.core.redis_client import get_redis

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    """Liveness check — process is up. Does not touch DB/Redis."""
    return {"status": "ok"}


@router.get("/health/ready")
async def readiness():
    """
    Readiness check — verifies the app can actually talk to its dependencies.
    Used by Docker/orchestrator health checks and by the Section-13 system
    health dashboard in later phases.
    """
    settings = get_settings()
    checks = {"database": "unknown", "redis": "unknown"}

    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:  # noqa: BLE001
        checks["database"] = f"error: {type(e).__name__}"

    try:
        redis = get_redis()
        await redis.ping()
        checks["redis"] = "ok"
    except Exception as e:  # noqa: BLE001
        checks["redis"] = f"error: {type(e).__name__}"

    all_ok = all(v == "ok" for v in checks.values())
    return {
        "status": "ok" if all_ok else "degraded",
        "checks": checks,
        "dry_run": settings.dry_run,
        "low_cost_mode": settings.low_cost_mode,
    }
