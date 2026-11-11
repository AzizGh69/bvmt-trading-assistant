"""Portfolio construction and risk: Markowitz optimisation, its explanation and stress tests.

Everything here is a pure function of return series and weights, so it is
tested without a database. Returns come from ``MarketData.returns_matrix``,
where one-day moves that look like corporate actions are already blanked.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from sklearn.covariance import LedoitWolf

from .market import MarketData

TRADING_DAYS = 250
LOOKBACK = 500
MIN_TRADED_SHARE = 0.7  # of the lookback sessions
UNIVERSE_SIZE = 40
MEAN_SHRINKAGE = 0.7  # pull each stock's mean return most of the way to the cross-section's

# Risk aversion and the largest weight one stock may take, per investor profile.
PROFILES = {
    "conservative": {"risk_aversion": 12.0, "max_weight": 0.15},
    "moderate": {"risk_aversion": 5.0, "max_weight": 0.25},
    "aggressive": {"risk_aversion": 2.0, "max_weight": 0.35},
}

QUESTIONS = {
    "horizon": ["short", "medium", "long"],  # under 1 year / 1 to 5 years / over 5 years
    "loss_reaction": ["sell", "hold", "buy_more"],  # after a 10% drop
    "experience": ["none", "some", "experienced"],
}


def profile_from_answers(answers: dict) -> str:
    """Score the three sign-up questions (0 to 2 each) into a risk profile."""
    score = 0
    for question, choices in QUESTIONS.items():
        answer = answers.get(question)
        if answer not in choices:
            raise ValueError(f"{question} must be one of {choices}")
        score += choices.index(answer)
    return "conservative" if score <= 2 else "moderate" if score <= 4 else "aggressive"


# ------------------------------------------------------------------ inputs
def select_universe(market: MarketData, lookback: int = LOOKBACK, size: int = UNIVERSE_SIZE) -> list[str]:
    """Listed stocks that traded on most recent sessions, the most liquid first."""
    sessions = market.sessions[-min(len(market.sessions), lookback) :]
    frame = market.prices[market.prices["date"].isin(sessions) & market.prices["ticker"].isin(market.tickers())]
    stats = frame.groupby("ticker").agg(traded=("traded", "mean"), count=("date", "size"), turnover=("turnover", "sum"))
    enough = stats[(stats["count"] >= 0.9 * len(sessions)) & (stats["traded"] >= MIN_TRADED_SHARE)]
    return enough.sort_values("turnover", ascending=False).head(size).index.tolist()


def estimate(returns: pd.DataFrame) -> tuple[pd.Series, pd.DataFrame]:
    """Annualised expected returns (shrunk) and covariance (Ledoit-Wolf) from daily returns."""
    clean = returns.fillna(0.0)
    daily_mean = clean.mean()
    shrunk = (1.0 - MEAN_SHRINKAGE) * daily_mean + MEAN_SHRINKAGE * float(daily_mean.mean())
    covariance = LedoitWolf().fit(clean.to_numpy()).covariance_
    return shrunk * TRADING_DAYS, pd.DataFrame(covariance * TRADING_DAYS, index=returns.columns, columns=returns.columns)


def universe_returns(market: MarketData, tickers: list[str], lookback: int = LOOKBACK) -> pd.DataFrame:
    return market.returns_matrix[tickers].tail(lookback)


# -------------------------------------------------------------- optimiser
def optimise(mu: pd.Series, cov: pd.DataFrame, risk_aversion: float, max_weight: float) -> pd.Series:
    """Long-only mean-variance weights: maximise ``w.mu - (risk_aversion / 2) * w'Cov w``."""
    n = len(mu)
    if n == 0:
        raise ValueError("no stock to optimise over")
    cap = max(max_weight, 1.0 / n + 1e-9)  # the cap must leave a feasible portfolio
    m, c = mu.to_numpy(), cov.to_numpy()

    def objective(w: np.ndarray) -> float:
        return float(-(w @ m) + 0.5 * risk_aversion * (w @ c @ w))

    def gradient(w: np.ndarray) -> np.ndarray:
        return -m + risk_aversion * (c @ w)

    result = minimize(
        objective,
        np.full(n, 1.0 / n),
        jac=gradient,
        method="SLSQP",
        bounds=[(0.0, cap)] * n,
        constraints=[{"type": "eq", "fun": lambda w: w.sum() - 1.0, "jac": lambda w: np.ones(n)}],
        options={"maxiter": 500, "ftol": 1e-10},
    )
    weights = np.clip(result.x, 0.0, cap)
    weights[weights < 1e-4] = 0.0
    return pd.Series(weights / weights.sum(), index=mu.index)


