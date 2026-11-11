"""Portfolio optimisation and the paper-trading account."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import account
from ..analytics.market import UnknownTicker
from ..analytics.portfolio import PROFILES, recommend
from ..config import get_settings
from ..db import get_db
from ..models import Transaction, User
from ..security import current_user, optional_user
from .market import market_or_503

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


class OrderIn(BaseModel):
    ticker: str
    side: str
    quantity: int = Field(gt=0, le=10_000_000)


class ResetIn(BaseModel):
    initial_capital: float = Field(account.DEFAULT_CAPITAL, ge=1_000, le=10_000_000)


def _recommendation(profile: str, capital: float | None) -> dict:
    try:
        return recommend(market_or_503(), profile, get_settings().risk_free_rate, capital)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/recommendation")
def recommendation(
    profile: str | None = Query(None),
    capital: float | None = Query(None, ge=100, le=100_000_000),
    user: User | None = Depends(optional_user),
) -> dict:
    """The mean-variance allocation for a risk profile. Open to anonymous visitors."""
    chosen = profile or (user.risk_profile if user else "moderate")
    if chosen not in PROFILES:
        raise HTTPException(status_code=422, detail=f"profile must be one of {sorted(PROFILES)}")
    return _recommendation(chosen, capital)


@router.get("")
def get_account(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    return account.snapshot(db, user, market_or_503(), get_settings().risk_free_rate)


@router.post("/orders", status_code=201)
def place_order(body: OrderIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    market = market_or_503()
    try:
        transaction = account.place_order(db, user, market, body.ticker, body.side, body.quantity)
    except UnknownTicker as exc:
        raise HTTPException(status_code=404, detail=f"unknown stock: {body.ticker}") from exc
    except account.OrderError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "order": {
            "ticker": transaction.ticker,
            "side": transaction.side,
            "quantity": transaction.quantity,
            "price": round(transaction.price, 3),
            "amount": round(transaction.quantity * transaction.price, 2),
        },
        "account": account.snapshot(db, user, market, get_settings().risk_free_rate),
    }


@router.get("/transactions")
def transactions(limit: int = Query(100, ge=1, le=500), user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(
        select(Transaction).where(Transaction.user_id == user.id).order_by(Transaction.id.desc()).limit(limit)
    ).all()
    return [
        {
            "id": t.id,
            "ticker": t.ticker,
            "side": t.side,
            "quantity": t.quantity,
            "price": round(t.price, 3),
            "amount": round(t.quantity * t.price, 2),
            "session_date": t.session_date.isoformat(),
        }
        for t in rows
    ]


@router.post("/reset")
def reset(body: ResetIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    account.reset(db, user, body.initial_capital)
    return account.snapshot(db, user, market_or_503(), get_settings().risk_free_rate)


@router.post("/apply-recommendation")
def apply_recommendation(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    """Rebalance the paper account to the allocation recommended for the user's profile."""
    market = market_or_503()
    plan = _recommendation(user.risk_profile, None)
    weights = {row["ticker"]: row["weight_pct"] / 100.0 for row in plan["holdings"]}
    try:
        done = account.rebalance(db, user, market, weights)
    except account.OrderError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "orders": len(done),
        "profile": user.risk_profile,
        "account": account.snapshot(db, user, market, get_settings().risk_free_rate),
    }
