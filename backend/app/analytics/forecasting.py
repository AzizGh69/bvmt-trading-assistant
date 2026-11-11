"""Five-day price and volume forecasts with the diagnostics that say how far to trust them.

Three models compete on every stock:

* ``arima``: an ARIMA(p, 1, q) on the log close, its order chosen by AIC among
  a small grid (BIC's choice is reported next to it);
* ``ema``: the exponentially weighted average of recent returns, extrapolated
  with damping;
* ``naive``: the random walk, i.e. "tomorrow equals today". It is the
  benchmark: a model that cannot beat it has no edge on that stock.

They are compared by a walk-forward backtest on sessions none of them was
fitted on, and the published forecast comes from the one with the lowest error
there. Nothing here is tuned to look good: on many illiquid stocks the random
walk wins, and the response says so.
"""
from __future__ import annotations

import math
import warnings
from dataclasses import dataclass

import numpy as np
import pandas as pd
from statsmodels.tsa.arima.model import ARIMA
from statsmodels.tsa.stattools import adfuller

WINDOW = 500  # sessions used for fitting
MIN_HISTORY = 150
BACKTEST_SPAN = 120  # most recent sessions held out for the walk-forward test
BACKTEST_STEP = 5
MAX_HORIZON = 10
ARIMA_ORDERS = [(0, 1, 0), (1, 1, 0), (0, 1, 1), (1, 1, 1), (2, 1, 0), (0, 1, 2), (2, 1, 1)]
EMA_SPAN = 20
EMA_DAMPING = 0.8
Z80, Z95 = 1.2816, 1.96


class NotEnoughHistory(ValueError):
    pass


@dataclass
class Candidate:
    order: tuple[int, int, int]
    aic: float
    bic: float


def adf_test(series: np.ndarray) -> dict:
    """Augmented Dickey-Fuller test. ``stationary`` means the unit root is rejected at 5%."""
    values = np.asarray(series, dtype=float)
    values = values[np.isfinite(values)]
    if len(values) < 30 or np.ptp(values) == 0.0:
        return {"statistic": None, "p_value": None, "lags": None, "stationary": None}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        statistic, p_value, lags, *_ = adfuller(values, autolag="AIC")
    return {
        "statistic": round(float(statistic), 4),
        "p_value": round(float(p_value), 4),
        "lags": int(lags),
        "stationary": bool(p_value < 0.05),
    }


def _fit(y: np.ndarray, order: tuple[int, int, int]):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return ARIMA(y, order=order, trend="n").fit(method_kwargs={"maxiter": 60})


def rank_orders(y: np.ndarray) -> tuple[list[Candidate], dict]:
    """Fit every order of the grid; return the AIC / BIC table and the fitted results."""
    candidates, fitted = [], {}
    for order in ARIMA_ORDERS:
        try:
            result = _fit(y, order)
        except Exception:  # a singular fit on a flat series: skip that order
            continue
        if not (math.isfinite(result.aic) and math.isfinite(result.bic)):
            continue
        candidates.append(Candidate(order, float(result.aic), float(result.bic)))
        fitted[order] = result
    return candidates, fitted


def ema_path(y: np.ndarray, horizon: int) -> np.ndarray:
    """Damped extrapolation of the exponentially weighted mean log return."""
    returns = pd.Series(np.diff(y))
    drift = float(returns.ewm(span=EMA_SPAN, adjust=False).mean().iloc[-1]) if len(returns) else 0.0
    steps = np.cumsum(EMA_DAMPING ** np.arange(1, horizon + 1))
    return y[-1] + drift * steps


def _score(errors: list[float], hits: list[bool]) -> dict:
    if not errors:
        return {"rmse": None, "mae": None, "directional_accuracy": None, "origins": 0}
    err = np.asarray(errors)
    return {
        "rmse": round(float(np.sqrt(np.mean(err**2))), 4),
        "mae": round(float(np.mean(np.abs(err))), 4),
        "directional_accuracy": round(float(np.mean(hits)), 3) if hits else None,
        "origins": int(len(err)),
    }


def backtest(y: np.ndarray, order: tuple[int, int, int], horizon: int) -> dict:
    """Walk forward over the last ``BACKTEST_SPAN`` sessions.

    The ARIMA parameters are estimated once on the sessions before the test
    span, then applied unchanged at each origin, so no forecast has seen the
    sessions it is scored on. Errors are in dinars at the horizon.
    """
    n = len(y)
    start = n - BACKTEST_SPAN
    scores: dict[str, tuple[list[float], list[bool]]] = {"arima": ([], []), "ema": ([], []), "naive": ([], [])}
    try:
        trained = _fit(y[:start], order)
    except Exception:
        trained = None
    for origin in range(start, n - horizon + 1, BACKTEST_STEP):
        past, actual = y[:origin], y[origin + horizon - 1]
        last = past[-1]
        forecasts = {"ema": float(ema_path(past, horizon)[-1]), "naive": float(last)}
        if trained is not None:
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    forecasts["arima"] = float(trained.apply(past).forecast(horizon)[-1])
            except Exception:
                pass
        moved = actual != last
        for name, value in forecasts.items():
            errors, hits = scores[name]
            errors.append(math.exp(value) - math.exp(actual))
            if moved and name != "naive" and value != last:
                hits.append((value > last) == (actual > last))
    return {name: _score(errors, hits) for name, (errors, hits) in scores.items()}


def _future_sessions(last: pd.Timestamp, horizon: int) -> list[str]:
    return [d.date().isoformat() for d in pd.bdate_range(last + pd.Timedelta(days=1), periods=horizon)]


