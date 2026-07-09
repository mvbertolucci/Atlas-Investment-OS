from __future__ import annotations

import pandas as pd


def build_diagnostics(df: pd.DataFrame) -> pd.DataFrame:
    base_cols = [c for c in ["symbol", "name"] if c in df.columns]

    available_cols = [
        c for c in df.columns
        if c.endswith("_available")
    ]

    confidence_cols = [
        c for c in df.columns
        if "Confidence" in c or "Coverage" in c
    ]

    other_cols = [
        c for c in ["Risk Penalty", "Deal Breakers"]
        if c in df.columns
    ]

    result = df[base_cols].copy()

    if available_cols:
        available_count = df[available_cols].sum(axis=1)
        total_count = len(available_cols)
        missing_count = total_count - available_count

        result["Available Metrics"] = available_count
        result["Missing Metrics"] = missing_count
        result["Data Coverage %"] = (available_count / total_count * 100).round(1)

    for col in confidence_cols + other_cols:
        result[col] = df[col]

    return result