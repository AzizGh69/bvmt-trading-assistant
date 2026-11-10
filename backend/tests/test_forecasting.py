"""Forecasts and their diagnostics."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.analytics import forecasting
from app.analytics.forecasting import NotEnoughHistory, adf_test, backtest, ema_path, forecast_stock, rank_orders


def history_from(log_prices: np.ndarray) -> pd.DataFrame:
    n = len(log_prices)
    return pd.DataFrame(
        {
            "date": pd.bdate_range("2023-01-02", periods=n),
            "close": np.exp(log_prices),
            "volume": np.full(n, 5000),
            "traded": True,
        }
    )


def random_walk(n: int = 400, seed: int = 3) -> np.ndarray:
    return np.log(10.0) + np.cumsum(np.random.default_rng(seed).normal(0.0, 0.01, n))


def test_adf_separates_a_random_walk_from_its_returns():
    walk = random_walk()
    assert adf_test(walk)["stationary"] is False
    assert adf_test(np.diff(walk))["stationary"] is True
    assert adf_test(np.ones(100))["stationary"] is None  # a flat series cannot be tested


def test_rank_orders_reports_every_fitted_order():
    candidates, fitted = rank_orders(random_walk(300))
    assert len(candidates) >= 5 and set(fitted) == {c.order for c in candidates}
    assert all(np.isfinite(c.aic) and np.isfinite(c.bic) for c in candidates)


def test_ema_path_follows_the_recent_drift_and_damps():
    rising = np.log(10.0) + 0.01 * np.arange(100)
    path = ema_path(rising, 5)
    steps = np.diff(np.concatenate([[rising[-1]], path]))
    assert np.all(steps > 0) and np.all(np.diff(steps) < 0)


def test_forecast_shape_and_ordered_bands():
    result = forecast_stock(history_from(random_walk()), horizon=5)
    assert len(result["forecast"]) == 5 and result["horizon"] == 5
    assert result["model"]["selected"] in {"arima", "ema", "naive"}
    widths = []
    for point in result["forecast"]:
        assert point["lower95"] <= point["lower80"] <= point["price"] <= point["upper80"] <= point["upper95"]
        widths.append(point["upper95"] - point["lower95"])
    assert widths == sorted(widths)  # uncertainty grows with the horizon
    first = pd.Timestamp(result["forecast"][0]["date"])
    assert first > pd.Timestamp(result["last_session"]) and first.dayofweek < 5
    diagnostics = result["diagnostics"]
    assert diagnostics["adf_log_returns"]["stationary"] is True
    aics = [c["aic"] for c in diagnostics["candidates"]]
    assert aics == sorted(aics) and diagnostics["selected_by_aic"] == diagnostics["candidates"][0]["order"]


def test_backtest_scores_each_model_on_held_out_sessions():
    scores = backtest(random_walk(), (1, 1, 0), horizon=5)
    assert set(scores) == {"arima", "ema", "naive"}
    for name in ("arima", "ema", "naive"):
        assert scores[name]["rmse"] > 0 and scores[name]["origins"] > 10
    assert scores["naive"]["directional_accuracy"] is None  # the random walk predicts no move


def test_a_random_walk_is_not_claimed_to_be_beaten_by_much():
    result = forecast_stock(history_from(random_walk(seed=11)), horizon=5)
    models = result["backtest"]["models"]
    best = models[result["model"]["selected"]]["rmse"]
    assert best <= models["naive"]["rmse"]
    if result["model"]["selected"] == "naive":
        assert result["model"]["beats_random_walk"] is False and result["expected_return_pct"] == 0.0


def test_a_strong_trend_is_picked_up():
    trend = np.log(10.0) + 0.004 * np.arange(400) + np.random.default_rng(5).normal(0, 0.001, 400)
    result = forecast_stock(history_from(trend), horizon=5)
    assert result["model"]["selected"] != "naive" and result["model"]["beats_random_walk"] is True
    assert result["expected_return_pct"] > 0.5


def test_volume_forecast_and_trading_probability():
    history = history_from(random_walk())
    history.loc[history.index[-30:], "traded"] = [True, False] * 15
    volume = forecast_stock(history)["volume"]
    assert volume["lower80"] <= volume["expected"] <= volume["upper80"]
    assert 4000 < volume["expected"] < 6000 and volume["traded_probability"] == 0.75


def test_short_history_and_bad_horizon_are_refused():
    with pytest.raises(NotEnoughHistory):
        forecast_stock(history_from(random_walk(80)))
    with pytest.raises(ValueError):
        forecast_stock(history_from(random_walk()), horizon=0)


def test_api_forecast(client):
    forecasting.clear_cache()
    response = client.get("/api/stocks/alpha/forecast", params={"horizon": 3})
    assert response.status_code == 200
    body = response.json()
    assert body["ticker"] == "ALPHA" and len(body["forecast"]) == 3
    assert client.get("/api/stocks/alpha/forecast", params={"horizon": 3}).json() == body  # served from the cache
    assert client.get("/api/stocks/NOPE/forecast").status_code == 404
    assert client.get("/api/stocks/alpha/forecast", params={"horizon": 99}).status_code == 422
