from __future__ import annotations

import pytest

from reports.report_models import (
    CompanyReport,
    MarketSummary,
    PortfolioReport,
)


def test_company_report_normalizes_values() -> None:
    report = CompanyReport(
        symbol=" nvda ",
        company_name="NVIDIA",
        decision="BUY",
        opportunity_score=120,
        conviction_score=-5,
        strengths="Business forte; Valuation atrativa",
        risks=["Ciclicidade", "Ciclicidade"],
    )

    assert report.symbol == "NVDA"
    assert report.opportunity_score == 100.0
    assert report.conviction_score == 0.0
    assert report.strengths == (
        "Business forte",
        "Valuation atrativa",
    )
    assert report.risks == ("Ciclicidade",)


def test_company_report_requires_symbol() -> None:
    with pytest.raises(ValueError):
        CompanyReport(symbol="")


def test_company_report_helpers() -> None:
    report = CompanyReport(
        symbol="AMD",
        company_name="Advanced Micro Devices",
        decision="ACCUMULATE",
        risks=("Ciclicidade",),
    )

    assert report.display_name == (
        "Advanced Micro Devices (AMD)"
    )
    assert report.has_risks is True
    assert report.is_actionable is True


def test_company_report_scorecard() -> None:
    report = CompanyReport(
        symbol="AAA",
        investment_score=80,
        opportunity_score=85,
        conviction_score=90,
    )

    scorecard = report.scorecard()

    assert scorecard["Investment Score"] == 80.0
    assert scorecard["Opportunity Score"] == 85.0
    assert scorecard["Conviction Score"] == 90.0


def test_company_report_to_dict_is_serializable() -> None:
    report = CompanyReport(
        symbol="AAA",
        decision_drivers=("Alta convicção",),
        strengths=("Business forte",),
        data_coverage=88,
        source_quality=80,
        data_freshness=100,
        missing_required_features="valuation:pe",
        risk_evidence_missing=("short_float",),
        observed_risk_penalty=4,
        risk_uncertainty_penalty=3,
    )

    data = report.to_dict()

    assert data["symbol"] == "AAA"
    assert data["decision_drivers"] == ["Alta convicção"]
    assert data["data_coverage"] == 88.0
    assert data["source_quality"] == 80.0
    assert data["data_freshness"] == 100.0
    assert data["missing_required_features"] == ["valuation:pe"]
    assert data["risk_evidence_missing"] == ["short_float"]
    assert data["observed_risk_penalty"] == 4.0
    assert data["risk_uncertainty_penalty"] == 3.0
    assert isinstance(data["generated_at"], str)


def test_market_summary_normalizes_counts_and_scores() -> None:
    summary = MarketSummary(
        companies_analyzed=-1,
        total_alerts=4,
        average_opportunity=110,
        maximum_opportunity=95,
    )

    assert summary.companies_analyzed == 0
    assert summary.total_alerts == 4
    assert summary.average_opportunity == 100.0
    assert summary.maximum_opportunity == 95.0


def test_portfolio_report_contract() -> None:
    report = PortfolioReport(
        portfolio_name="Long Term",
        holdings_count=8,
        total_value=100000,
        average_investment_score=76,
        observations="Boa qualidade; Revisar concentração",
    )

    assert report.portfolio_name == "Long Term"
    assert report.holdings_count == 8
    assert report.total_value == 100000.0
    assert report.observations == (
        "Boa qualidade",
        "Revisar concentração",
    )


def test_portfolio_report_requires_name() -> None:
    with pytest.raises(ValueError):
        PortfolioReport(portfolio_name="")
