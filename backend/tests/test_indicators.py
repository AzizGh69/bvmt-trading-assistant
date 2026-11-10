"""RSI, MACD and Bollinger Bands against hand-checked properties."""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.analytics.indicators import bollinger, macd, rsi, technical_frame, technical_summary


def test_rsi_bounds_and_extremes():
    rising = pd.Series(np.arange(1.0, 60.0))
    falling = pd.Series(np.arange(60.0, 1.0, -1.0))
    flat = pd.Series([5.0] * 40)
    assert rsi(rising).iloc[-1] == 100.0
    assert rsi(falling).iloc[-1] == 0.0
    assert rsi(flat).iloc[-1] == 50.0
    noisy = pd.Series(100 + np.cumsum(np.random.default_rng(1).normal(0, 1, 300)))
    values = rsi(noisy).dropna()
    assert ((values >= 0) & (values <= 100)).all()
    assert rsi(noisy).iloc[:14].isna().all()  # needs 14 changes


def test_rsi_matches_a_step_by_step_wilder_calculation():
    closes = [
        44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08, 45.89, 46.03, 45.61, 46.28, 46.28,
        46.00, 46.03, 46.41, 46.22, 45.64,
    ]
    changes = np.diff(closes)
    gains, losses = np.clip(changes, 0, None), np.clip(-changes, 0, None)
    avg_gain, avg_loss = gains[:14].mean(), losses[:14].mean()  # simple mean seeds the average
    expected = [100 - 100 / (1 + avg_gain / avg_loss)]
    for gain, loss in zip(gains[14:], losses[14:]):
        avg_gain, avg_loss = (avg_gain * 13 + gain) / 14, (avg_loss * 13 + loss) / 14
        expected.append(100 - 100 / (1 + avg_gain / avg_loss))
    values = rsi(pd.Series(closes))
    assert values.iloc[:14].isna().all()
    assert np.allclose(values.iloc[14:], expected)
    assert 70 < values.iloc[14] < 71  # mostly gains in the first 14 changes


def test_macd_definition():
    close = pd.Series(50 + np.cumsum(np.random.default_rng(2).normal(0, 0.5, 200)))
    out = macd(close)
    expected = close.ewm(span=12, adjust=False).mean() - close.ewm(span=26, adjust=False).mean()
    assert np.allclose(out["macd"], expected)
    assert np.allclose(out["histogram"], out["macd"] - out["signal"])
    assert macd(pd.Series([10.0] * 50))["macd"].abs().max() == 0.0


def test_bollinger_bands():
    close = pd.Series(np.linspace(10, 20, 60))
    bands = bollinger(close, window=20, width=2.0)
    window = close.iloc[-20:]
    assert np.isclose(bands["middle"].iloc[-1], window.mean())
    assert np.isclose(bands["upper"].iloc[-1], window.mean() + 2 * window.std(ddof=0))
    assert np.isclose(bands["lower"].iloc[-1], window.mean() - 2 * window.std(ddof=0))
    assert bands["middle"].iloc[:19].isna().all()
    valid = bands.dropna()
    assert (valid["lower"] <= valid["middle"]).all() and (valid["middle"] <= valid["upper"]).all()


def test_technical_frame_and_summary(market):
    history = market.history("ALPHA")
    frame = technical_frame(history)
    assert len(frame) == len(history)
    for column in ("rsi", "macd", "signal", "histogram", "bb_upper", "bb_lower", "sma_20", "sma_50"):
        assert column in frame.columns
    summary = technical_summary(history)
    assert 0 <= summary["rsi"] <= 100
    assert summary["bb_lower"] <= summary["bb_middle"] <= summary["bb_upper"]
    assert len(summary["readings"]) == 3
