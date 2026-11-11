"""Surveillance endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Query

from ..analytics.anomalies import SCAN_SESSIONS, SEVERITIES, cached_scan, filter_alerts
from .market import market_or_503, records, resolve_or_404

router = APIRouter(prefix="/api", tags=["anomalies"])

SEVERITY_PATTERN = "^(" + "|".join(SEVERITIES) + ")$"


def _payload(market, alerts, limit: int) -> dict:
    counts = alerts["severity"].value_counts()
    return {
        "session": market.last_session.date().isoformat(),
        "scanned_sessions": SCAN_SESSIONS,
        "total": int(len(alerts)),
        "by_severity": {severity: int(counts.get(severity, 0)) for severity in reversed(SEVERITIES)},
        "alerts": records(alerts.head(limit), digits=4),
    }


@router.get("/anomalies")
def market_anomalies(
    sessions: int = Query(20, ge=1, le=SCAN_SESSIONS),
    min_severity: str = Query("medium", pattern=SEVERITY_PATTERN),
    limit: int = Query(100, ge=1, le=500),
) -> dict:
    """Flagged sessions across the market, most severe first."""
    market = market_or_503()
    alerts = filter_alerts(cached_scan(market), market, sessions=sessions, min_severity=min_severity)
    return _payload(market, alerts, limit)


@router.get("/stocks/{ticker}/anomalies")
def stock_anomalies(
    ticker: str,
    sessions: int = Query(SCAN_SESSIONS, ge=1, le=SCAN_SESSIONS),
    min_severity: str = Query("low", pattern=SEVERITY_PATTERN),
) -> dict:
    market = market_or_503()
    symbol = resolve_or_404(market, ticker)
    alerts = filter_alerts(cached_scan(market), market, sessions=sessions, min_severity=min_severity, ticker=symbol)
    return {"ticker": symbol, **_payload(market, alerts.sort_values("date", ascending=False), limit=500)}
