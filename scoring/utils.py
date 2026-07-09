from __future__ import annotations

import pandas as pd


def pct_rank(df: pd.DataFrame, col: str, higher: bool = True) -> pd.Series:
    if col not in df.columns:
        return pd.Series(50.0, index=df.index)
    s = pd.to_numeric(df[col], errors="coerce")
    if s.notna().sum() <= 1:
        return pd.Series(50.0, index=df.index)
    r = s.rank(method="average", pct=True) * 100
    if not higher:
        r = 100 - r
    return r.fillna(50)


def weighted(parts: list[tuple[pd.Series, float]]) -> pd.Series:
    total = None
    for score, weight in parts:
        total = score * weight if total is None else total + score * weight
    return total if total is not None else pd.Series(dtype=float)
