from __future__ import annotations

import pandas as pd

CORE_METRICS = [
    "price", "market_cap", "pe", "forward_pe", "pb", "ps", "ev_ebitda",
    "roe", "roa", "gross_margin", "net_margin", "debt_to_equity",
    "current_liquidity", "net_debt_ebitda", "rsi_14", "momentum_3m",
    "momentum_6m", "momentum_12m", "distance_52w_high", "target_upside",
    "short_float", "insider_own", "inst_own"
]


def add_confidence_score(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    available = []
    for col in CORE_METRICS:
        if col in out.columns:
            available.append(out[col].notna().astype(int))
        else:
            available.append(pd.Series(0, index=out.index))
    matrix = pd.concat(available, axis=1)
    out["Confidence Score"] = (matrix.mean(axis=1) * 100).round(1)
    out["Metrics Available"] = matrix.sum(axis=1).astype(int)
    out["Metrics Expected"] = len(CORE_METRICS)
    return out
