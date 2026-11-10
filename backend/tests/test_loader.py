"""Bootstrap of the database from the Parquet file."""
from __future__ import annotations

import pandas as pd
from sqlalchemy import func, select

from app.data.loader import bootstrap_prices, load_price_frame
from app.db import Base, make_engine
from app.models import Price, Stock


def _engine(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'loader.db'}")
    Base.metadata.create_all(engine)
    return engine


def test_bootstrap_loads_once_and_round_trips(tmp_path, prices):
    parquet = tmp_path / "prices.parquet"
    prices.drop(columns=["sector"]).to_parquet(parquet, index=False)
    engine = _engine(tmp_path)

    assert bootstrap_prices(engine, parquet) == len(prices)
    assert bootstrap_prices(engine, parquet) == 0  # second start: nothing to do

    with engine.connect() as conn:
        assert conn.execute(select(func.count()).select_from(Stock)).scalar_one() == prices["ticker"].nunique()
        assert conn.execute(select(func.count()).select_from(Price)).scalar_one() == len(prices)

    frame = load_price_frame(engine)
    assert len(frame) == len(prices)
    assert pd.api.types.is_datetime64_any_dtype(frame["date"])
    expected = prices.sort_values(["ticker", "date"]).reset_index(drop=True)
    assert (frame["ticker"].values == expected["ticker"].values).all()
    assert abs(frame["close"].values - expected["close"].values).max() < 1e-9
    assert (frame["volume"].values == expected["volume"].values).all()


def test_bootstrap_assigns_sectors(tmp_path):
    rows = pd.DataFrame(
        {
            "date": pd.to_datetime(["2025-01-02", "2025-01-02"]),
            "isin": ["TN0001800457", "TN0009999999"],
            "ticker": ["BIAT", "MYSTERY"],
            "name": ["BIAT", "MYSTERY"],
            "market_group": [11, 12],
            "open": [90.0, 1.0], "high": [91.0, 1.0], "low": [89.0, 1.0], "close": [90.5, 1.0],
            "volume": [100, 0], "trades": [3, 0], "turnover": [9050.0, 0.0], "traded": [True, False],
        }
    )
    parquet = tmp_path / "p.parquet"
    rows.to_parquet(parquet, index=False)
    engine = _engine(tmp_path)
    bootstrap_prices(engine, parquet)
    with engine.connect() as conn:
        sectors = dict(conn.execute(select(Stock.ticker, Stock.sector)).all())
    assert sectors == {"BIAT": "Banks", "MYSTERY": "Other"}


def test_missing_parquet_is_a_soft_failure(tmp_path):
    engine = _engine(tmp_path)
    assert bootstrap_prices(engine, tmp_path / "absent.parquet") == 0
    assert load_price_frame(engine).empty
