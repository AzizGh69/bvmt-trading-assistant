"""The decision engine: three directional signals, one warning signal, then safety rules.

The idea of combining forecast, technical, sentiment and anomaly signals into a
buy / hold / sell call with explicit safety rules comes from Tradeili (The
Overfitters). This is a reimplementation with its own scoring.

Every signal is a score in [-1, 1] with a weight. The forecast only counts when
its model beat the random walk on the backtest; news only counts when there is
some; an anomaly is not a direction, it is a reason to wait. Weights can be
tilted per user by the feedback policy (``trust``), never past the safety rules.
"""
from __future__ import annotations

import math

BASE_WEIGHTS = {"forecast": 0.4, "technical": 0.35, "sentiment": 0.25}
THRESHOLDS = {"conservative": 0.35, "moderate": 0.25, "aggressive": 0.15}
MAX_WEIGHT = {"conservative": 0.15, "moderate": 0.25, "aggressive": 0.35}  # as in the optimiser
MIN_COVERAGE = 0.5  # share of the signal weight that must be present to act
DISCLAIMER = "Educational output from historical data. Not financial advice."


def _clip(value: float) -> float:
    return max(-1.0, min(1.0, value))


def forecast_signal(forecast: dict | None) -> dict:
    """Expected move over the horizon, measured in units of its own uncertainty."""
    if not forecast:
        return {"name": "forecast", "available": False, "score": 0.0, "reason": "no_forecast"}
    expected = forecast["expected_return_pct"]
    spread = forecast["daily_volatility_pct"] * math.sqrt(forecast["horizon"])
    score = _clip(expected / spread) if spread > 0 else 0.0
    useful = bool(forecast["model"]["beats_random_walk"])
    return {
        "name": "forecast",
        "available": useful,
        "score": round(score, 3),
        "reason": "model_beats_random_walk" if useful else "model_no_better_than_random_walk",
        "expected_return_pct": expected,
        "uncertainty_pct": round(spread, 3),
        "model": forecast["model"]["selected"],
    }


def technical_signal(summary: dict, close: float) -> dict:
    """RSI extremes, the MACD histogram and the close against its 50-session average."""
    parts = []
    rsi = summary.get("rsi")
    if rsi is not None:
        parts.append(_clip((50.0 - rsi) / 20.0) if rsi < 30 or rsi > 70 else 0.0)  # mean reversion at extremes
    hist = summary.get("macd_histogram")
    if hist is not None and close > 0:
        parts.append(_clip(hist / close * 200.0))  # 0.5% of the price saturates
    sma50 = summary.get("sma_50")
    if sma50:
        parts.append(_clip((close / sma50 - 1.0) * 10.0))  # 10% above the average saturates
    if not parts:
        return {"name": "technical", "available": False, "score": 0.0, "reason": "not_enough_history"}
    return {
        "name": "technical",
        "available": True,
        "score": round(sum(parts) / len(parts), 3),
        "reason": "indicators",
        "rsi": rsi,
        "macd_histogram": hist,
        "close_vs_sma50_pct": round((close / sma50 - 1.0) * 100.0, 2) if sma50 else None,
    }


def sentiment_signal(news: dict) -> dict:
    """Recent news on the stock; fewer than three articles count for less."""
    if not news.get("articles"):
        return {"name": "sentiment", "available": False, "score": 0.0, "reason": "no_recent_news", "articles": 0}
    return {
        "name": "sentiment",
        "available": True,
        "score": round(_clip(news["score"]), 3),
        "reason": "recent_news",
        "articles": news["articles"],
        "strength": round(min(1.0, news["articles"] / 3.0), 2),
    }


def anomaly_signal(alert: dict) -> dict:
    """The worst unusual session of the last few, if any. A warning, not a direction."""
    return {
        "name": "anomaly",
        "available": alert.get("severity") is not None,
        "score": 0.0,
        "severity": alert.get("severity"),
        "count": alert.get("count", 0),
        "kinds": alert.get("kinds", []),
        "last_date": alert.get("last_date"),
    }


def decide(
    signals: list[dict],
    profile: str,
    *,
    listed: bool = True,
    traded_share: float = 1.0,
    held_weight: float | None = None,
    trust: dict[str, float] | None = None,
) -> dict:
    """Combine the signals into BUY / HOLD / SELL, then apply the safety rules.

    ``traded_share`` is the share of the last 60 sessions on which the stock
    traded; ``held_weight`` is the stock's weight in the user's account (None
    without an account).
    """
    if profile not in THRESHOLDS:
        raise ValueError(f"profile must be one of {sorted(THRESHOLDS)}")
    by_name = {s["name"]: s for s in signals}
    trust = trust or {}
    used, total, covered = 0.0, 0.0, 0.0
    contributions = []
    for name, base in BASE_WEIGHTS.items():
        signal = by_name.get(name, {"available": False, "score": 0.0})
        weight = base * trust.get(name, 1.0)
        if name == "sentiment" and signal.get("available"):
            weight *= signal.get("strength", 1.0)
        total += base
        if signal.get("available"):
            used += weight * signal["score"]
            covered += weight
            contributions.append({"name": name, "weight": round(weight, 3), "score": signal["score"]})
    combined = used / covered if covered else 0.0
    coverage = min(1.0, covered / total)
    threshold = THRESHOLDS[profile]
    action = "BUY" if combined >= threshold else "SELL" if combined <= -threshold else "HOLD"
    proposed = action

    rules = []

    def rule(name: str, triggered: bool, effect: str | None = None) -> None:
        rules.append({"rule": name, "triggered": triggered, "effect": effect if triggered else None})

    anomaly = by_name.get("anomaly", {})
    rule("not_listed", not listed and action == "BUY", "BUY -> HOLD")
    if not listed and action == "BUY":
        action = "HOLD"
    severe = anomaly.get("severity") in {"high", "critical"}
    rule("recent_anomaly", severe and action == "BUY", "BUY -> HOLD")
    if severe and action == "BUY":
        action = "HOLD"
    illiquid = traded_share < 0.5
    blocks = illiquid and profile != "aggressive" and action == "BUY"
    rule("illiquid", blocks, "BUY -> HOLD")
    if blocks:
        action = "HOLD"
    thin = coverage < MIN_COVERAGE and action != "HOLD"
    rule("thin_evidence", thin, f"{action} -> HOLD")
    if thin:
        action = "HOLD"
    capped = held_weight is not None and held_weight >= MAX_WEIGHT[profile] and action == "BUY"
    rule("position_cap", capped, "BUY -> HOLD")
    if capped:
        action = "HOLD"
    no_short = held_weight is not None and held_weight <= 0 and action == "SELL"
    rule("no_short_selling", no_short, "SELL -> AVOID")
    if no_short:
        action = "AVOID"

    return {
        "action": action,
        "proposed_action": proposed,
        "score": round(combined, 3),
        "threshold": threshold,
        "coverage": round(coverage, 2),  # share of the signal weight that was available
        "contributions": contributions,
        "illiquid": illiquid,
        "traded_share": round(traded_share, 2),
        "safety_rules": rules,
        "profile": profile,
        "disclaimer": DISCLAIMER,
    }
