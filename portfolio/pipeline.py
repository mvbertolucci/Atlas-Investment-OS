from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pandas as pd

from portfolio.allocation import calculate_allocation
from portfolio.concentration import analyze_allocation_concentration
from portfolio.loader import load_portfolio_csv
from portfolio.models import Holding, Portfolio
from portfolio.quality import calculate_allocation_quality
from portfolio.rebalance import build_rebalance_plan, build_sell_only_plan
from portfolio.report import PortfolioReport, build_portfolio_report
from reports.report_engine import build_company_reports


def _clean_text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _clean_float(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if numeric == numeric else None


def enrich_portfolio_from_analysis(
    portfolio: Portfolio,
    analysis_df: pd.DataFrame,
) -> Portfolio:
    """Liga holdings aos CompanyReports do mesmo ciclo do Atlas."""
    reports = {
        report.symbol: report
        for report in build_company_reports(analysis_df)
    }

    rows: dict[str, pd.Series] = {}
    if "symbol" in analysis_df.columns:
        for _, row in analysis_df.iterrows():
            symbol = _clean_text(row.get("symbol")).upper()
            if symbol:
                rows[symbol] = row

    holdings: list[Holding] = []

    for holding in portfolio.holdings:
        row = rows.get(holding.symbol)
        current_price = holding.current_price
        sector = holding.sector
        industry = holding.industry
        country = holding.country
        currency = holding.currency

        if row is not None:
            if current_price is None:
                current_price = _clean_float(row.get("price"))
            sector = sector or _clean_text(row.get("sector"))
            industry = industry or _clean_text(row.get("industry"))
            country = country or _clean_text(row.get("country"))
            currency = currency or _clean_text(row.get("currency"))

        holdings.append(
            replace(
                holding,
                current_price=current_price,
                sector=sector,
                industry=industry,
                country=country,
                currency=currency or "USD",
                company_report=reports.get(holding.symbol),
            )
        )

    return Portfolio(
        name=portfolio.name,
        holdings=tuple(holdings),
        cash=portfolio.cash,
        currency=portfolio.currency,
        created_at=portfolio.created_at,
    )


REBALANCE_MODES = ("sell_only", "auto")


def build_portfolio_intelligence(
    portfolio_path: Path,
    analysis_df: pd.DataFrame,
    *,
    portfolio_name: str | None = None,
    cash: float = 0.0,
    currency: str = "BRL",
    rebalance_mode: str = "sell_only",
) -> PortfolioReport:
    """
    rebalance_mode:
    - "sell_only" (default): sinaliza apenas venda de holdings em AVOID;
      todo o resto fica HOLD no peso atual. Nunca sugere aumentar peso em
      uma posição já existente -- o capital liberado vira caixa, para ser
      realocado em novos papéis fora deste motor (screener/ranking).
    - "auto": modo histórico, com pesos-alvo calculados por qualidade e
      possíveis sugestões de compra em holdings já existentes.
    """
    if rebalance_mode not in REBALANCE_MODES:
        raise ValueError(
            f"rebalance_mode inválido: {rebalance_mode!r}. "
            f"Use um de {REBALANCE_MODES!r}."
        )

    portfolio = load_portfolio_csv(
        portfolio_path,
        portfolio_name=portfolio_name,
        cash=cash,
        currency=currency,
    )
    portfolio = enrich_portfolio_from_analysis(portfolio, analysis_df)

    allocation = calculate_allocation(portfolio)
    concentration = analyze_allocation_concentration(allocation)
    quality = calculate_allocation_quality(
        allocation,
        concentration=concentration,
    )

    if rebalance_mode == "sell_only":
        rebalance = build_sell_only_plan(
            allocation.portfolio,
            quality=quality,
        )
    else:
        rebalance = build_rebalance_plan(
            allocation.portfolio,
            quality=quality,
        )

    return build_portfolio_report(
        allocation,
        concentration,
        quality,
        rebalance,
    )


def write_portfolio_report(
    report: PortfolioReport,
    output_path: Path,
) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            report.to_dict(),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return path
