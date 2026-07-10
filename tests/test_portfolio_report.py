from __future__ import annotations

import pytest

from portfolio.allocation import calculate_allocation
from portfolio.concentration import (
    ConcentrationPolicy,
    analyze_allocation_concentration,
)
from portfolio.models import Holding, Portfolio
from portfolio.quality import calculate_allocation_quality
from portfolio.rebalance import (
    RebalancePolicy,
    build_rebalance_plan,
)
from portfolio.report import build_portfolio_report
from reports.report_models import CompanyReport


def _company_report(
    symbol: str,
    decision: str,
    score: float,
) -> CompanyReport:
    return CompanyReport(
        symbol=symbol,
        decision=decision,
        investment_score=score,
        opportunity_score=score,
        conviction_score=score,
        decision_confidence=score,
    )


def _build_components():
    portfolio = Portfolio(
        name="Atlas Portfolio",
        cash=1000,
        currency="BRL",
        holdings=(
            Holding(
                symbol="AAA",
                quantity=10,
                average_price=80,
                current_price=100,
                sector="Technology",
                country="USA",
                currency="USD",
                company_report=_company_report(
                    "AAA",
                    "BUY",
                    90,
                ),
            ),
            Holding(
                symbol="BBB",
                quantity=10,
                average_price=40,
                current_price=50,
                sector="Financials",
                country="Brazil",
                currency="BRL",
                company_report=_company_report(
                    "BBB",
                    "HOLD",
                    70,
                ),
            ),
        ),
    )

    allocation = calculate_allocation(portfolio)

    concentration = analyze_allocation_concentration(
        allocation,
        policy=ConcentrationPolicy(
            max_position_weight=1.0,
            max_top_5_weight=1.0,
            max_sector_weight=1.0,
            max_country_weight=1.0,
            max_currency_weight=1.0,
            minimum_cash_weight=0.0,
        ),
    )

    quality = calculate_allocation_quality(
        allocation,
        concentration=concentration,
    )

    rebalance = build_rebalance_plan(
        allocation.portfolio,
        quality=quality,
        policy=RebalancePolicy(
            tolerance=0.02,
            minimum_trade_value=0,
            allow_sells=True,
            maximum_position_weight=0.80,
            minimum_cash_weight=0.10,
        ),
    )

    return (
        allocation,
        concentration,
        quality,
        rebalance,
    )


def test_portfolio_report_consolidates_engines() -> None:
    components = _build_components()

    report = build_portfolio_report(*components)

    assert report.portfolio_name == "Atlas Portfolio"
    assert report.summary["holdings_count"] == 2
    assert report.summary["total_value"] == 2500.0
    assert report.summary["quality_rating"] in {
        "EXCELLENT",
        "GOOD",
        "FAIR",
        "WEAK",
        "POOR",
    }
    assert "by_symbol" in report.allocation
    assert "concentration_score" in report.concentration
    assert "portfolio_quality_score" in report.quality
    assert "actions" in report.rebalance


def test_portfolio_report_is_serializable() -> None:
    report = build_portfolio_report(
        *_build_components()
    )

    data = report.to_dict()

    assert data["portfolio_name"] == "Atlas Portfolio"
    assert isinstance(data["generated_at"], str)
    assert isinstance(data["warnings"], list)
    assert isinstance(data["rebalance"]["actions"], list)


def test_portfolio_report_deduplicates_warnings() -> None:
    allocation, concentration, quality, rebalance = (
        _build_components()
    )

    report = build_portfolio_report(
        allocation,
        concentration,
        quality,
        rebalance,
    )

    assert len(report.warnings) == len(
        set(report.warnings)
    )


def test_portfolio_report_validates_inputs() -> None:
    allocation, concentration, quality, rebalance = (
        _build_components()
    )

    with pytest.raises(TypeError):
        build_portfolio_report(
            object(),
            concentration,
            quality,
            rebalance,
        )

    with pytest.raises(TypeError):
        build_portfolio_report(
            allocation,
            object(),
            quality,
            rebalance,
        )