def frontier(mu: pd.Series, cov: pd.DataFrame, max_weight: float, points: int = 12) -> list[dict]:
    """Risk / return of the optimal portfolio for a range of risk aversions."""
    out = []
    for aversion in np.geomspace(0.5, 60.0, points):
        weights = optimise(mu, cov, float(aversion), max_weight)
        out.append(
            {
                "risk_aversion": round(float(aversion), 2),
                "volatility_pct": round(math.sqrt(float(weights @ cov @ weights)) * 100.0, 2),
                "return_pct": round(float(weights @ mu) * 100.0, 2),
            }
        )
    return out


def explain(weights: pd.Series, mu: pd.Series, cov: pd.DataFrame) -> list[dict]:
    """Why each holding is there: its share of the expected return and of the risk.

    Expected return is additive, so each holding's Shapley value is exactly
    ``weight * expected return``. Risk is not additive; the Euler decomposition
    ``w_i * (Cov w)_i / variance`` gives shares that sum to one.
    """
    held = weights[weights > 0]
    variance = float(weights @ cov @ weights)
    marginal = cov @ weights
    total_return = float(weights @ mu)
    rows = []
    for ticker, weight in held.sort_values(ascending=False).items():
        return_part = float(weight * mu[ticker])
        risk_share = float(weight * marginal[ticker] / variance) if variance > 0 else 0.0
        volatility = math.sqrt(float(cov.loc[ticker, ticker]))
        # A holding earns its place by adding more return than risk, or by diversifying.
        if risk_share < 0.8 * weight:
            reason = "diversifier"
        elif total_return > 0 and return_part / total_return > 1.2 * weight:
            reason = "return_driver"
        else:
            reason = "core"
        rows.append(
            {
                "ticker": ticker,
                "weight_pct": round(float(weight) * 100.0, 2),
                "expected_return_pct": round(float(mu[ticker]) * 100.0, 2),
                "volatility_pct": round(volatility * 100.0, 2),
                "return_contribution_pct": round(return_part * 100.0, 2),
                "risk_share_pct": round(risk_share * 100.0, 2),
                "reason": reason,
            }
        )
    return rows


# ------------------------------------------------------------------- risk
def max_drawdown(values: np.ndarray) -> float:
    """Largest peak-to-trough fall of a value series, as a negative fraction."""
    if len(values) == 0:
        return 0.0
    peaks = np.maximum.accumulate(values)
    return float(np.min(values / peaks - 1.0))


def risk_metrics(daily_returns: pd.Series, risk_free_rate: float, value: float = 0.0) -> dict:
    """Realised statistics of a daily return series (of a fixed allocation or an account)."""
    series = daily_returns.dropna()
    if len(series) < 20:
        return {key: None for key in ("annual_return_pct", "volatility_pct", "sharpe", "max_drawdown_pct", "var95_pct", "cvar95_pct", "var95_tnd")}
    annual_return = float(series.mean()) * TRADING_DAYS
    volatility = float(series.std(ddof=0)) * math.sqrt(TRADING_DAYS)
    var95 = float(-np.quantile(series, 0.05))
    tail = series[series <= -var95]
    cvar95 = float(-tail.mean()) if len(tail) else var95
    curve = np.cumprod(1.0 + series.to_numpy())
    return {
        "annual_return_pct": round(annual_return * 100.0, 2),
        "volatility_pct": round(volatility * 100.0, 2),
        "sharpe": round((annual_return - risk_free_rate) / volatility, 3) if volatility > 0 else None,
        "max_drawdown_pct": round(max_drawdown(curve) * 100.0, 2),
        "var95_pct": round(var95 * 100.0, 2),
        "cvar95_pct": round(cvar95 * 100.0, 2),
        "var95_tnd": round(var95 * value, 2) if value else None,
    }


def allocation_returns(returns: pd.DataFrame, weights: pd.Series) -> pd.Series:
    """Daily returns of holding ``weights`` (rebalanced daily) over the given sessions."""
    held = weights[weights > 0]
    return (returns[held.index].fillna(0.0) * held).sum(axis=1)


