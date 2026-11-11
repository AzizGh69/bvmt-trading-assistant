"""Sentiment of any text, and the news read from the configured feeds."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import news
from ..analytics.sentiment import score_text, tickers_in
from ..config import get_settings
from ..db import get_db
from ..models import User
from ..security import current_user
from .market import market_or_503

router = APIRouter(prefix="/api", tags=["sentiment"])


class TextIn(BaseModel):
    text: str = Field(min_length=3, max_length=2000)


@router.post("/sentiment/analyze")
def analyze(body: TextIn) -> dict:
    """Score a headline or a post in French, Arabic or Tunizi. Nothing is stored."""
    return {**score_text(body.text), "tickers": tickers_in(body.text, market_or_503())}


@router.get("/news")
def list_news(
    ticker: str | None = None,
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict:
    symbol = market_or_503().resolve(ticker) if ticker else None
    rows = news.recent_articles(db, symbol, days=days, limit=limit)
    return {"scraping_enabled": get_settings().enable_scraping, "articles": [news.article_out(r) for r in rows]}


@router.post("/news/refresh")
def refresh(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    """Read the feeds now. Only when ENABLE_SCRAPING is on."""
    try:
        return news.refresh_news(db, market_or_503())
    except news.ScrapingDisabled as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
