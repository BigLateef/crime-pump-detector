from pydantic import BaseModel
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_current_user
from app.models.token import SignalAlert, Token, TokenMetric
from app.models.user import User

router = APIRouter(prefix="/tokens", tags=["tokens"])


class TokenOut(BaseModel):
    id: str
    chain: str
    address: str
    name: str | None
    symbol: str | None
    dex: str | None
    first_seen_at: datetime

    class Config:
        from_attributes = True


class TokenMetricOut(BaseModel):
    timestamp: datetime
    price: float | None
    market_cap: float | None
    liquidity: float | None
    volume: float | None
    holder_count: int | None
    data_status: str

    class Config:
        from_attributes = True


class SignalAlertOut(BaseModel):
    id: str
    token_id: str
    signal_type: str
    score: int
    confidence: str
    payload_json: dict
    detected_at: datetime

    class Config:
        from_attributes = True


@router.get("", response_model=list[TokenOut])
async def list_tokens(
    chain: str | None = None,
    limit: int = Query(default=50, le=200),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Token).order_by(Token.first_seen_at.desc()).limit(limit)
    if chain:
        stmt = stmt.where(Token.chain == chain)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/{token_id}", response_model=TokenOut)
async def get_token(token_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Token).where(Token.id == token_id))
    token = result.scalar_one_or_none()
    if token is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Token not found.")
    return token


@router.get("/{token_id}/metrics", response_model=list[TokenMetricOut])
async def get_token_metrics(
    token_id: str,
    limit: int = Query(default=100, le=1000),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(TokenMetric).where(TokenMetric.token_id == token_id).order_by(TokenMetric.timestamp.desc()).limit(limit)
    )
    return result.scalars().all()


@router.get("/{token_id}/alerts", response_model=list[SignalAlertOut])
async def get_token_alerts(
    token_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(SignalAlert).where(SignalAlert.token_id == token_id).order_by(SignalAlert.detected_at.desc())
    )
    return result.scalars().all()
