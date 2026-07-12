from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from portfolio.loader import load_portfolio_csv
from portfolio.pipeline import (
    build_portfolio_intelligence,
    enrich_portfolio_from_analysis,
    write_portfolio_report,
)


def _analysis_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": ["AAA", "BBB"],
            "name": ["Alpha", "Beta"],
            "price": [12.0, 25.0],
            "sector": ["Technology", "Financials"],
            "industry": ["Software", "Banks"],
            "country": ["USA", "Brazil"],
            "Decision": ["BUY", "HOLD"],
            "Decision Rating": ["HIGH", "MEDIUM"],
            "Suggested Action": ["ACCUMULATE", "HOLD"],
            "Decision Confidence": [88, 70],
            "Investment Score": [90, 70],
            "Opportunity Score": [85, 65],
            "Conviction Score": [88, 68],
            "Business Score": [92, 75],
            "Valuation Score": [80, 60],
            "Financial Score": [90, 72],
            "Timing Score": [82, 58],
            "Confidence Score": [88, 70],
            "Risk Penalty": [5, 10],
        }
    )


def _portfolio_file(tmp_path: Path) -> Path:
    path = tmp_path / "portfolio.csv"
    pd.DataFrame(
        {
            "symbol": ["AAA", "BBB"],
            "quantity": [10, 5],
            "average_price": [10, 20],
            "current_price": [None, 24],
            "currency": ["USD", "BRL"],
            "sector": ["", "Financials"],
            "country": ["", "Brazil"],
        }
    ).to_csv(path, index=False)
    return path


def test_enrich_portfolio_links_reports_and_missing_market_data(
    tmp_path: Path,
) -> None:
    portfolio = load_portfolio_csv(_portfolio_file(tmp_path))

    enriched = enrich_portfolio_from_analysis(
        portfolio,
        _analysis_frame(),
    )

    aaa = enriched.holding("AAA")
    bbb = enriched.holding("BBB")

    assert aaa is not None
    assert aaa.current_price == 12.0
    assert aaa.sector == "Technology"
    assert aaa.country == "USA"
    assert aaa.company_report is not None
    assert aaa.company_report.decision == "BUY"

    assert bbb is not None
    assert bbb.current_price == 24.0
    assert bbb.company_report is not None


def test_build_portfolio_intelligence_runs_all_engines(
    tmp_path: Path,
) -> None:
    report = build_portfolio_intelligence(
        _portfolio_file(tmp_path),
        _analysis_frame(),
        portfolio_name="Test Portfolio",
        cash=100,
        currency="BRL",
    )

    assert report.portfolio_name == "Test Portfolio"
    assert report.summary["holdings_count"] == 2
    assert report.summary["quality_score"] is not None
    assert "by_symbol" in report.allocation
    assert "actions" in report.rebalance


def test_write_portfolio_report_creates_json(
    tmp_path: Path,
) -> None:
    report = build_portfolio_intelligence(
        _portfolio_file(tmp_path),
        _analysis_frame(),
    )

    output = write_portfolio_report(
        report,
        tmp_path / "output" / "portfolio_report.json",
    )

    data = json.loads(output.read_text(encoding="utf-8"))

    assert output.exists()
    assert data["portfolio_name"] == "portfolio"
    assert isinstance(data["warnings"], list)
