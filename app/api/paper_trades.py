from datetime import datetime, timezone

from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_current_user
from app.models.paper_trade import PaperTrade
from app.models.token import Token, TokenMetric
from app.models.user import User
from app.paper_trading.simulation import evaluate_exit, realized_return_pct, simulate_entry

router = APIRouter(prefix="/paper-trades", tags=["paper-trading"])


class PaperTradeCreate(BaseModel):
    token_id: str
    signal_alert_id: str | None = None
    position_size_usd: float = 100.0
    stop_loss_pct: float | None = 20.0
    take_profit_pct: float | None = 50.0
    max_holding_minutes: int | None = 1440


class PaperTradeOut(BaseModel):
    id: str
    token_id: str
    status: str
    entry_price: float
    entry_time: datetime
    exit_price: float | None
    exit_time: datetime | None
    exit_reason: str | None
    realized_return_pct: float | None

    class Config:
        from_attributes = True


@router.post("", response_model=PaperTradeOut, status_code=status.HTTP_201_CREATED)
async def open_paper_trade(
    body: PaperTradeCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    latest_metric = (
        await db.execute(
            select(TokenMetric)
            .where(TokenMetric.token_id == body.token_id)
            .order_by(TokenMetric.timestamp.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if latest_metric is None or latest_metric.price is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No price data available for this token yet.")

    sim = simulate_entry(latest_metric.price)

    trade = PaperTrade(
        user_id=user.id,
        token_id=body.token_id,
        signal_alert_id=body.signal_alert_id,
        entry_price=sim.effective_entry_price,
        simulated_slippage_pct=sim.total_friction_pct,
        stop_loss_pct=body.stop_loss_pct,
        take_profit_pct=body.take_profit_pct,
        max_holding_minutes=body.max_holding_minutes,
        position_size_usd=body.position_size_usd,
    )
    db.add(trade)
    await db.commit()
    await db.refresh(trade)
    return trade


@router.get("", response_model=list[PaperTradeOut])
async def list_paper_trades(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(PaperTrade).where(PaperTrade.user_id == user.id).order_by(PaperTrade.created_at.desc())
    )
    return result.scalars().all()


@router.post("/{trade_id}/check-exit", response_model=PaperTradeOut)
async def check_and_maybe_exit(
    trade_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """
    Evaluates stop-loss/take-profit/time-limit against the latest known
    price and closes the trade if triggered. Called on-demand from the
    dashboard rather than by a dedicated always-on worker, per Section 13.
    """
    result = await db.execute(select(PaperTrade).where(PaperTrade.id == trade_id, PaperTrade.user_id == user.id))
    trade = result.scalar_one_or_none()
    if trade is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Paper trade not found.")
    if trade.status != "open":
        return trade

    latest_metric = (
        await db.execute(
            select(TokenMetric)
            .where(TokenMetric.token_id == trade.token_id)
            .order_by(TokenMetric.timestamp.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if latest_metric is None or latest_metric.price is None:
        return trade

    minutes_held = int((datetime.now(timezone.utc) - trade.entry_time.replace(tzinfo=timezone.utc)).total_seconds() // 60)
    should_exit, reason = evaluate_exit(
        trade.entry_price,
        latest_metric.price,
        trade.stop_loss_pct,
        trade.take_profit_pct,
        minutes_held,
        trade.max_holding_minutes,
    )
    if should_exit:
        trade.exit_price = latest_metric.price
        trade.exit_time = datetime.now(timezone.utc)
        trade.exit_reason = reason
        trade.status = "closed"
        trade.realized_return_pct = realized_return_pct(trade.entry_price, latest_metric.price)
        await db.commit()
        await db.refresh(trade)
    return trade