def forecast_volume(history: pd.DataFrame, horizon: int) -> dict:
    """Expected daily volume: the smoothed recent level, with an 80% band from past surprises."""
    volume = history["volume"].astype(float)
    log_volume = np.log1p(volume)
    level = log_volume.ewm(span=EMA_SPAN, adjust=False).mean()
    surprise = (log_volume - level.shift(1)).tail(120).std(ddof=0)
    surprise = 0.0 if not math.isfinite(surprise) else float(surprise)
    centre = float(level.iloc[-1])
    traded = history["traded"].tail(60)
    return {
        "expected": int(round(math.expm1(centre))),
        "lower80": int(round(max(0.0, math.expm1(centre - Z80 * surprise)))),
        "upper80": int(round(math.expm1(centre + Z80 * surprise))),
        "average_20_sessions": int(round(float(volume.tail(20).mean()))),
        "traded_probability": round(float(traded.mean()), 3) if len(traded) else None,
        "horizon": horizon,
    }


def forecast_stock(history: pd.DataFrame, horizon: int = 5) -> dict:
    """Forecast one stock from its tidy history (columns: date, close, volume, traded)."""
    if not 1 <= horizon <= MAX_HORIZON:
        raise ValueError(f"horizon must be between 1 and {MAX_HORIZON}")
    history = history.tail(WINDOW).reset_index(drop=True)
    if len(history) < MIN_HISTORY:
        raise NotEnoughHistory(f"needs at least {MIN_HISTORY} sessions, found {len(history)}")
    close = history["close"].astype(float).to_numpy()
    if np.any(close <= 0):
        raise NotEnoughHistory("the history contains non-positive prices")
    y = np.log(close)
    returns = np.diff(y)

    candidates, fitted = rank_orders(y)
    by_aic = min(candidates, key=lambda c: c.aic) if candidates else None
    by_bic = min(candidates, key=lambda c: c.bic) if candidates else None
    order = by_aic.order if by_aic else (0, 1, 0)

    scores = backtest(y, order, horizon)
    ranked = sorted((s["rmse"], name) for name, s in scores.items() if s["rmse"] is not None)
    # Ties go to the simpler model: naive, then ema, then arima.
    simplicity = {"naive": 0, "ema": 1, "arima": 2}
    best = min(ranked, key=lambda item: (round(item[0], 4), simplicity[item[1]]))[1] if ranked else "naive"
    if best == "arima" and order not in fitted:
        best = "naive"

    sigma = float(np.std(returns[-250:], ddof=0)) if len(returns) else 0.0
    steps = np.arange(1, horizon + 1)
    if best == "arima":
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            prediction = fitted[order].get_forecast(horizon)
            centre = np.asarray(prediction.predicted_mean, dtype=float)
            band80 = np.asarray(prediction.conf_int(alpha=0.20), dtype=float)
            band95 = np.asarray(prediction.conf_int(alpha=0.05), dtype=float)
        lower80, upper80, lower95, upper95 = band80[:, 0], band80[:, 1], band95[:, 0], band95[:, 1]
    else:
        centre = ema_path(y, horizon) if best == "ema" else np.full(horizon, y[-1])
        spread = sigma * np.sqrt(steps)
        lower80, upper80 = centre - Z80 * spread, centre + Z80 * spread
        lower95, upper95 = centre - Z95 * spread, centre + Z95 * spread

    last_session = pd.Timestamp(history["date"].iloc[-1])
    last_close = float(close[-1])
    path = [
        {
            "date": date,
            "price": round(math.exp(centre[i]), 3),
            "lower80": round(math.exp(lower80[i]), 3),
            "upper80": round(math.exp(upper80[i]), 3),
            "lower95": round(math.exp(lower95[i]), 3),
            "upper95": round(math.exp(upper95[i]), 3),
        }
        for i, date in enumerate(_future_sessions(last_session, horizon))
    ]
    expected_return = path[-1]["price"] / last_close - 1.0
    naive_rmse, best_rmse = scores["naive"]["rmse"], scores[best]["rmse"]
    return {
        "last_session": last_session.date().isoformat(),
        "last_close": round(last_close, 3),
        "horizon": horizon,
        "sessions_used": int(len(history)),
        "model": {
            "selected": best,
            "arima_order": list(order),
            "beats_random_walk": bool(
                best != "naive" and naive_rmse is not None and best_rmse is not None and best_rmse < naive_rmse
            ),
        },
        "expected_return_pct": round(expected_return * 100.0, 2),
        "daily_volatility_pct": round(sigma * 100.0, 3),
        "forecast": path,
        "diagnostics": {
            "adf_log_price": adf_test(y),
            "adf_log_returns": adf_test(returns),
            "candidates": [
                {"order": list(c.order), "aic": round(c.aic, 2), "bic": round(c.bic, 2)}
                for c in sorted(candidates, key=lambda c: c.aic)
            ],
            "selected_by_aic": list(by_aic.order) if by_aic else None,
            "selected_by_bic": list(by_bic.order) if by_bic else None,
        },
        "backtest": {
            "span_sessions": BACKTEST_SPAN,
            "step_sessions": BACKTEST_STEP,
            "horizon": horizon,
            "unit": "TND",
            "models": scores,
        },
        "volume": forecast_volume(history, horizon),
    }


# ----------------------------------------------------------------- caching
_cache: dict[tuple[str, int, str], dict] = {}


def cached_forecast(market, ticker: str, horizon: int = 5) -> dict:
    """Forecast through a small cache keyed by the last session, so each stock is fitted once."""
    symbol = market.resolve(ticker)
    key = (symbol, horizon, market.last_session.date().isoformat())
    if key not in _cache:
        if len(_cache) > 400:
            _cache.clear()
        _cache[key] = {"ticker": symbol, **forecast_stock(market.history(symbol), horizon)}
    return _cache[key]


def clear_cache() -> None:
    _cache.clear()
