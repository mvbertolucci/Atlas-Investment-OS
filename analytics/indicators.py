from __future__ import annotations

import pandas as pd


def sma(series: pd.Series, window: int):
    s = pd.to_numeric(series, errors="coerce").dropna()
    if len(s) < window:
        return None
    return float(s.rolling(window).mean().iloc[-1])


def momentum(series: pd.Series, window: int):
    s = pd.to_numeric(series, errors="coerce").dropna()
    if len(s) <= window:
        return None
    current = float(s.iloc[-1])
    past = float(s.iloc[-window])
    if past == 0:
        return None
    return (current / past - 1) * 100


def rsi(series: pd.Series, window: int = 14):
    s = pd.to_numeric(series, errors="coerce").dropna()
    if len(s) <= window:
        return None
    delta = s.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window).mean()
    avg_loss = loss.rolling(window).mean()
    if pd.isna(avg_loss.iloc[-1]) or avg_loss.iloc[-1] == 0:
        return 100.0
    rs = avg_gain.iloc[-1] / avg_loss.iloc[-1]
    return float(100 - (100 / (1 + rs)))


def enrich_technicals(row: dict) -> dict:
    hist = row.get("history") or []
    if not hist:
        return row
    df = pd.DataFrame(hist)
    if "Close" not in df.columns:
        return row
    closes = pd.to_numeric(df["Close"], errors="coerce").dropna()
    if closes.empty:
        return row
    price = row.get("price") or float(closes.iloc[-1])
    high_52 = float(closes.max())
    low_52 = float(closes.min())

    row.update({
        "rsi_14": rsi(closes, 14),
        "sma_50": sma(closes, 50),
        "sma_200": sma(closes, 200),
        "momentum_3m": momentum(closes, 63),
        "momentum_6m": momentum(closes, 126),
        "momentum_12m": momentum(closes, 252),
        "distance_52w_high": (price / high_52 - 1) * 100 if price and high_52 else None,
        "distance_52w_low": (price / low_52 - 1) * 100 if price and low_52 else None,
    })
    return row
