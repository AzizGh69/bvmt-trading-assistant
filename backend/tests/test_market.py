"""Market data layer and the market / stock endpoints."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.analytics.market import INDEX_BASE, MarketData, UnknownTicker


def test_resolve_accepts_ticker_isin_and_name(market):
    assert market.resolve("alpha") == "ALPHA"
    assert market.resolve("TN0000000001") == "BETA"
    assert market.resolve("Gamma") == "GAMMA"
    with pytest.raises(UnknownTicker):
        market.resolve("NOPE")


def test_history_is_sorted_and_limited(market):
    history = market.history("ALPHA", 30)
    assert len(history) == 30
    assert history["date"].is_monotonic_increasing
    assert history["date"].iloc[-1] == market.last_session


def test_session_table_change(market):
    table = market.session_table().set_index("ticker")
    history = market.history("DELTA")
    expected = (history["close"].iloc[-1] / history["close"].iloc[-2] - 1) * 100
    assert np.isclose(table.loc["DELTA", "change_pct"], expected)


def test_composite_index_chains_weighted_returns(prices):
    # Two shares, equal constant turnover: the index return is the mean of their returns.
    dates = pd.bdate_range("2025-01-01", periods=12)
    a = pd.DataFrame({"date": dates, "ticker": "A", "close": 10 * 1.01 ** np.arange(12), "turnover": 1000.0})
    b = pd.DataFrame({"date": dates, "ticker": "B", "close": 20 * 0.99 ** np.arange(12), "turnover": 1000.0})
    frame = pd.concat([a, b])
    frame["isin"], frame["name"], frame["market_group"] = frame["ticker"], frame["ticker"], 11
    for column in ("open", "high", "low"):
        frame[column] = frame["close"]
    frame["volume"], frame["trades"], frame["traded"] = 100, 1, True
    index = MarketData(frame).composite_index
    assert index["value"].iloc[0] == INDEX_BASE
    # weights need 5 sessions of turnover history before the index starts moving
    assert np.allclose(index["return"].iloc[6:], 0.0, atol=1e-12)
    assert np.isclose(index["value"].iloc[-1], INDEX_BASE)


def test_composite_index_ignores_corporate_action_jumps():
    dates = pd.bdate_range("2025-01-01", periods=10)
    close = np.array([10.0] * 7 + [5.0] * 3)  # a 2-for-1 split on day 8
    frame = pd.DataFrame({"date": dates, "ticker": "A", "close": close, "turnover": 1000.0})
    frame["isin"], frame["name"], frame["market_group"] = "A", "A", 11
    for column in ("open", "high", "low"):
        frame[column] = frame["close"]
    frame["volume"], frame["trades"], frame["traded"] = 100, 1, True
    index = MarketData(frame).composite_index
    assert np.isclose(index["value"].iloc[-1], INDEX_BASE)


def test_overview_shape(market):
    overview = market.overview(top=3, index_sessions=50)
    assert overview["session"] == market.last_session.date().isoformat()
    assert len(overview["index"]["history"]) == 50
    assert len(overview["gainers"]) == 3 and len(overview["losers"]) == 3
    assert overview["gainers"][0]["change_pct"] >= overview["gainers"][-1]["change_pct"]
    assert overview["losers"][0]["change_pct"] <= overview["losers"][-1]["change_pct"]
    breadth = overview["breadth"]
    assert breadth["advancing"] + breadth["declining"] + breadth["unchanged"] == breadth["traded"]
    assert overview["totals"]["volume"] == int(market.session_table()["volume"].sum())


def test_api_health_and_market(client):
    health = client.get("/health").json()
    assert health["status"] == "ok" and health["rows"] > 0 and health["llm_configured"] is False

    overview = client.get("/api/market/overview", params={"top": 2, "sessions": 30})
    assert overview.status_code == 200
    body = overview.json()
    assert len(body["gainers"]) == 2 and len(body["index"]["history"]) == 30

    stocks = client.get("/api/stocks").json()
    assert {s["ticker"] for s in stocks} == {"ALPHA", "BETA", "GAMMA", "DELTA", "EPSILON", "ZETA"}
    assert all(s["sector"] == "Other" for s in stocks)  # synthetic tickers are not in the sector map

    quotes = client.get("/api/market/quotes").json()
    assert len(quotes["quotes"]) == 6


def test_api_stock_detail(client):
    response = client.get("/api/stocks/alpha", params={"sessions": 60})
    assert response.status_code == 200
    body = response.json()
    assert body["ticker"] == "ALPHA" and len(body["history"]) == 60
    last = body["history"][-1]
    for key in ("rsi", "macd", "signal", "histogram", "bb_upper", "bb_lower"):
        assert last[key] is not None
    assert body["indicators"]["rsi"] == last["rsi"]
    assert client.get("/api/stocks/NOPE").status_code == 404
