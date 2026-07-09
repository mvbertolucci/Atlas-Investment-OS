from __future__ import annotations

import pandas as pd
from scoring.utils import pct_rank, weighted


def timing_score(df: pd.DataFrame) -> pd.Series:
    return weighted([
        (pct_rank(df, "rsi_14", False), 0.20),
        (pct_rank(df, "momentum_3m", True), 0.15),
        (pct_rank(df, "momentum_6m", True), 0.20),
        (pct_rank(df, "momentum_12m", True), 0.20),
        (pct_rank(df, "distance_52w_high", False), 0.15),
        (pct_rank(df, "target_upside", True), 0.10),
    ])
