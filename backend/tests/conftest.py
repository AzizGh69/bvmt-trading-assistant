"""Shared fixtures. Nothing here touches the network."""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Make sure no developer .env leaks an API key or a scraping flag into tests.
os.environ["LLM_API_KEY"] = ""
os.environ["ENABLE_SCRAPING"] = "false"
os.environ["ENABLE_SCHEDULER"] = "false"
os.environ["SMTP_HOST"] = ""
os.environ["JWT_SECRET"] = "test-secret-not-used-anywhere-else-0123456789"

REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_PARQUET = REPO_ROOT / "data" / "bvmt_prices.parquet"

SYNTHETIC = {
    # ticker: (sector, start price, daily drift, daily volatility, mean volume)
    "ALPHA": ("Banks", 20.0, 0.0006, 0.010, 20000),
    "BETA": ("Banks", 8.0, 0.0002, 0.014, 9000),
    "GAMMA": ("Insurance", 55.0, 0.0004, 0.008, 3000),
    "DELTA": ("Food & beverages", 12.0, 0.0008, 0.012, 15000),
    "EPSILON": ("Industry & chemicals", 3.0, -0.0003, 0.020, 40000),
    "ZETA": ("Leasing", 30.0, 0.0001, 0.006, 1500),
}


def make_prices(sessions: int = 420, seed: int = 7) -> pd.DataFrame:
    """Deterministic synthetic history in the tidy-table layout."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2024-01-02", periods=sessions)
    common = rng.normal(0.0, 0.004, sessions)  # a shared market factor
    frames = []
    for i, (ticker, (sector, start, drift, vol, mean_volume)) in enumerate(SYNTHETIC.items()):
        returns = drift + common + rng.normal(0.0, vol, sessions)
        close = start * np.exp(np.cumsum(returns))
        open_ = np.concatenate([[start], close[:-1]]) * (1 + rng.normal(0, 0.002, sessions))
        high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.003, sessions)))
        low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.003, sessions)))
        volume = rng.lognormal(np.log(mean_volume), 0.4, sessions).round().astype("int64")
        frames.append(
            pd.DataFrame(
                {
                    "date": dates,
                    "isin": f"TN00000000{i:02d}",
                    "ticker": ticker,
                    "name": ticker.title(),
                    "sector": sector,
                    "market_group": 11,
                    "open": open_.round(3),
                    "high": high.round(3),
                    "low": low.round(3),
                    "close": close.round(3),
                    "volume": volume,
                    "trades": (volume // 200 + 1).astype("int32"),
                    "turnover": (volume * close).round(3),
                    "traded": True,
                }
            )
        )
    return pd.concat(frames, ignore_index=True)


@pytest.fixture(scope="session")
def prices() -> pd.DataFrame:
    return make_prices()


@pytest.fixture()
def market(prices):
    from app.analytics.market import MarketData

    return MarketData(prices.copy())


@pytest.fixture(scope="session")
def real_prices() -> pd.DataFrame:
    if not REAL_PARQUET.exists():
        pytest.skip("committed price history not found")
    return pd.read_parquet(REAL_PARQUET)


@pytest.fixture()
def client(tmp_path, prices, monkeypatch):
    """API client backed by a temporary SQLite database loaded from a synthetic Parquet file."""
    from fastapi.testclient import TestClient

    from app import config, db
    from app.analytics import market as market_module

    parquet = tmp_path / "prices.parquet"
    prices.drop(columns=["sector"]).to_parquet(parquet, index=False)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setenv("DATA_PARQUET", str(parquet))
    config.get_settings.cache_clear()
    db.reset_engine()
    from app.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client
    market_module.set_market(None)
    db.reset_engine()
    config.get_settings.cache_clear()
