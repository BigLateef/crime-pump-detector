from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.crypto import encrypt_webhook_url
from app.core.db import get_db
from app.core.deps import require_admin
from app.core.discord_alert_types import ALL_ALERT_TYPES, IMPLEMENTED_ALERT_TYPES
from app.models.discord import DiscordIntegration
from app.models.user import User

router = APIRouter(prefix="/admin/discord-integrations", tags=["admin-discord"])


class DiscordAlertConfigOut(BaseModel):
    """
    Read-only view of the global, env-var-controlled Discord alert
    settings (DISCORD_ALERT_ALL_SIGNALS / DISCORD_ALERT_MIN_SCORE /
    DISCORD_ALERT_COOLDOWN_MINUTES) - these are deployment configuration,
    not per-integration DB settings, so this endpoint only ever reports
    the current value; changing them means updating the deployment's
    environment variables and redeploying, not a PATCH here.
    """

    all_signals_enabled: bool
    min_score: int
    cooldown_minutes: int
    all_alert_types: list[str]
    implemented_alert_types: list[str]


class DiscordIntegrationCreate(BaseModel):
    name: str
    webhook_url: str = Field(min_length=10)
    channel_label: str | None = None
    minimum_score: int | None = Field(default=None, ge=0, le=100)
    allowed_chains: list[str] = Field(default_factory=list)
    alert_types: list[str] = Field(default_factory=list)


class DiscordIntegrationOut(BaseModel):
    id: str
    name: str
    channel_label: str | None
    enabled: bool
    minimum_score: int
    allowed_chains: list[str]
    alert_types: list[str]
    # Deliberately no webhook_url field — it is write-only.

    class Config:
        from_attributes = True


@router.get("/config", response_model=DiscordAlertConfigOut)
async def get_discord_alert_config(admin: User = Depends(require_admin)):
    """
    Surfaces the current DISCORD_ALERT_ALL_SIGNALS / _MIN_SCORE /
    _COOLDOWN_MINUTES env vars, plus which of the seven alert types
    actually have detection logic behind them - so the admin UI can be
    honest about which alert types are real today (SIGNAL_DETECTED,
    SECURITY_RISK, SCANNER_FAILURE) versus defined-but-not-yet-wired
    (LIQUIDITY_WARNING, DEPLOYER_SELLING, MOMENTUM_FAILURE,
    MOMENTUM_RECOVERY) rather than silently implying all seven work.
    """
    settings = get_settings()
    return DiscordAlertConfigOut(
        all_signals_enabled=settings.discord_alert_all_signals,
        min_score=settings.discord_alert_min_score,
        cooldown_minutes=settings.discord_alert_cooldown_minutes,
        all_alert_types=list(ALL_ALERT_TYPES),
        implemented_alert_types=list(IMPLEMENTED_ALERT_TYPES),
    )


@router.post("", response_model=DiscordIntegrationOut, status_code=status.HTTP_201_CREATED)
async def create_integration(
    body: DiscordIntegrationCreate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    settings = get_settings()
    integration = DiscordIntegration(
        name=body.name,
        encrypted_webhook_url=encrypt_webhook_url(body.webhook_url),
        channel_label=body.channel_label,
        # Falls back to the env-configurable DISCORD_ALERT_MIN_SCORE
        # default when the admin doesn't specify one explicitly, rather
        # than a value hardcoded here that the env var couldn't reach.
        minimum_score=body.minimum_score if body.minimum_score is not None else settings.discord_alert_min_score,
        allowed_chains=body.allowed_chains,
        alert_types=body.alert_types,
        created_by=admin.id,
    )
    db.add(integration)
    await db.commit()
    await db.refresh(integration)
    return integration


@router.get("", response_model=list[DiscordIntegrationOut])
async def list_integrations(admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(DiscordIntegration))
    return result.scalars().all()


@router.post("/{integration_id}/disable", response_model=DiscordIntegrationOut)
async def disable_integration(
    integration_id: str, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(DiscordIntegration).where(DiscordIntegration.id == integration_id))
    integration = result.scalar_one_or_none()
    if integration is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Integration not found.")
    integration.enabled = False
    await db.commit()
    await db.refresh(integration)
    return integration
