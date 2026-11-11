"""Forecast endpoint."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ..analytics.forecasting import MAX_HORIZON, NotEnoughHistory, cached_forecast
from .market import market_or_503, resolve_or_404

router = APIRouter(prefix="/api", tags=["forecast"])


@router.get("/stocks/{ticker}/forecast")
def stock_forecast(ticker: str, horizon: int = Query(5, ge=1, le=MAX_HORIZON)) -> dict:
    """Price and volume forecast with ADF, AIC / BIC and walk-forward backtest diagnostics."""
    market = market_or_503()
    symbol = resolve_or_404(market, ticker)
    try:
        return cached_forecast(market, symbol, horizon)
    except NotEnoughHistory as exc:
        raise HTTPException(status_code=422, detail=f"{symbol}: {exc}") from exc
