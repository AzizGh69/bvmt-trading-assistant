"""Technical indicators computed on a close series: RSI, MACD, Bollinger Bands."""
from __future__ import annotations

import numpy as np
import pandas as pd


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's Relative Strength Index (0-100).

    The first average gain / loss is the simple mean of the first ``period``
    changes; later ones use Wilder's smoothing ``(previous * (n - 1) + current) / n``.
    """
    values = close.to_numpy(dtype=float)
    out = np.full(len(values), np.nan)
    if len(values) <= period:
        return pd.Series(out, index=close.index)
    delta = np.diff(values)
    gains, losses = np.clip(delta, 0.0, None), np.clip(-delta, 0.0, None)
    avg_gain, avg_loss = gains[:period].mean(), losses[:period].mean()
    for i in range(period, len(values)):
        if i > period:
            avg_gain = (avg_gain * (period - 1) + gains[i - 1]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i - 1]) / period
        if avg_loss == 0.0:
            out[i] = 100.0 if avg_gain > 0.0 else 50.0  # no losses in the window
        else:
            out[i] = 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)
    return pd.Series(out, index=close.index)


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    """MACD line, signal line and histogram."""
    fast_ema = close.ewm(span=fast, adjust=False).mean()
    slow_ema = close.ewm(span=slow, adjust=False).mean()
    line = fast_ema - slow_ema
    signal_line = line.ewm(span=signal, adjust=False).mean()
    return pd.DataFrame({"macd": line, "signal": signal_line, "histogram": line - signal_line})


def bollinger(close: pd.Series, window: int = 20, width: float = 2.0) -> pd.DataFrame:
    """Bollinger Bands: moving average and bands at ``width`` standard deviations."""
    middle = close.rolling(window).mean()
    deviation = close.rolling(window).std(ddof=0)
    upper = middle + width * deviation
    lower = middle - width * deviation
    span = (upper - lower).replace(0.0, np.nan)
    return pd.DataFrame({"middle": middle, "upper": upper, "lower": lower, "percent_b": (close - lower) / span})


def technical_frame(history: pd.DataFrame) -> pd.DataFrame:
    """Price history with all indicator columns appended."""
    close = history["close"].astype(float)
    out = history[["date", "open", "high", "low", "close", "volume", "traded"]].copy()
    out["rsi"] = rsi(close)
    out = pd.concat([out, macd(close)], axis=1)
    bands = bollinger(close)
    out["bb_middle"], out["bb_upper"], out["bb_lower"], out["bb_percent_b"] = (
        bands["middle"], bands["upper"], bands["lower"], bands["percent_b"],
    )
    out["sma_20"] = close.rolling(20).mean()
    out["sma_50"] = close.rolling(50).mean()
    return out


def technical_summary(history: pd.DataFrame) -> dict:
    """Latest indicator values and a plain-language reading of each."""
    frame = technical_frame(history)
    if frame.empty:
        return {}
    last = frame.iloc[-1]

    def value(key: str) -> float | None:
        return None if pd.isna(last[key]) else round(float(last[key]), 4)

    rsi_value, hist, percent_b = value("rsi"), value("histogram"), value("bb_percent_b")
    readings = []
    if rsi_value is not None:
        state = "oversold" if rsi_value < 30 else "overbought" if rsi_value > 70 else "neutral"
        readings.append(f"RSI {rsi_value:.0f} ({state})")
    if hist is not None:
        readings.append("MACD above its signal line" if hist > 0 else "MACD below its signal line")
    if percent_b is not None:
        if percent_b > 1:
            readings.append("close above the upper Bollinger band")
        elif percent_b < 0:
            readings.append("close below the lower Bollinger band")
        else:
            readings.append("close inside the Bollinger bands")
    return {
        "rsi": rsi_value,
        "macd": value("macd"),
        "macd_signal": value("signal"),
        "macd_histogram": hist,
        "bb_upper": value("bb_upper"),
        "bb_middle": value("bb_middle"),
        "bb_lower": value("bb_lower"),
        "bb_percent_b": percent_b,
        "sma_20": value("sma_20"),
        "sma_50": value("sma_50"),
        "readings": readings,
    }
