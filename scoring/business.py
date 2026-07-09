from __future__ import annotations
import pandas as pd


def pct_rank(df: pd.DataFrame, col: str, higher: bool = True) -> pd.Series:
    if col not in df.columns:
        return pd.Series(50.0, index=df.index)

    s = pd.to_numeric(df[col], errors="coerce")

    if s.notna().sum() <= 1:
        return pd.Series(50.0, index=df.index)

    r = s.rank(pct=True) * 100

    if not higher:
        r = 100 - r

    return r.fillna(50)


def weighted(parts: list[tuple[pd.Series, float]]) -> pd.Series:
    total = pd.Series(0.0, index=parts[0][0].index)
    for score, weight in parts:
        total += score * weight
    return total


def business_score(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()

    roic = pct_rank(result, "roic", True)
    roe = pct_rank(result, "roe", True)

    margins = weighted([
        (pct_rank(result, "gross_margin", True), 0.25),
        (pct_rank(result, "operating_margin", True), 0.25),
        (pct_rank(result, "ebitda_margin", True), 0.25),
        (pct_rank(result, "net_margin", True), 0.25),
    ])

    debt = weighted([
        (pct_rank(result, "net_debt_ebitda", False), 0.35),
        (pct_rank(result, "net_debt_total_equity", False), 0.35),
        (pct_rank(result, "debt_to_equity", False), 0.30),
    ])

    liquidity = weighted([
        (pct_rank(result, "current_ratio", True), 0.40),
        (pct_rank(result, "quick_ratio", True), 0.30),
        (pct_rank(result, "interest_coverage", True), 0.30),
    ])

    piotroski = pct_rank(result, "f_score_annual", True)

    result["Business ROIC Score"] = roic.round(1)
    result["Business ROE Score"] = roe.round(1)
    result["Business Margin Score"] = margins.round(1)
    result["Business Debt Score"] = debt.round(1)
    result["Business Liquidity Score"] = liquidity.round(1)
    result["Business Piotroski Score"] = piotroski.round(1)

    result["Business Score"] = weighted([
        (roic, 0.20),
        (roe, 0.15),
        (piotroski, 0.15),
        (margins, 0.20),
        (debt, 0.15),
        (liquidity, 0.10),
        (pd.Series(50.0, index=result.index), 0.05),
    ]).round(1)

    return result