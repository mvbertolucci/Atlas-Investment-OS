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
