from __future__ import annotations

import pandas as pd


VALUATION_FEATURES = {
    "pe": {"label": "PE", "weight": 0.20, "higher": False},
    "forward_pe": {"label": "Forward PE", "weight": 0.15, "higher": False},
    "ev_ebitda": {"label": "EV EBITDA", "weight": 0.20, "higher": False},
    "ev_ebit": {"label": "EV EBIT", "weight": 0.15, "higher": False},
    "peg": {"label": "PEG", "weight": 0.10, "higher": False},
    "pb": {"label": "Price Book", "weight": 0.10, "higher": False},
    "shareholder_yield": {"label": "Shareholder Yield", "weight": 0.05, "higher": True},
    "fcf_yield": {"label": "FCF Yield", "weight": 0.05, "higher": True},
}


def pct_rank(df: pd.DataFrame, column: str, higher_is_better: bool = True) -> pd.Series:
    if column not in df.columns:
        return pd.Series(50.0, index=df.index)

    s = pd.to_numeric(df[column], errors="coerce")
    if s.notna().sum() <= 1:
        return pd.Series(50.0, index=df.index)

    r = s.rank(method="average", pct=True) * 100
    if not higher_is_better:
        r = 100 - r

    return r.fillna(50.0)


def metric_available(df: pd.DataFrame, column: str) -> pd.Series:
    if column not in df.columns:
        return pd.Series(False, index=df.index)

    return pd.to_numeric(df[column], errors="coerce").notna()


def score_valuation(df: pd.DataFrame) -> tuple[pd.Series, pd.Series, pd.DataFrame]:
    weighted_sum = pd.Series(0.0, index=df.index)
    available_weight = pd.Series(0.0, index=df.index)
    total_weight = sum(v["weight"] for v in VALUATION_FEATURES.values())

    details = pd.DataFrame(index=df.index)

    for column, cfg in VALUATION_FEATURES.items():
        score = pct_rank(df, column, cfg["higher"])
        available = metric_available(df, column)

        weighted_sum += score * cfg["weight"]
        available_weight += available.astype(float) * cfg["weight"]

        safe_label = cfg["label"].replace(" ", "_").replace("/", "_")
        details[f"valuation_{safe_label}_score"] = score.round(1)
        details[f"valuation_{safe_label}_available"] = available

    factor_score = (weighted_sum / total_weight).round(1)
    confidence = (available_weight / total_weight * 100).clip(0, 100).round(1)

    return factor_score, confidence, details