"""Market surveillance: sessions that do not look like a stock's usual trading.

Three independent detectors look at every traded session:

* ``volume_spike``: the volume is more than 3 standard deviations above the
  stock's own previous 60 sessions;
* ``price_move``: the close moved more than 5% from the previous close;
* ``pattern``: an Isolation Forest, fitted on all stocks at once, isolates the
  session on the combination of return, volume and intraday range (each scaled
  to the stock's own habits, so a quiet stock and a busy one are comparable).

A move beyond 15% is labelled ``corporate_action`` instead: the history is not
adjusted for splits and bonus issues, and such a jump is far more likely one of
those than a trading anomaly. It is listed, but never ranked as severe.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from .market import CORPORATE_ACTION_MOVE, MarketData

VOLUME_Z_THRESHOLD = 3.0
PRICE_MOVE_THRESHOLD = 0.05
VOLUME_WINDOW = 60
HABIT_WINDOW = 120
SCAN_SESSIONS = 250  # sessions scored by the forest
CONTAMINATION = 0.02
SEVERITIES = ["low", "medium", "high", "critical"]


def _matrices(market: MarketData, sessions: int) -> dict[str, pd.DataFrame]:
    cutoff = market.sessions[-min(len(market.sessions), sessions)]
    frame = market.prices[market.prices["date"] >= cutoff]
    return {
        name: frame.pivot(index="date", columns="ticker", values=name).sort_index()
        for name in ("close", "high", "low", "volume", "traded")
    }


def session_features(market: MarketData, sessions: int = SCAN_SESSIONS) -> pd.DataFrame:
    """One row per (traded session, stock) with the features the detectors use."""
    m = _matrices(market, sessions + HABIT_WINDOW + 1)
    close, volume = m["close"], m["volume"].astype(float)
    traded = m["traded"].astype("boolean").fillna(False).astype(bool)
    change = close.pct_change(fill_method=None)
    volume_mean = volume.rolling(VOLUME_WINDOW, min_periods=20).mean().shift(1)
    volume_std = volume.rolling(VOLUME_WINDOW, min_periods=20).std(ddof=0).shift(1)
    volume_z = (volume - volume_mean) / volume_std.where(volume_std > 0)
    usual_move = change.abs().rolling(HABIT_WINDOW, min_periods=30).mean().shift(1)
    spread = (m["high"] - m["low"]) / close.where(close > 0)
    usual_spread = spread.rolling(HABIT_WINDOW, min_periods=30).mean().shift(1)

    def tail(matrix: pd.DataFrame) -> pd.Series:
        return matrix.tail(sessions).stack(future_stack=True)

    out = pd.DataFrame(
        {
            "close": tail(close),
            "volume": tail(volume),
            "change": tail(change),
            "volume_z": tail(volume_z),
            "move_ratio": tail(change.abs() / usual_move.where(usual_move > 0)),
            "spread_ratio": tail(spread / usual_spread.where(usual_spread > 0)),
            "traded": tail(traded),
        }
    ).reset_index()
    out = out[out["traded"].fillna(False).astype(bool) & out["close"].notna()].drop(columns="traded")
    return out.reset_index(drop=True)


def _forest_flags(features: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Isolation Forest over all stocks; returns (is_outlier, strength in 0..1)."""
    if len(features) < 200:
        return np.zeros(len(features), dtype=bool), np.zeros(len(features))
    matrix = np.column_stack(
        [
            features["volume_z"].fillna(0.0).clip(-5, 15),
            features["move_ratio"].fillna(1.0).clip(0, 15),
            features["spread_ratio"].fillna(1.0).clip(0, 15),
        ]
    )
    forest = IsolationForest(n_estimators=200, contamination=CONTAMINATION, random_state=0)
    labels = forest.fit_predict(matrix)
    raw = -forest.score_samples(matrix)  # higher = more isolated
    low, high = np.quantile(raw, 0.5), raw.max()
    strength = np.clip((raw - low) / (high - low), 0.0, 1.0) if high > low else np.zeros(len(raw))
    return labels == -1, strength


def _describe(row: pd.Series, kinds: list[str]) -> str:
    parts = []
    if "corporate_action" in kinds:
        parts.append(f"close moved {row['change'] * 100:+.1f}%, probably a corporate action (unadjusted prices)")
    if "price_move" in kinds:
        parts.append(f"close moved {row['change'] * 100:+.1f}%")
    if "volume_spike" in kinds:
        parts.append(f"volume {row['volume_z']:.1f} standard deviations above its 60-session average")
    if "pattern" in kinds:
        parts.append("unusual combination of return, volume and intraday range")
    return f"{row['ticker']}: " + "; ".join(parts)


