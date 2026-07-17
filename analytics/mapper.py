from __future__ import annotations

import pandas as pd

from providers.evidence import DataValueStatus, FieldEvidence, utc_now

COLUMN_MAP = {
    "ev_to_ebitda": "ev_ebitda",
    "enterprise_to_ebitda": "ev_ebitda",
    "debt_to_equity": "net_debt_total_equity",
    "current_ratio": "current_liquidity",
    "target_price": "consensus_target",
    "ebitda_margin": "operating_margin_proxy",
}


DERIVED_DEPENDENCIES = {
    "net_debt": ("total_debt", "total_cash"),
    "net_debt_ebitda": ("total_debt", "total_cash", "ebitda"),
    "fcf_yield": ("free_cashflow", "market_cap"),
    "shareholder_yield": ("dividend_rate", "price", "market_cap"),
    "target_upside": ("consensus_target", "price"),
    "ev_ebit": ("enterprise_value", "ebit"),
}


def _propagate_field_evidence(frame: pd.DataFrame) -> pd.DataFrame:
    if "field_evidence" not in frame.columns:
        return frame
    for index, row in frame.iterrows():
        evidence = dict(row.get("field_evidence") or {})
        for source, target in COLUMN_MAP.items():
            if source in evidence and target not in evidence:
                evidence[target] = dict(evidence[source])
        for target, dependencies in DERIVED_DEPENDENCIES.items():
            if target not in frame.columns or target in evidence:
                continue
            dependency_evidence = [
                FieldEvidence.from_dict(evidence[name])
                for name in dependencies
                if name in evidence
            ]
            statuses = {item.status for item in dependency_evidence}
            if DataValueStatus.NOT_APPLICABLE in statuses:
                status = DataValueStatus.NOT_APPLICABLE
            elif pd.notna(row.get(target)) and statuses <= {DataValueStatus.PRESENT}:
                status = DataValueStatus.PRESENT
            elif DataValueStatus.INVALID in statuses:
                status = DataValueStatus.INVALID
            elif DataValueStatus.STALE in statuses:
                status = DataValueStatus.STALE
            elif DataValueStatus.UNAVAILABLE in statuses:
                status = DataValueStatus.UNAVAILABLE
            else:
                status = DataValueStatus.MISSING
            timestamps = [item.retrieved_at for item in dependency_evidence if item.retrieved_at]
            observed = [item.observed_at for item in dependency_evidence if item.observed_at]
            evidence[target] = FieldEvidence(
                status=status,
                source="Atlas derived",
                category="fundamentals",
                retrieved_at=max(timestamps) if timestamps else utc_now(),
                observed_at=max(observed) if observed else None,
                available_at=max(timestamps) if timestamps else None,
                detail="derived from " + ", ".join(dependencies),
            ).to_dict()
        frame.at[index, "field_evidence"] = evidence
    return frame


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

    # O Yahoo devolve shortPercentOfFloat como fração (0.25 = 25%), mas o
    # deal breaker short_float_max é expresso em pontos percentuais (20 = 20%).
    # Sem esta conversão o threshold nunca dispara (uma fração <= ~1 nunca é
    # > 20). normalize_columns recebe a saída crua do provider e converte uma
    # única vez.
    if "short_float" in out.columns:
        out["short_float"] = pd.to_numeric(out["short_float"], errors="coerce") * 100

    return _propagate_field_evidence(out)
