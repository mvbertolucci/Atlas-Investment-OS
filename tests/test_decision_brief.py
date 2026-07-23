from __future__ import annotations

from datetime import datetime

from portfolio.report import PortfolioReport
from reports.decision_brief import render_decision_brief
from reports.report_models import CompanyReport


def _report(symbol: str, name: str, decision: str) -> CompanyReport:
    return CompanyReport(
        symbol=symbol,
        company_name=name,
        decision=decision,
        decision_rating=decision,
        suggested_action="Agir",
        investment_thesis="Tese mensurável",
        opportunity_score=80,
        conviction_score=70,
        decision_confidence=65,
        data_coverage=64,
        risk_penalty=3,
        decision_drivers=("Driver medido",),
        risks=("Risco medido",),
    )


def test_decision_brief_combines_actions_names_theses_and_metrics() -> None:
    portfolio = PortfolioReport(
        portfolio_name="Carteira",
        generated_at=datetime(2026, 7, 22),
        summary={"currency": "USD", "total_value": 1000, "quality_score": 50, "quality_rating": "WEAK", "cash_weight": 0, "largest_position_weight": 1},
        allocation={"by_symbol": {"AAA": 1}}, concentration={}, quality={},
        rebalance={"actions": [{"symbol": "AAA", "action": "SELL", "reason": "Risco confirmado"}]},
    )
    html = render_decision_brief([_report("AAA", "Alpha", "AVOID"), _report("BBB", "Beta", "BUY")], portfolio_report=portfolio)
    assert "Alpha (AAA)" in html
    assert "Beta (BBB)" in html
    assert "Tese mensurável" in html
    assert "Opportunity" in html
    assert "Risco confirmado" in html
