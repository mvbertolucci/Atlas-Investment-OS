from __future__ import annotations

import pandas as pd
from scoring.utils import pct_rank, weighted


def valuation_score(df: pd.DataFrame) -> pd.Series:
    return weighted([
        (pct_rank(df, "ev_ebitda", False), 0.18),
        (pct_rank(df, "mc_ebitda", False), 0.12),
        (pct_rank(df, "pb", False), 0.12),
        (pct_rank(df, "pe", False), 0.12),
        (pct_rank(df, "forward_pe", False), 0.12),
        (pct_rank(df, "shiller_pe", False), 0.08),
        (pct_rank(df, "peg", False), 0.11),
        (pct_rank(df, "shareholder_yield", True), 0.15),
    ])
