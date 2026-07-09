from __future__ import annotations

import pandas as pd
from scoring.utils import pct_rank, weighted


def financial_score(df: pd.DataFrame) -> pd.Series:
    return weighted([
        (pct_rank(df, "net_debt_ebitda", False), 0.30),
        (pct_rank(df, "net_debt_total_equity", False), 0.25),
        (pct_rank(df, "current_liquidity", True), 0.20),
        (pct_rank(df, "interest_coverage", True), 0.15),
        (pct_rank(df, "altman_z", True), 0.10),
    ])