def stress_tests(market: MarketData, weights: pd.Series) -> list[dict]:
    """What the allocation would lose in bad episodes, real and hypothetical."""
    held = weights[weights > 0]
    if held.empty:
        return []
    returns = market.returns_matrix
    index = market.composite_index.set_index("date")["value"]
    scenarios = []

    def replay(name: str, start: pd.Timestamp, end: pd.Timestamp, market_move: float) -> dict:
        window = returns.loc[start:end, [t for t in held.index if t in returns.columns]]
        per_stock = (1.0 + window.fillna(0.0)).prod() - 1.0
        # A stock with no quotes in the window is assumed to have moved with the market.
        covered = window.notna().any()
        per_stock = per_stock.where(covered, market_move).reindex(held.index).fillna(market_move)
        return {
            "name": name,
            "kind": "historical",
            "from": start.date().isoformat(),
            "to": end.date().isoformat(),
            "market_pct": round(market_move * 100.0, 2),
            "portfolio_pct": round(float((per_stock * held).sum()) * 100.0, 2),
        }

    if len(index) > 25:
        over20 = index / index.shift(20) - 1.0
        end = over20.idxmin()
        start = index.index[index.index.get_loc(end) - 20 + 1]
        scenarios.append(replay("worst_20_sessions", start, end, float(over20.min())))
        daily = index.pct_change()
        worst_day = daily.idxmin()
        scenarios.append(replay("worst_session", worst_day, worst_day, float(daily.min())))

    scenarios.append(
        {"name": "market_minus_10", "kind": "hypothetical", "market_pct": -10.0, "portfolio_pct": round(-10.0 * float(held.sum()), 2)}
    )
    sectors = market.stocks.set_index("ticker")["sector"].reindex(held.index)
    by_sector = held.groupby(sectors).sum().sort_values(ascending=False)
    if len(by_sector):
        top, share = str(by_sector.index[0]), float(by_sector.iloc[0])
        scenarios.append(
            {
                "name": "largest_sector_minus_15",
                "kind": "hypothetical",
                "sector": top,
                "sector_weight_pct": round(share * 100.0, 2),
                "portfolio_pct": round(-15.0 * share, 2),
            }
        )
    return scenarios


def out_of_sample(returns: pd.DataFrame, risk_aversion: float, max_weight: float, risk_free_rate: float) -> dict | None:
    """Choose weights on the first half of the window, score them on the second.

    The figures computed on the estimation window itself flatter the optimiser,
    which by construction picks what did well there. This is the honest check:
    how an allocation chosen a year ago went on to behave, next to simply
    holding every stock of the universe in equal parts.
    """
    half = len(returns) // 2
    if half < 60:
        return None
    train, test = returns.iloc[:half], returns.iloc[half:]
    mu, cov = estimate(train)
    weights = optimise(mu, cov, risk_aversion, max_weight)
    equal = pd.Series(1.0 / returns.shape[1], index=returns.columns)
    return {
        "chosen_on": [train.index[0].date().isoformat(), train.index[-1].date().isoformat()],
        "scored_on": [test.index[0].date().isoformat(), test.index[-1].date().isoformat()],
        "portfolio": risk_metrics(allocation_returns(test, weights), risk_free_rate),
        "equal_weight": risk_metrics(allocation_returns(test, equal), risk_free_rate),
    }


# ------------------------------------------------------------ whole answer
def recommend(market: MarketData, profile: str, risk_free_rate: float, capital: float | None = None) -> dict:
    """The optimal allocation for a profile, with its explanation, risk and stress tests."""
    if profile not in PROFILES:
        raise ValueError(f"profile must be one of {sorted(PROFILES)}")
    settings = PROFILES[profile]
    tickers = select_universe(market)
    if len(tickers) < 3:
        raise ValueError("not enough liquid stocks to build a portfolio")
    returns = universe_returns(market, tickers)
    mu, cov = estimate(returns)
    weights = optimise(mu, cov, settings["risk_aversion"], settings["max_weight"])
    holdings = explain(weights, mu, cov)
    stocks = market.stocks.set_index("ticker")
    for row in holdings:
        row["name"] = str(stocks.loc[row["ticker"], "name"])
        row["sector"] = str(stocks.loc[row["ticker"], "sector"])
        row["last_close"] = round(float(stocks.loc[row["ticker"], "last_close"]), 3)
        if capital:
            row["shares"] = int(capital * row["weight_pct"] / 100.0 // row["last_close"])
            row["amount_tnd"] = round(row["shares"] * row["last_close"], 2)
    history = allocation_returns(returns, weights)
    curve = (1.0 + history).cumprod()
    expected_return, variance = float(weights @ mu), float(weights @ cov @ weights)
    return {
        "profile": profile,
        "session": market.last_session.date().isoformat(),
        "universe": {"stocks": len(tickers), "lookback_sessions": int(len(returns))},
        "assumptions": {**settings, "risk_free_rate": risk_free_rate, "mean_shrinkage": MEAN_SHRINKAGE},
        "expected": {
            "return_pct": round(expected_return * 100.0, 2),
            "volatility_pct": round(math.sqrt(variance) * 100.0, 2),
            "sharpe": round((expected_return - risk_free_rate) / math.sqrt(variance), 3) if variance > 0 else None,
        },
        "holdings": holdings,
        # Measured on the sessions the weights were chosen on: an upper bound, not a promise.
        "in_sample": risk_metrics(history, risk_free_rate, capital or 0.0),
        "out_of_sample": out_of_sample(returns, settings["risk_aversion"], settings["max_weight"], risk_free_rate),
        "history": [{"date": d.date().isoformat(), "value": round(float(v) * 100.0, 2)} for d, v in curve.iloc[::5].items()],
        "frontier": frontier(mu, cov, settings["max_weight"]),
        "stress_tests": stress_tests(market, weights),
    }
