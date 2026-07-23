from __future__ import annotations

from pathlib import Path

import pytest

from decision.cockpit import render_decision_cockpit, write_decision_cockpit
from decision.queue import build_decision_queue
from portfolio.scenario import build_sell_scenario


def _queue():
    return build_decision_queue(
        priority={
            "sell": {
                "items": [
                    {
                        "symbol": "<FMC>",
                        "action": "SELL",
                        "reason": "distress & risco",
                        "priority": 0,
                    }
                ]
            }
        },
        company_context={
            "<FMC>": {
                "company_name": "FMC Corporation",
                "investment_thesis": "Tese com evidência.",
            }
        },
        active_watchlist=(
            {
                "symbol": "KGC",
                "effective_state": "promotion_ready",
                "state_reason": "gatilho",
                "analytical_origin": "adr",
            },
        ),
        generated_at="2026-07-22T15:00:00",
    )


def test_renders_responsive_cockpit_and_escapes_content() -> None:
    html = render_decision_cockpit(_queue())
    assert "Atlas Decision Cockpit" in html
    assert 'name="viewport"' in html
    assert "@media(max-width:800px)" in html
    assert "&lt;FMC&gt;" in html
    assert "distress &amp; risco" in html
    assert "REVIEW_FOR_PURCHASE" in html
    assert "FMC Corporation" in html
    assert "Tese com evidência." in html
    assert "Nenhum item nesta fila." in html


def test_write_is_atomic_and_validates_type(tmp_path: Path) -> None:
    output = write_decision_cockpit(_queue(), tmp_path / "reports" / "cockpit.html")
    assert output.exists()
    assert not output.with_suffix(".html.tmp").exists()
    with pytest.raises(TypeError):
        render_decision_cockpit(object())


def test_renders_sell_scenario_summary() -> None:
    scenario = build_sell_scenario(
        {
            "summary": {"total_value": 1000, "cash": 0, "currency": "USD"},
            "holdings": [{"symbol": "AAA", "market_value": 200, "sector": "Tech"}],
            "rebalance": {
                "actions": [{"symbol": "AAA", "action": "SELL", "trade_value": -200}]
            },
        }
    )
    html = render_decision_cockpit(_queue(), scenario=scenario)
    assert "Impacto se executar SELL/TRIM" in html
    assert "Caixa liberado" in html
    assert "20.0%" in html


def test_renders_human_review_summary() -> None:
    html = render_decision_cockpit(
        _queue(),
        journal_summary={"accepted": 2, "rejected": 1, "deferred": 3, "total_events": 7},
    )
    assert "Revisões humanas registradas" in html
    assert "Aceitas:</b> 2" in html
    assert "Eventos:</b> 7" in html


def test_renders_execution_ledger_summary() -> None:
    html = render_decision_cockpit(
        _queue(),
        execution_summary={
            "fills": 2,
            "decisions_executed": 1,
            "gross_sell_value": 500.0,
            "fees": 2.5,
            "net_cash_delta": 497.5,
        },
    )
    assert "Execuções reais informadas" in html
    assert "Preenchimentos:</b> 2" in html
    assert "Caixa líquido:</b> 497.5" in html


def test_renders_reconciliation_summary() -> None:
    html = render_decision_cockpit(
        _queue(), reconciliation_summary={"confirmed": 2, "partial": 1,
        "not_reflected": 1, "variance": 1, "unverifiable": 0}
    )
    assert "Reconciliação de custódia" in html
    assert "Confirmadas:</b> 2" in html
    assert "Divergências:</b> 1" in html


def test_renders_delta_section_with_transition_and_change() -> None:
    delta = {
        "baseline_generated_at": "2026-07-21T15:00:00",
        "summary": {"entered": 1, "exited": 0, "changed": 1,
                    "action_transitions": 1, "unchanged": 40},
        "action_transitions": [
            {"symbol": "FMC", "company_name": "FMC Corporation", "action": "SELL",
             "group": "EXECUTE", "from_action": "REVISAR", "from_group": "INVESTIGATE"}
        ],
        "changed": [
            {"symbol": "KGC", "company_name": "Kinross", "action": "REVIEW",
             "changes": [{"field": "opportunity_score", "from": 50.0, "to": 42.0, "delta": -8.0}]}
        ],
        "entered": [
            {"symbol": "MU", "company_name": "Micron", "action": "WAIT_TRIGGER", "group": "WAIT"}
        ],
        "exited": [],
    }
    html = render_decision_cockpit(_queue(), delta=delta)
    assert "Mudou desde a última execução" in html
    assert "Mudança de ação (1)" in html
    assert "REVISAR" in html and "SELL" in html
    assert "Opportunity 50.0→42.0 (-8.0)" in html
    assert "40 itens sem mudança" in html


def test_delta_section_first_run_has_no_baseline() -> None:
    html = render_decision_cockpit(_queue(), delta={"baseline_generated_at": None})
    assert "sem base de comparação" in html


def test_omits_delta_section_when_absent() -> None:
    html = render_decision_cockpit(_queue())
    assert "Mudou desde a última execução" not in html


def test_renders_three_tier_hierarchy() -> None:
    html = render_decision_cockpit(_queue())
    # Ação vem antes de Oportunidades, que vem antes de Acompanhar (colapsado).
    assert html.index("Agir agora") < html.index("Oportunidades") < html.index("Acompanhar")
    assert "<details>" in html
    assert "sem ação — clique para expandir" in html


def test_renders_buy_opportunities_section() -> None:
    html = render_decision_cockpit(
        _queue(),
        opportunities=(
            {
                "symbol": "NVDA",
                "company_name": "NVIDIA",
                "action": "CANDIDATA",
                "decision_drivers": ("Opportunity alto", "Convicção alta"),
                "investment_thesis": "Liderança em IA.",
                "opportunity_score": 88.0,
                "conviction_score": 75.0,
            },
        ),
    )
    assert "NVIDIA" in html
    assert "CANDIDATA" in html
    assert "Opportunity alto; Convicção alta" in html
    assert "fora da carteira" in html


def test_renders_portfolio_health_and_outcomes() -> None:
    html = render_decision_cockpit(
        _queue(),
        portfolio_health={
            "currency": "USD",
            "total_value": "1,000.00",
            "quality_score": "72.0",
            "quality_rating": "Bom",
            "cash_weight": "5.0%",
            "largest_position_weight": "12.0%",
            "warnings": ("Concentração setorial.",),
        },
        outcomes_line="Hit rate direcional: 60.0% (6/10).",
    )
    assert "Saúde da carteira" in html
    assert "1,000.00" in html
    assert "Concentração setorial." in html
    assert "Evidência histórica" in html
    assert "Hit rate direcional: 60.0% (6/10)." in html


def test_monitor_items_go_into_collapsed_section() -> None:
    # KGC (promotion_ready -> EXECUTE) e itens MONITOR; o card MONITOR fica
    # dentro do <details> de Acompanhar, não no topo.
    html = render_decision_cockpit(_queue())
    head, _, tail = html.partition("<details>")
    assert "Agir agora" in head
    assert "Acompanhar" in tail or "Acompanhar" in html
