from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from portfolio.report import PortfolioReport
from reports.morning_brief import (
    build_morning_brief_dataframe,
    build_morning_brief_tables,
    build_top_opportunities,
    render_morning_brief,
    write_morning_brief,
)


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "symbol": "AAA",
                "name": "Alpha",
                "Opportunity Score": 90.0,
                "Conviction Score": 88.0,
                "Decision": "BUY",
                "Decision Rating": "★★★★ Comprar",
                "Suggested Action": "Considerar compra gradual",
                "Decision Confidence": 89.0,
                "Investment Thesis": "Tese Alpha",
                "Thesis Risks": "Risco A",
                "Decision Drivers": "Alta convicção",
                "Risk Penalty": 5.0,
            },
            {
                "symbol": "BBB",
                "name": "Beta",
                "Opportunity Score": 70.0,
                "Conviction Score": 72.0,
                "Decision": "ACCUMULATE",
                "Decision Rating": "★★★ Acumular",
                "Suggested Action": "Considerar aumentar posição",
                "Decision Confidence": 74.0,
                "Investment Thesis": "Tese Beta",
                "Thesis Risks": "Nenhum risco crítico identificado",
                "Decision Drivers": "Opportunity atrativa",
                "Risk Penalty": 18.0,
            },
        ]
    )


def _portfolio_report() -> PortfolioReport:
    return PortfolioReport(
        portfolio_name="Atlas Portfolio",
        generated_at=datetime(2026, 7, 12, 9, 0, 0),
        summary={
            "portfolio_name": "Atlas Portfolio",
            "currency": "BRL",
            "holdings_count": 2,
            "total_value": 2500.0,
            "cash_weight": 0.10,
            "quality_rating": "GOOD",
            "quality_score": 78.5,
            "concentration_score": 62.0,
            "diversification_score": 74.0,
            "largest_position_weight": 0.55,
        },
        allocation={
            "by_symbol": {
                "AAA": 0.55,
                "BBB": 0.35,
            },
            "cash_weight": 0.10,
        },
        concentration={},
        quality={},
        rebalance={
            "actions": [
                {
                    "symbol": "BBB",
                    "action": "SELL",
                    "current_weight": 0.35,
                    "target_weight": 0.25,
                    "trade_value": -250.0,
                    "reason": "Reduzir risco agregado",
                    "priority": 1,
                },
                {
                    "symbol": "AAA",
                    "action": "HOLD",
                    "current_weight": 0.55,
                    "target_weight": 0.55,
                    "trade_value": 0.0,
                    "reason": "Manter posição",
                    "priority": 2,
                },
            ],
        },
        warnings=("Concentração elevada em AAA.",),
    )


def test_top_opportunities_use_company_reports() -> None:
    result = build_top_opportunities(
        _frame(),
        top_count=1,
    )

    assert len(result) == 1
    assert result.loc[0, "symbol"] == "AAA"
    assert result.loc[0, "Investment Thesis"] == "Tese Alpha"


def test_brief_tables_expose_domain_reports(
    tmp_path: Path,
) -> None:
    data = build_morning_brief_tables(
        current_df=_frame(),
        database_path=tmp_path / "history.db",
        top_count=2,
    )

    assert len(data["company_reports"]) == 2
    assert data["top_reports"][0].symbol == "AAA"
    assert data["top_reports"][0].investment_thesis == "Tese Alpha"


def test_render_brief_uses_company_report_fields(
    tmp_path: Path,
) -> None:
    text = render_morning_brief(
        current_df=_frame(),
        database_path=tmp_path / "history.db",
        top_count=1,
    )

    assert "AAA" in text
    assert "Decisão: ★★★★ Comprar" in text
    assert "Conviction: 88.0" in text
    assert "Tese: Tese Alpha" in text
    assert "Riscos: Risco A" in text
    assert "Ação: Considerar compra gradual" in text
    assert "Drivers: Alta convicção" in text


def test_brief_tables_expose_portfolio_intelligence(
    tmp_path: Path,
) -> None:
    data = build_morning_brief_tables(
        current_df=_frame(),
        database_path=tmp_path / "history.db",
        top_count=2,
        portfolio_report=_portfolio_report(),
    )

    portfolio = data["portfolio"]

    assert portfolio is not None
    assert portfolio["summary"]["quality_score"] == 78.5
    assert portfolio["largest_positions"][0]["symbol"] == "AAA"
    assert portfolio["highest_conviction"][0]["symbol"] == "AAA"
    assert portfolio["highest_risk"][0]["symbol"] == "BBB"
    assert portfolio["rebalance_actions"][0]["action"] == "SELL"


def test_render_brief_includes_advisory_portfolio_sections(
    tmp_path: Path,
) -> None:
    text = render_morning_brief(
        current_df=_frame(),
        database_path=tmp_path / "history.db",
        top_count=2,
        portfolio_report=_portfolio_report(),
    )

    assert "PORTFOLIO INTELLIGENCE" in text
    assert "Carteira: Atlas Portfolio" in text
    assert "Valor total: BRL 2,500.00" in text
    assert "Qualidade: 78.5 (GOOD)" in text
    assert "- AAA: 55.0%" in text
    assert "- BBB: penalidade 18.0" in text
    assert "Rebalanceamento consultivo:" in text
    assert "nenhuma ordem é executada" in text
    assert "- BBB: SELL | 35.0% → 25.0%" in text
    assert "Concentração elevada em AAA." in text


def test_brief_without_portfolio_preserves_company_only_contract(
    tmp_path: Path,
) -> None:
    text = render_morning_brief(
        current_df=_frame(),
        database_path=tmp_path / "history.db",
    )
    dataframe = build_morning_brief_dataframe(
        current_df=_frame(),
        database_path=tmp_path / "history.db",
    )

    assert "PORTFOLIO INTELLIGENCE" not in text
    assert not dataframe["Section"].str.startswith(
        "Portfolio"
    ).any()


def test_write_morning_brief_persists_portfolio_section(
    tmp_path: Path,
) -> None:
    output = write_morning_brief(
        current_df=_frame(),
        database_path=tmp_path / "history.db",
        output_path=tmp_path / "morning_brief.md",
        portfolio_report=_portfolio_report(),
    )

    content = output.read_text(encoding="utf-8")

    assert "PORTFOLIO INTELLIGENCE" in content
    assert "Rebalanceamento consultivo" in content
