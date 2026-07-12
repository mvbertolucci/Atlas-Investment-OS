from __future__ import annotations

import pandas as pd

COLUMN_MAP = {
    "ev_to_ebitda": "ev_ebitda",
    "enterprise_to_ebitda": "ev_ebitda",
    "debt_to_equity": "net_debt_total_equity",
    "current_ratio": "current_liquidity",
    "target_price": "consensus_target",
    "ebitda_margin": "operating_margin_proxy",
}


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for src, dst in COLUMN_MAP.items():
        if src in out.columns and dst not in out.columns:
            out[dst] = out[src]

    # Derived fields available from Yahoo Finance.
    if {"total_debt", "total_cash", "ebitda"}.issubset(out.columns):
        debt = pd.to_numeric(out["total_debt"], errors="coerce")
        cash = pd.to_numeric(out["total_cash"], errors="coerce")
        ebitda = pd.to_numeric(out["ebitda"], errors="coerce")
        out["net_debt"] = debt - cash
        out["net_debt_ebitda"] = out["net_debt"] / ebitda.replace(0, pd.NA)

    if {"free_cashflow", "market_cap"}.issubset(out.columns):
        fcf = pd.to_numeric(out["free_cashflow"], errors="coerce")
        mcap = pd.to_numeric(out["market_cap"], errors="coerce")
        out["fcf_yield"] = fcf / mcap.replace(0, pd.NA)

    # Shareholder yield = dividend yield + buyback yield, ambos expressos
    # como fração do valor de mercado para ficarem na mesma escala antes do
    # ranking cross-sectional. O campo dividendYield do Yahoo é frágil
    # (percentual em algumas versões, fração em outras), então o dividendo é
    # recalculado de dividend_rate/price (dólar/dólar, à prova de versão).
    if "market_cap" in out.columns:
        mcap = pd.to_numeric(out["market_cap"], errors="coerce").replace(0, pd.NA)

        if {"dividend_rate", "price"}.issubset(out.columns):
            rate = pd.to_numeric(out["dividend_rate"], errors="coerce")
            price = pd.to_numeric(out["price"], errors="coerce").replace(0, pd.NA)
            dividend_frac = (rate / price).fillna(0.0)
        else:
            dividend_frac = pd.Series(0.0, index=out.index)

        if "buyback" in out.columns:
            buyback_frac = (
                pd.to_numeric(out["buyback"], errors="coerce") / mcap
            ).fillna(0.0)
        else:
            buyback_frac = pd.Series(0.0, index=out.index)

        out["shareholder_yield"] = dividend_frac + buyback_frac

    if {"consensus_target", "price"}.issubset(out.columns):
        target = pd.to_numeric(out["consensus_target"], errors="coerce")
        price = pd.to_numeric(out["price"], errors="coerce")
        out["target_upside"] = (target / price.replace(0, pd.NA) - 1) * 100

    if {"enterprise_value", "ebit"}.issubset(out.columns):
        ev = pd.to_numeric(out["enterprise_value"], errors="coerce")
        ebit = pd.to_numeric(out["ebit"], errors="coerce")
        out["ev_ebit"] = ev / ebit.replace(0, pd.NA)

    return out
