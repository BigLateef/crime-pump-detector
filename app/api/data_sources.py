"""
Reports which data providers are configured and enabled, without exposing
any credentials — there are none in these providers (both are keyless),
but the shape here is deliberately credential-free regardless, so it
stays safe if a future provider needs a key.
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.deps import get_current_user
from app.models.user import User

router = APIRouter(prefix="/data-sources", tags=["data-sources"])


class ProviderStatus(BaseModel):
    name: str
    enabled: bool
    mode: str  # "live" | "mock" | "disabled"


class DataSourceStatusOut(BaseModel):
    provider_mode: str
    cache_ttl_seconds: int
    request_timeout_seconds: float
    max_retries: int
    providers: list[ProviderStatus]


@router.get("/status", response_model=DataSourceStatusOut)
async def get_status(user: User = Depends(get_current_user)):
    settings = get_settings()
    is_live = settings.data_provider_mode == "live"

    return DataSourceStatusOut(
        provider_mode=settings.data_provider_mode,
        cache_ttl_seconds=settings.data_cache_ttl_seconds,
        request_timeout_seconds=settings.data_request_timeout_seconds,
        max_retries=settings.data_max_retries,
        providers=[
            ProviderStatus(
                name="dexscreener",
                enabled=settings.dexscreener_enabled,
                mode="live" if (is_live and settings.dexscreener_enabled) else ("mock" if not is_live else "disabled"),
            ),
            ProviderStatus(
                name="goplus",
                enabled=settings.goplus_enabled,
                mode="live" if (is_live and settings.goplus_enabled) else ("mock" if not is_live else "disabled"),
            ),
        ],
    )
