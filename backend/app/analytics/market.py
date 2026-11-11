"""In-memory view of the price history and market-wide statistics.

The price table lives in the database; the API reads it once at start-up into
a pandas frame (about 210k rows) because every analytic needs fast slices of
it. ``MarketData`` is a plain object built from a frame, so tests can create
one without a database.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property

import numpy as np
import pandas as pd

# A close-to-close move beyond this size on one session is treated as a
# corporate action (split, bonus issue, dividend detachment) when building the
# composite index, because the history is not adjusted for them.
CORPORATE_ACTION_MOVE = 0.15
INDEX_BASE = 1000.0
INDEX_WEIGHT_WINDOW = 60  # sessions of turnover used as the weight


class UnknownTicker(KeyError):
    pass


@dataclass
class MarketData:
    prices: pd.DataFrame  # columns: date, isin, ticker, name, sector, market_group, OHLC, volume, trades, turnover, traded

    def __post_init__(self) -> None:
        frame = self.prices.copy()
        frame["date"] = pd.to_datetime(frame["date"])
        if "sector" not in frame.columns:
            frame["sector"] = "Other"
        frame = frame.sort_values(["ticker", "date"], kind="stable").reset_index(drop=True)
        self.prices = frame
        self._by_ticker = {ticker: group for ticker, group in frame.groupby("ticker", sort=False)}

    # ------------------------------------------------------------------ basics
    @property
    def empty(self) -> bool:
        return self.prices.empty

    @cached_property
    def sessions(self) -> pd.DatetimeIndex:
        return pd.DatetimeIndex(sorted(self.prices["date"].unique()))

    @property
    def last_session(self) -> pd.Timestamp:
        return self.sessions[-1]

    @cached_property
    def stocks(self) -> pd.DataFrame:
        """One row per security with its latest quote and listing status."""
        last = self.prices.groupby("ticker", sort=True).tail(1).set_index("ticker")
        first = self.prices.groupby("ticker", sort=True)["date"].min()
        out = last[["isin", "name", "sector", "market_group", "close", "date"]].rename(
            columns={"close": "last_close", "date": "last_session"}
        )
        out["first_session"] = first
        out["listed"] = out["last_session"] == self.last_session
        return out.reset_index()

    def tickers(self, listed_only: bool = True) -> list[str]:
        stocks = self.stocks
        if listed_only:
            stocks = stocks[stocks["listed"]]
        return stocks["ticker"].tolist()

    def resolve(self, ticker: str) -> str:
        """Accept a ticker, an ISIN or a display name (case-insensitive)."""
        key = ticker.strip().upper()
        if key in self._by_ticker:
            return key
        stocks = self.stocks
        match = stocks[(stocks["isin"] == key) | (stocks["name"].str.upper() == key)]
        if match.empty:
            raise UnknownTicker(ticker)
        return str(match.iloc[0]["ticker"])

    def history(self, ticker: str, sessions: int | None = None) -> pd.DataFrame:
        frame = self._by_ticker[self.resolve(ticker)]
        if sessions:
            frame = frame.tail(sessions)
        return frame.reset_index(drop=True)

    def info(self, ticker: str) -> dict:
        row = self.stocks.set_index("ticker").loc[self.resolve(ticker)]
        return {
            "ticker": row.name,
            "isin": row["isin"],
            "name": row["name"],
            "sector": row["sector"],
            "market_group": int(row["market_group"]),
            "listed": bool(row["listed"]),
            "first_session": row["first_session"].date().isoformat(),
            "last_session": row["last_session"].date().isoformat(),
        }

    # --------------------------------------------------------------- matrices
    @cached_property
    def close_matrix(self) -> pd.DataFrame:
        return self.prices.pivot(index="date", columns="ticker", values="close").sort_index()

    @cached_property
    def turnover_matrix(self) -> pd.DataFrame:
        return self.prices.pivot(index="date", columns="ticker", values="turnover").sort_index().fillna(0.0)

    @cached_property
    def returns_matrix(self) -> pd.DataFrame:
        """Daily close-to-close returns; moves that look like corporate actions are blanked."""
        returns = self.close_matrix.pct_change(fill_method=None)
        return returns.mask(returns.abs() > CORPORATE_ACTION_MOVE)

    # ------------------------------------------------------------------ index
    @cached_property
    def composite_index(self) -> pd.DataFrame:
        """A liquidity-weighted composite of all listed shares, base 1000.

        The official TUNINDEX is weighted by free-float capitalisation, which the
        price files do not contain. This proxy weights each share by its traded
        value over the previous 60 sessions and chains the weighted daily
        returns. It tracks the direction of the market, not the official level.
        """
        returns = self.returns_matrix
        weights = self.turnover_matrix.rolling(INDEX_WEIGHT_WINDOW, min_periods=5).mean().shift(1)
        weights = weights.where(returns.notna(), 0.0)
        total = weights.sum(axis=1)
        daily = (returns.fillna(0.0) * weights).sum(axis=1) / total.where(total > 0)
        daily = daily.fillna(0.0)
        level = INDEX_BASE * (1.0 + daily).cumprod()
        return pd.DataFrame({"date": level.index, "value": level.values, "return": daily.values})

    # --------------------------------------------------------------- overview
    def session_table(self, session: pd.Timestamp | None = None) -> pd.DataFrame:
        """Quotes of one session with the change against the previous close."""
        session = self.last_session if session is None else pd.Timestamp(session)
        position = self.sessions.get_indexer([session])[0]
        if position < 0:
            raise KeyError(f"no session on {session.date()}")
        today = self.prices[self.prices["date"] == session].set_index("ticker")
        closes = self.close_matrix
        previous = closes.iloc[position - 1] if position > 0 else pd.Series(np.nan, index=closes.columns)
        out = today[["name", "sector", "open", "high", "low", "close", "volume", "trades", "turnover", "traded"]].copy()
        out["previous_close"] = previous.reindex(out.index)
        out["change_pct"] = (out["close"] / out["previous_close"] - 1.0) * 100.0
        out.loc[~out["traded"], "change_pct"] = 0.0
        return out.reset_index()

    def overview(self, top: int = 5, index_sessions: int = 250) -> dict:
        table = self.session_table()
        traded = table[table["traded"]]
        movers = traded.dropna(subset=["change_pct"])
        # Moves that look like corporate actions are not genuine gains or losses.
        movers = movers[movers["change_pct"].abs() <= CORPORATE_ACTION_MOVE * 100]
        index = self.composite_index.tail(index_sessions)
        last, prev = index.iloc[-1], index.iloc[-2] if len(index) > 1 else index.iloc[-1]
        volume_history = (
            self.prices.groupby("date")[["volume", "turnover"]].sum().tail(index_sessions).reset_index()
        )

        def rows(frame: pd.DataFrame) -> list[dict]:
            return [
                {
                    "ticker": r.ticker,
                    "name": r.name,
                    "sector": r.sector,
                    "close": round(float(r.close), 3),
                    "change_pct": round(float(r.change_pct), 2),
                    "volume": int(r.volume),
                    "turnover": round(float(r.turnover), 2),
                }
                for r in frame.itertuples(index=False)
            ]

        return {
            "session": self.last_session.date().isoformat(),
            "index": {
                "name": "BVMT composite (TUNINDEX proxy)",
                "note": "Liquidity-weighted proxy computed from share prices; not the official TUNINDEX level.",
                "value": round(float(last["value"]), 2),
                "change_pct": round(float(last["value"] / prev["value"] - 1.0) * 100.0, 2),
                "history": [
                    {"date": d.date().isoformat(), "value": round(float(v), 2)}
                    for d, v in zip(index["date"], index["value"])
                ],
            },
            "breadth": {
                "listed": int(len(table)),
                "traded": int(len(traded)),
                "advancing": int((movers["change_pct"] > 0).sum()),
                "declining": int((movers["change_pct"] < 0).sum()),
                "unchanged": int((movers["change_pct"] == 0).sum()),
            },
            "totals": {
                "volume": int(table["volume"].sum()),
                "turnover": round(float(table["turnover"].sum()), 2),
                "trades": int(table["trades"].sum()),
            },
            "gainers": rows(movers.sort_values("change_pct", ascending=False).head(top)),
            "losers": rows(movers.sort_values("change_pct").head(top)),
            "most_active": rows(traded.sort_values("turnover", ascending=False).head(top)),
            "volume_history": [
                {"date": r.date.date().isoformat(), "volume": int(r.volume), "turnover": round(float(r.turnover), 2)}
                for r in volume_history.itertuples(index=False)
            ],
        }


_market: MarketData | None = None


def set_market(market: MarketData | None) -> None:
    global _market
    _market = market


def get_market() -> MarketData:
    if _market is None:
        raise RuntimeError("market data is not loaded yet")
    return _market
