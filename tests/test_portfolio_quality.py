from __future__ import annotations

import pytest

from portfolio.allocation import calculate_allocation
from portfolio.concentration import (
    ConcentrationPolicy,
    analyze_allocation_concentration,
)
from portfolio.models import Holding, Portfolio
from portfolio.quality import (
    PortfolioQualityError,
    QualityPolicy,
    calculate_allocation_quality,
    calculate_portfolio_quality,
    classify_portfolio_quality,
)
from reports.report_models import CompanyReport


def _report(
    symbol: str,
    *,
    investment: float,
    opportunity: float,
    conviction: float,
    decision_confidence: float,
) -> CompanyReport:
    return CompanyReport(
        symbol=symbol,
        investment_score=investment,
        opportunity_score=opportunity,
        conviction_score=conviction,
        decision_confidence=decision_confidence,
    )


def test_weighted_portfolio_scores() -> None:
    portfolio = Portfolio(
        name="Quality",
        holdings=(
            Holding(
                symbol="AAA",
                quantity=1,
                average_price=80,
                current_price=100,
                company_report=_report(
                    "AAA",
                    investment=90,
                    opportunity=80,
                    conviction=85,
                    decision_confidence=88,
                ),
            ),
            Holding(
                symbol="BBB",
                quantity=1,
                average_price=40,
                current_price=50,
                company_report=_report(
                    "BBB",
                    investment=60,
                    opportunity=70,
                    conviction=65,
                    decision_confidence=68,
                ),
            ),
        ),
    )

    result = calculate_portfolio_quality(
        portfolio
    )

    assert result.investment_score == 80.0
    assert result.opportunity_score == pytest.approx(
        76.7,
        abs=0.1,
    )
    assert result.conviction_score == pytest.approx(
        78.3,
        abs=0.1,
    )
    assert result.decision_confidence == pytest.approx(
        81.3,
        abs=0.1,
    )
    assert result.base_quality_score is not None
    assert result.portfolio_quality_score is not None


def test_quality_score_uses_configured_weights() -> None:
    portfolio = Portfolio(
        name="Policy",
        holdings=(
            Holding(
                symbol="AAA",
                quantity=1,
                average_price=100,
                current_price=100,
                company_report=_report(
                    "AAA",
                    investment=100,
                    opportunity=0,
                    conviction=0,
                    decision_confidence=0,
                ),
            ),
        ),
    )

    result = calculate_portfolio_quality(
        portfolio,
        policy=QualityPolicy(
            investment_weight=1.0,
            opportunity_weight=0.0,
            conviction_weight=0.0,
            decision_confidence_weight=0.0,
            concentration_penalty_weight=0.0,
            missing_report_penalty=0.0,
        ),
    )

    assert result.base_quality_score == 100.0
    assert result.portfolio_quality_score == 100.0
    assert result.rating == "EXCELLENT"


def test_missing_report_reduces_quality() -> None:
    portfolio = Portfolio(
        name="Missing",
        holdings=(
            Holding(
                symbol="AAA",
                quantity=1,
                average_price=100,
                current_price=100,
                company_report=_report(
                    "AAA",
                    investment=80,
                    opportunity=80,
                    conviction=80,
                    decision_confidence=80,
                ),
            ),
            Holding(
                symbol="BBB",
                quantity=1,
                average_price=100,
                current_price=100,
                company_report=None,
            ),
        ),
    )

    result = calculate_portfolio_quality(
        portfolio
    )

    assert result.missing_report_symbols == ("BBB",)
    assert result.missing_report_penalty == 5.0
    assert result.covered_weight == 0.5
    assert result.has_full_coverage is False
    assert any(
        "BBB" in warning
        for warning in result.warnings
    )


def test_concentration_penalty_is_applied() -> None:
    portfolio = Portfolio(
        name="Concentrated",
        holdings=(
            Holding(
                symbol="AAA",
                quantity=9,
                average_price=100,
                current_price=100,
                sector="Technology",
                country="USA",
                currency="USD",
                company_report=_report(
                    "AAA",
                    investment=90,
                    opportunity=90,
                    conviction=90,
                    decision_confidence=90,
                ),
            ),
            Holding(
                symbol="BBB",
                quantity=1,
                average_price=100,
                current_price=100,
                sector="Technology",
                country="USA",
                currency="USD",
                company_report=_report(
                    "BBB",
                    investment=90,
                    opportunity=90,
                    conviction=90,
                    decision_confidence=90,
                ),
            ),
        ),
    )

    allocation = calculate_allocation(
        portfolio
    )
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

    result = calculate_allocation_quality(
        allocation,
        concentration=concentration,
    )

    assert result.base_quality_score == 90.0
    assert result.concentration_penalty > 0
    assert (
        result.portfolio_quality_score
        < result.base_quality_score
    )


def test_quality_is_unavailable_without_reports() -> None:
    portfolio = Portfolio(
        name="No Reports",
        cash=1000,
        holdings=(
            Holding(
                symbol="AAA",
                quantity=1,
                average_price=100,
                current_price=100,
            ),
        ),
    )

    result = calculate_portfolio_quality(
        portfolio
    )

    assert result.base_quality_score is None
    assert result.portfolio_quality_score is None
    assert result.rating == "UNAVAILABLE"


def test_invalid_policy_is_rejected() -> None:
    portfolio = Portfolio(
        name="Invalid Policy",
        cash=1000,
    )

    with pytest.raises(PortfolioQualityError):
        calculate_portfolio_quality(
            portfolio,
            policy=QualityPolicy(
                investment_weight=0.50,
                opportunity_weight=0.50,
                conviction_weight=0.50,
                decision_confidence_weight=0.00,
            ),
        )


@pytest.mark.parametrize(
    ("score", "rating"),
    [
        (90, "EXCELLENT"),
        (80, "GOOD"),
        (65, "FAIR"),
        (50, "WEAK"),
        (30, "POOR"),
        (None, "UNAVAILABLE"),
    ],
)
def test_quality_classification(
    score: float | None,
    rating: str,
) -> None:
    assert (
        classify_portfolio_quality(score)
        == rating
    )


def test_result_is_serializable() -> None:
    portfolio = Portfolio(
        name="Serializable",
        holdings=(
            Holding(
                symbol="AAA",
                quantity=1,
                average_price=100,
                current_price=100,
                company_report=_report(
                    "AAA",
                    investment=80,
                    opportunity=75,
                    conviction=85,
                    decision_confidence=82,
                ),
            ),
        ),
    )

    result = calculate_portfolio_quality(
        portfolio
    )
    data = result.to_dict()

    assert "portfolio_quality_score" in data
    assert isinstance(data["warnings"], list)
    assert data["rating"] in {
        "EXCELLENT",
        "GOOD",
        "FAIR",
        "WEAK",
        "POOR",
    }
