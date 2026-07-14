from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from portfolio.allocation import calculate_allocation
from portfolio.concentration import analyze_allocation_concentration
from portfolio.loader import load_portfolio_csv
from portfolio.models import Holding, Portfolio
from portfolio.quality import calculate_allocation_quality
from portfolio.rebalance import build_rebalance_plan, build_stateful_sell_plan
from portfolio.report import PortfolioReport, build_portfolio_report
from portfolio.sell_rules import SellRulesPolicy, load_sell_rules_policy
from reports.report_engine import build_company_reports

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SELL_RULES_POLICY_PATH = ROOT / "config" / "sell_rules.yaml"


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
        origin = holding.origin

        if row is not None:
            if current_price is None:
                current_price = _clean_float(row.get("price"))
            sector = sector or _clean_text(row.get("sector"))
            industry = industry or _clean_text(row.get("industry"))
            country = country or _clean_text(row.get("country"))
            currency = currency or _clean_text(row.get("currency"))
            # A linha do DataFrame analisado (tagueada por
            # run_all.merge_watchlist_with_portfolio) é a fonte autoritativa
            # de proveniência -- nunca assumida, sempre lida do que o merge
            # de fato tagueou. Isso é o que permite build_sell_only_plan
            # detectar e recusar um holding cuja origem verificada não seja
            # "portfolio".
            row_origin = _clean_text(row.get("origin"))
            if row_origin:
                origin = row_origin

        # Sem nenhuma linha correspondente no DataFrame analisado (holding
        # sem CompanyReport, por exemplo), não há como verificar a
        # proveniência -- mantém o comportamento anterior de tratar como
        # posição real, já que todo Holding carregado de
        # config/portfolio.csv é, por definição, uma posição real.
        origin = origin or "portfolio"

        holdings.append(
            replace(
                holding,
                current_price=current_price,
                sector=sector,
                industry=industry,
                country=country,
                currency=currency or "USD",
                origin=origin,
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
    sell_rules_policy: SellRulesPolicy | None = None,
    previous_by_symbol: Mapping[str, Mapping[str, Any]] | None = None,
    baseline_status: str = "first_run",
    previous_run_at: pd.Timestamp | None = None,
    current_run_at: str | datetime | pd.Timestamp | None = None,
) -> PortfolioReport:
    """
    rebalance_mode:
    - "sell_only" (default): motor de venda com regras nomeadas
      (portfolio.sell_rules), stateful entre runs. Nunca sugere aumentar
      peso em uma posição já existente -- o capital liberado vira caixa,
      para ser realocado em novos papéis fora deste motor (screener/
      ranking). `sell_rules_policy` é opcional -- ausente, carrega
      config/sell_rules.yaml (a política canônica governada). Os demais
      parâmetros de contexto (`previous_by_symbol`, `baseline_status`,
      `previous_run_at`, `current_run_at`) também são opcionais e,
      ausentes, tratam a execução como primeiro run (sem baseline para
      comparar).
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
        policy = sell_rules_policy or load_sell_rules_policy(
            DEFAULT_SELL_RULES_POLICY_PATH
        )
        rebalance = build_stateful_sell_plan(
            allocation.portfolio,
            analysis_df,
            sell_rules_policy=policy,
            previous_by_symbol=previous_by_symbol,
            baseline_status=baseline_status,
            previous_run_at=previous_run_at,
            current_run_at=current_run_at,
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
