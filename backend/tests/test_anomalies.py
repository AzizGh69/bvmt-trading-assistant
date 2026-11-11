"""Surveillance detectors."""
from __future__ import annotations

import pandas as pd

from app.analytics import anomalies
from app.analytics.anomalies import filter_alerts, scan, stock_signal
from app.analytics.market import MarketData


def with_event(prices: pd.DataFrame, ticker: str, offset: int, *, volume_x: float = 1.0, move: float = 0.0) -> pd.DataFrame:
    """Multiply one session's volume and shift its close (and every later close) by ``move``."""
    frame = prices.copy()
    rows = frame.index[frame["ticker"] == ticker]
    target = rows[offset]
    frame.loc[target, "volume"] = int(frame.loc[target, "volume"] * volume_x)
    later = rows[rows >= target]
    for column in ("open", "high", "low", "close"):
        frame.loc[later, column] = frame.loc[later, column] * (1.0 + move)
    frame.loc[target, "open"] = frame.loc[rows[offset - 1], "close"]
    frame.loc[target, "low"] = min(frame.loc[target, "low"], frame.loc[target, "open"])
    frame.loc[target, "high"] = max(frame.loc[target, "high"], frame.loc[target, "open"])
    return frame


def alert_for(alerts: pd.DataFrame, ticker: str, date) -> pd.Series:
    match = alerts[(alerts["ticker"] == ticker) & (alerts["date"] == date)]
    assert len(match) == 1, f"expected one alert on {ticker} {date}, got {len(match)}"
    return match.iloc[0]


def test_a_volume_spike_with_a_price_jump_is_severe(prices):
    date = prices[prices["ticker"] == "GAMMA"]["date"].iloc[-10]
    market = MarketData(with_event(prices, "GAMMA", -10, volume_x=15, move=0.09))
    alert = alert_for(scan(market), "GAMMA", date)
    assert {"volume_spike", "price_move"} <= set(alert["kinds"])
    assert alert["severity"] in {"high", "critical"} and alert["volume_z"] > 6 and 6 < alert["change_pct"] < 13
    assert "GAMMA" in alert["message"]


def test_a_volume_spike_alone_is_flagged_but_not_critical(prices):
    date = prices[prices["ticker"] == "ZETA"]["date"].iloc[-30]
    alert = alert_for(scan(MarketData(with_event(prices, "ZETA", -30, volume_x=6))), "ZETA", date)
    assert "volume_spike" in alert["kinds"] and "price_move" not in alert["kinds"]
    assert alert["severity"] != "critical"


def test_a_huge_jump_is_a_corporate_action_not_a_price_alert(prices):
    date = prices[prices["ticker"] == "DELTA"]["date"].iloc[-20]
    alert = alert_for(scan(MarketData(with_event(prices, "DELTA", -20, move=-0.40))), "DELTA", date)
    assert alert["kinds"] == ["corporate_action"] and alert["severity"] == "low"
    assert "corporate action" in alert["message"]


def test_ordinary_trading_raises_few_alerts(market):
    alerts = scan(market)
    sessions_scanned = 6 * anomalies.SCAN_SESSIONS
    assert len(alerts) < 0.08 * sessions_scanned
    assert not (alerts["severity"] == "critical").any()
    ranks = alerts["severity"].map({s: i for i, s in enumerate(anomalies.SEVERITIES)}).tolist()
    assert ranks == sorted(ranks, reverse=True)  # most severe first


def test_filters_and_stock_signal(prices):
    market = MarketData(with_event(prices, "BETA", -2, volume_x=20, move=0.07))
    anomalies.clear_cache()
    alerts = anomalies.cached_scan(market)
    recent = filter_alerts(alerts, market, sessions=5, min_severity="high")
    assert set(recent["ticker"]) == {"BETA"}
    signal = stock_signal(market, "beta")
    assert signal["severity"] in {"high", "critical"} and signal["count"] >= 1
    assert stock_signal(market, "ALPHA", sessions=1)["severity"] in {None, "low", "medium"}
    anomalies.clear_cache()


def test_api_anomalies(client):
    anomalies.clear_cache()
    body = client.get("/api/anomalies", params={"sessions": 250, "min_severity": "low"}).json()
    assert body["total"] == sum(body["by_severity"].values()) and len(body["alerts"]) <= 100
    if body["alerts"]:
        first = body["alerts"][0]
        assert {"date", "ticker", "kinds", "severity", "score", "message"} <= set(first)
    stock = client.get("/api/stocks/alpha/anomalies").json()
    assert stock["ticker"] == "ALPHA" and all(a["ticker"] == "ALPHA" for a in stock["alerts"])
    assert client.get("/api/anomalies", params={"min_severity": "nope"}).status_code == 422
    assert client.get("/api/stocks/NOPE/anomalies").status_code == 404
