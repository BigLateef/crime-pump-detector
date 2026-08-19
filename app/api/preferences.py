from pydantic import BaseModel
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.tokens import SignalAlertOut
from app.core.db import get_db
from app.core.deps import get_current_user
from app.models.token import SignalAlert
from app.models.user import User, UserPreference

router = APIRouter(tags=["alerts-and-preferences"])


@router.get("/alerts", response_model=list[SignalAlertOut])
async def alert_history(
    signal_type: str | None = None,
    min_score: int = Query(default=0, ge=0, le=100),
    limit: int = Query(default=50, le=200),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(SignalAlert).where(SignalAlert.score >= min_score).order_by(SignalAlert.detected_at.desc()).limit(limit)
    if signal_type:
        stmt = stmt.where(SignalAlert.signal_type == signal_type)
    result = await db.execute(stmt)
    return result.scalars().all()


class PreferencesUpdate(BaseModel):
    alert_threshold: int | None = None
    selected_chains: list[str] | None = None
    watchlists: dict | None = None
    discord_preferences: dict | None = None


class PreferencesOut(BaseModel):
    alert_threshold: int
    selected_chains: list
    watchlists: dict
    discord_preferences: dict
    updated_at: datetime

    class Config:
        from_attributes = True


@router.get("/preferences", response_model=PreferencesOut)
async def get_preferences(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(UserPreference).where(UserPreference.user_id == user.id))
    prefs = result.scalar_one_or_none()
    if prefs is None:
        prefs = UserPreference(user_id=user.id)
        db.add(prefs)
        await db.commit()
        await db.refresh(prefs)
    return prefs


@router.patch("/preferences", response_model=PreferencesOut)
async def update_preferences(
    body: PreferencesUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(UserPreference).where(UserPreference.user_id == user.id))
    prefs = result.scalar_one_or_none()
    if prefs is None:
        prefs = UserPreference(user_id=user.id)
        db.add(prefs)

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(prefs, field, value)

    await db.commit()
    await db.refresh(prefs)
    return prefs