def scan(market: MarketData, sessions: int = SCAN_SESSIONS) -> pd.DataFrame:
    """Every flagged (session, stock), most severe first."""
    features = session_features(market, sessions)
    columns = ["date", "ticker", "name", "sector", "close", "volume", "change_pct", "volume_z", "kinds", "severity", "score", "message"]
    if features.empty:
        return pd.DataFrame(columns=columns)
    change = features["change"].abs()
    corporate = change > CORPORATE_ACTION_MOVE
    price = (change > PRICE_MOVE_THRESHOLD) & ~corporate
    spike = features["volume_z"] > VOLUME_Z_THRESHOLD
    pattern, strength = _forest_flags(features)
    pattern = pattern & ~corporate.to_numpy()

    # Points: how many detectors fired and how far past their thresholds.
    points = (
        spike.astype(int)
        + (features["volume_z"] > 2 * VOLUME_Z_THRESHOLD).astype(int)
        + price.astype(int)
        + ((change > 1.6 * PRICE_MOVE_THRESHOLD) & ~corporate).astype(int)
        + pattern.astype(int)
    )
    flagged = features[(points > 0) | corporate].copy()
    if flagged.empty:
        return pd.DataFrame(columns=columns)
    idx = flagged.index
    flagged["points"] = points.loc[idx]
    flagged["severity"] = [SEVERITIES[min(max(p, 1), 4) - 1] for p in flagged["points"]]
    flagged.loc[corporate.loc[idx] & (flagged["points"] <= 1), "severity"] = "low"
    volume_part = (features["volume_z"].loc[idx].fillna(0.0).clip(0, 4 * VOLUME_Z_THRESHOLD)) / (4 * VOLUME_Z_THRESHOLD)
    price_part = (change.loc[idx].clip(0, CORPORATE_ACTION_MOVE) / CORPORATE_ACTION_MOVE).where(~corporate.loc[idx], 0.0)
    flagged["score"] = (0.4 * volume_part + 0.4 * price_part + 0.2 * strength[idx]).round(4)

    kinds_per_row = []
    for i in idx:
        kinds = []
        if corporate.loc[i]:
            kinds.append("corporate_action")
        if price.loc[i]:
            kinds.append("price_move")
        if spike.loc[i]:
            kinds.append("volume_spike")
        if pattern[i]:
            kinds.append("pattern")
        kinds_per_row.append(kinds)
    flagged["kinds"] = kinds_per_row
    flagged["message"] = [_describe(row, kinds) for (_, row), kinds in zip(flagged.iterrows(), kinds_per_row)]
    stocks = market.stocks.set_index("ticker")
    flagged["name"] = flagged["ticker"].map(stocks["name"])
    flagged["sector"] = flagged["ticker"].map(stocks["sector"])
    flagged["change_pct"] = (flagged["change"] * 100.0).round(2)
    flagged["volume_z"] = flagged["volume_z"].round(2)
    flagged["volume"] = flagged["volume"].astype("int64")
    flagged["rank"] = flagged["severity"].map({s: i for i, s in enumerate(SEVERITIES)})
    flagged = flagged.sort_values(["rank", "score", "date"], ascending=[False, False, False])
    return flagged[columns].reset_index(drop=True)


# ----------------------------------------------------------------- caching
_cache: dict[str, pd.DataFrame] = {}


def cached_scan(market: MarketData) -> pd.DataFrame:
    key = market.last_session.date().isoformat()
    if key not in _cache:
        _cache.clear()
        _cache[key] = scan(market)
    return _cache[key]


def clear_cache() -> None:
    _cache.clear()


def filter_alerts(
    alerts: pd.DataFrame,
    market: MarketData,
    sessions: int | None = None,
    min_severity: str = "low",
    ticker: str | None = None,
) -> pd.DataFrame:
    out = alerts
    if sessions:
        cutoff = market.sessions[-min(len(market.sessions), sessions)]
        out = out[out["date"] >= cutoff]
    if min_severity in SEVERITIES:
        keep = SEVERITIES[SEVERITIES.index(min_severity) :]
        out = out[out["severity"].isin(keep)]
    if ticker:
        out = out[out["ticker"] == ticker]
    return out


def stock_signal(market: MarketData, ticker: str, sessions: int = 5) -> dict:
    """The worst alert on a stock over the last few sessions, for the decision engine."""
    recent = filter_alerts(cached_scan(market), market, sessions=sessions, ticker=market.resolve(ticker))
    recent = recent[recent["kinds"].map(lambda kinds: kinds != ["corporate_action"])]
    if recent.empty:
        return {"severity": None, "count": 0, "kinds": [], "last_date": None}
    worst = recent.iloc[0]
    return {
        "severity": worst["severity"],
        "count": int(len(recent)),
        "kinds": sorted({kind for kinds in recent["kinds"] for kind in kinds}),
        "last_date": recent["date"].max().date().isoformat(),
    }
