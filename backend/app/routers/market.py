"""Market overview and per-stock endpoints."""
from __future__ import annotations

import math

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from ..analytics.indicators import technical_frame, technical_summary
from ..analytics.market import MarketData, UnknownTicker, get_market

router = APIRouter(prefix="/api", tags=["market"])


def market_or_503() -> MarketData:
    try:
        market = get_market()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if market.empty:
        raise HTTPException(status_code=503, detail="the price history is empty; check DATA_PARQUET")
    return market


def resolve_or_404(market: MarketData, ticker: str) -> str:
    try:
        return market.resolve(ticker)
    except UnknownTicker as exc:
        raise HTTPException(status_code=404, detail=f"unknown stock: {ticker}") from exc


def records(frame: pd.DataFrame, digits: int = 4) -> list[dict]:
    """JSON-safe rows: ISO dates, rounded floats, NaN as null."""
    out = []
    for row in frame.to_dict("records"):
        clean = {}
        for key, value in row.items():
            if isinstance(value, pd.Timestamp):
                clean[key] = value.date().isoformat()
            elif isinstance(value, float):
                clean[key] = None if math.isnan(value) or math.isinf(value) else round(value, digits)
            elif hasattr(value, "item"):
                clean[key] = value.item()
            else:
                clean[key] = value
        out.append(clean)
    return out


@router.get("/market/overview")
def market_overview(top: int = Query(5, ge=1, le=20), sessions: int = Query(250, ge=20, le=3000)) -> dict:
    """Composite index, breadth, gainers, losers, most active and volumes of the last session."""
    return market_or_503().overview(top=top, index_sessions=sessions)


@router.get("/market/quotes")
def market_quotes() -> dict:
    """Every quote of the last session."""
    market = market_or_503()
    table = market.session_table().sort_values("turnover", ascending=False)
    return {"session": market.last_session.date().isoformat(), "quotes": records(table, digits=3)}


@router.get("/stocks")
def list_stocks(listed_only: bool = True) -> list[dict]:
    market = market_or_503()
    stocks = market.stocks
    if listed_only:
        stocks = stocks[stocks["listed"]]
    return records(stocks[["ticker", "isin", "name", "sector", "market_group", "last_close", "listed"]], digits=3)


@router.get("/stocks/{ticker}")
def stock_detail(ticker: str, sessions: int = Query(250, ge=30, le=3000)) -> dict:
    """Price history with RSI, MACD and Bollinger Bands."""
    market = market_or_503()
    symbol = resolve_or_404(market, ticker)
    # Indicators need a warm-up, so compute on a longer window than is returned.
    history = market.history(symbol, sessions + 60)
    frame = technical_frame(history).tail(sessions)
    last, prev = history.iloc[-1], history.iloc[-2] if len(history) > 1 else history.iloc[-1]
    return {
        **market.info(symbol),
        "quote": {
            "session": last["date"].date().isoformat(),
            "close": round(float(last["close"]), 3),
            "previous_close": round(float(prev["close"]), 3),
            "change_pct": round((float(last["close"]) / float(prev["close"]) - 1.0) * 100.0, 2),
            "volume": int(last["volume"]),
            "turnover": round(float(last["turnover"]), 2),
            "traded": bool(last["traded"]),
        },
        "indicators": technical_summary(history),
        "history": records(frame),
    }
