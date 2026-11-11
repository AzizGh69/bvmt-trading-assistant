"""News: RSS feeds read on demand (opt-in), stored with their sentiment and the tickers they name."""
from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from html import unescape

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .analytics.market import MarketData
from .analytics.sentiment import score_text, tickers_in
from .config import Settings, get_settings
from .models import NewsArticle

log = logging.getLogger("bvmt.news")
_TAG = re.compile(r"<[^>]+>")


class ScrapingDisabled(RuntimeError):
    pass


def _text(node: ET.Element | None) -> str:
    if node is None:
        return ""
    return " ".join(unescape(_TAG.sub(" ", "".join(node.itertext()))).split())


def _date(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def parse_feed(xml_text: str, source: str) -> list[dict]:
    """Items of an RSS 2.0 or Atom feed as ``{source, url, title, summary, published_at}``."""
    root = ET.fromstring(xml_text)
    atom = "{http://www.w3.org/2005/Atom}"
    items = []
    for item in root.iter("item"):
        items.append(
            {
                "source": source,
                "url": (item.findtext("link") or "").strip(),
                "title": _text(item.find("title")),
                "summary": _text(item.find("description"))[:1000],
                "published_at": _date(item.findtext("pubDate") or ""),
            }
        )
    for entry in root.iter(f"{atom}entry"):
        link = entry.find(f"{atom}link")
        items.append(
            {
                "source": source,
                "url": (link.get("href", "") if link is not None else "").strip(),
                "title": _text(entry.find(f"{atom}title")),
                "summary": _text(entry.find(f"{atom}summary"))[:1000],
                "published_at": _date(entry.findtext(f"{atom}updated") or ""),
            }
        )
    return [i for i in items if i["url"] and i["title"]]


def fetch_feeds(settings: Settings | None = None) -> tuple[list[dict], list[str]]:
    """Read every configured feed. A feed that fails is reported, never fatal."""
    settings = settings or get_settings()
    if not settings.enable_scraping:
        raise ScrapingDisabled("live news is off (set ENABLE_SCRAPING=true to read the feeds)")
    articles, errors = [], []
    for url in settings.news_feed_list:
        source = re.sub(r"^https?://(www\.)?", "", url).split("/")[0]
        try:
            response = httpx.get(
                url,
                timeout=settings.scrape_timeout_seconds,
                follow_redirects=True,
                headers={"User-Agent": "bvmt-trading-assistant (educational project)"},
            )
            response.raise_for_status()
            articles.extend(parse_feed(response.text, source))
        except (httpx.HTTPError, ET.ParseError) as exc:
            log.warning("feed %s failed: %s", source, type(exc).__name__)
            errors.append(f"{source}: {type(exc).__name__}")
    return articles, errors


def store_articles(db: Session, market: MarketData, articles: list[dict]) -> int:
    """Score and keep the articles not seen before. Returns how many were new."""
    known = set(db.scalars(select(NewsArticle.url).where(NewsArticle.url.in_([a["url"] for a in articles]))).all())
    added = 0
    for article in articles:
        if article["url"] in known:
            continue
        text = f"{article['title']}. {article['summary']}"
        sentiment = score_text(text)
        db.add(
            NewsArticle(
                source=article["source"],
                url=article["url"][:600],
                title=article["title"],
                summary=article["summary"],
                language=sentiment["language"],
                tickers=tickers_in(text, market),
                score=sentiment["score"],
                label=sentiment["label"],
                method=sentiment["method"],
                published_at=article["published_at"],
            )
        )
        known.add(article["url"])
        added += 1
    db.commit()
    return added


def refresh_news(db: Session, market: MarketData, settings: Settings | None = None) -> dict:
    articles, errors = fetch_feeds(settings)
    return {"fetched": len(articles), "stored": store_articles(db, market, articles), "errors": errors}


def iso_utc(moment: datetime) -> str:
    return (moment if moment.tzinfo else moment.replace(tzinfo=UTC)).isoformat()


def article_out(article: NewsArticle) -> dict:
    return {
        "id": article.id,
        "source": article.source,
        "url": article.url,
        "title": article.title,
        "language": article.language,
        "tickers": article.tickers,
        "score": article.score,
        "label": article.label,
        "method": article.method,
        "published_at": iso_utc(article.published_at or article.created_at),
    }


def recent_articles(db: Session, ticker: str | None = None, days: int = 30, limit: int = 50) -> list[NewsArticle]:
    since = datetime.now(UTC) - timedelta(days=days)
    rows = db.scalars(
        select(NewsArticle).where(NewsArticle.created_at >= since).order_by(NewsArticle.id.desc()).limit(2000)
    ).all()
    if ticker:
        rows = [r for r in rows if ticker in (r.tickers or [])]
    return rows[:limit]


def ticker_sentiment(db: Session, ticker: str, days: int = 30) -> dict:
    """Average sentiment of the recent articles naming a stock, the newest counting most."""
    rows = recent_articles(db, ticker, days=days, limit=50)
    if not rows:
        return {"articles": 0, "score": None, "label": None, "latest": []}
    weights = [0.9**i for i in range(len(rows))]  # newest first
    score = sum(w * r.score for w, r in zip(weights, rows)) / sum(weights)
    return {
        "articles": len(rows),
        "score": round(score, 3),
        "label": "positive" if score > 0.15 else "negative" if score < -0.15 else "neutral",
        "latest": [article_out(r) for r in rows[:5]],
    }
