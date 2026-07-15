from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from analytics.performance_validation import (
    build_performance_validation_report,
    write_performance_validation_report,
)


def _scored_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "symbol": "AAA",
                "Investment Score": 80.0,
                "Opportunity Score": 70.0,
                "Conviction Score": 85.0,
                "Business Score": 75.0,
                "Valuation Score": 60.0,
                "Financial Score": 90.0,
                "Timing Score": 40.0,
                "Risk Penalty": 5.0,
            },
            {
                "symbol": "BBB",
                "Investment Score": 50.0,
                "Opportunity Score": 55.0,
                "Conviction Score": 45.0,
                "Business Score": 50.0,
                "Valuation Score": 40.0,
                "Financial Score": 60.0,
                "Timing Score": 30.0,
                "Risk Penalty": 0.0,
            },
        ]
    )


def test_score_distribution_summarizes_present_columns() -> None:
    report = build_performance_validation_report(_scored_df())
    dist = report["current_score_distribution"]
    inv = dist["investment_score"]
    assert inv["available"] is True
    assert inv["count"] == 2
    assert inv["average"] == 65.0
    assert inv["minimum"] == 50.0
    assert inv["maximum"] == 80.0


def test_missing_score_column_marked_unavailable_not_invented() -> None:
    df = _scored_df().drop(columns=["Timing Score"])
    report = build_performance_validation_report(df)
    timing = report["current_score_distribution"]["timing_score"]
    assert timing["available"] is False
    assert timing["average"] is None


def test_does_not_claim_alpha_without_historical_data() -> None:
    report = build_performance_validation_report(_scored_df())
    assert report["status"] == "validation_contract_initialized"
    # Nenhuma métrica de performance realizada afirmada -- só listada como
    # trabalho futuro em open_items.
    blob = json.dumps(report).lower()
    for forbidden in ("cagr", "sharpe", "drawdown", "alpha"):
        assert forbidden not in json.dumps(report["current_score_distribution"]).lower()
        assert forbidden in blob  # aparece só em open_items/important_note


def test_portfolio_quality_reads_holdings_count_key() -> None:
    """
    Regressão do bug de conteúdo do WIP original: lia summary["total_positions"]
    (chave inexistente -> sempre None). O PortfolioReport.summary expõe
    holdings_count; o contrato precisa ler essa chave.
    """

    class _FakePortfolioReport:
        def to_dict(self) -> dict:
            return {
                "summary": {
                    "quality_score": 72.5,
                    "quality_rating": "Sólida",
                    "holdings_count": 24,
                    "currency": "USD",
                },
                "allocation": {"by_symbol": {"AAA": 0.5, "BBB": 0.5}},
            }

    report = build_performance_validation_report(
        _scored_df(), portfolio_report=_FakePortfolioReport()
    )
    quality = report["portfolio_quality"]
    assert quality["total_positions"] == 24
    assert quality["quality_score"] == 72.5
    assert quality["quality_rating"] == "Sólida"
    assert quality["currency"] == "USD"
    assert quality["allocation_by_symbol_available"] is True
    assert report["coverage"]["portfolio_report_available"] is True


def test_outcome_validation_reads_hit_rate() -> None:
    class _FakeOutcomeReport:
        def to_dict(self) -> dict:
            return {
                "hit_rate": {
                    "eligible_count": 10,
                    "hit_count": 6,
                    "hit_rate": 0.6,
                }
            }

    report = build_performance_validation_report(
        _scored_df(), outcome_report=_FakeOutcomeReport()
    )
    outcome = report["outcome_validation"]
    assert outcome["eligible_count"] == 10
    assert outcome["hit_count"] == 6
    assert outcome["hit_rate"] == 0.6


def test_degrades_gracefully_without_reports() -> None:
    report = build_performance_validation_report(_scored_df())
    assert report["coverage"]["portfolio_report_available"] is False
    assert report["coverage"]["outcome_report_available"] is False
    assert report["portfolio_quality"]["total_positions"] is None
    assert report["portfolio_quality"]["allocation_by_symbol_available"] is False
    assert report["outcome_validation"]["hit_rate"] is None


def test_write_report_roundtrips(tmp_path: Path) -> None:
    report = build_performance_validation_report(
        _scored_df(), snapshot_date="2026-07-14T00:00:00"
    )
    out = tmp_path / "nested" / "performance_validation.json"
    written = write_performance_validation_report(report, out)
    assert written == out
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded["snapshot_date"] == "2026-07-14T00:00:00"
    assert loaded["coverage"]["companies_analyzed"] == 2
