from __future__ import annotations

import json
from pathlib import Path

from decision.queue import build_decision_queue, write_decision_queue


def test_consolidates_portfolio_and_watchlist_without_redeciding() -> None:
    priority = {
        "sell": {
            "items": [
                {"symbol": "FMC", "action": "SELL", "reason": "distress", "priority": 0},
                {"symbol": "JNJ", "action": "REVISAR", "reason": "confirmar", "priority": 20},
            ]
        }
    }
    active = (
        {
            "symbol": "KGC",
            "effective_state": "promotion_ready",
            "state_reason": "condição de promoção disparada",
            "analytical_origin": "adr",
            "entry_rank": 1,
            "entry_score": 72.2,
        },
        {
            "symbol": "MU",
            "effective_state": "waiting_trigger",
            "state_reason": "aguardando",
        },
    )

    queue = build_decision_queue(
        priority=priority,
        active_watchlist=active,
        portfolio_actions=(
            {"symbol": "MSFT", "action": "ACOMPANHAR", "reason": "relativo"},
        ),
        company_context={
            "FMC": {
                "company_name": "FMC Corporation",
                "investment_thesis": "Recuperar geração de caixa.",
                "opportunity_score": 30.0,
                "conviction_score": 40.0,
                "decision_confidence": 62.0,
                "data_coverage": 62.0,
                "risk_penalty": 55.0,
            }
        },
        generated_at="2026-07-22T00:00:00",
    ).to_dict()

    assert queue["summary"] == {
        "execute": 2,
        "investigate": 1,
        "wait": 1,
        "monitor": 1,
    }
    execute = queue["groups"]["EXECUTE"]
    assert [item["symbol"] for item in execute] == ["FMC", "KGC"]
    assert execute[0]["action"] == "SELL"
    assert execute[0]["engine"] == "portfolio.sell_rules"
    assert execute[0]["company_name"] == "FMC Corporation"
    assert execute[0]["investment_thesis"] == "Recuperar geração de caixa."
    assert execute[0]["risk_penalty"] == 55.0
    assert execute[1]["action"] == "REVIEW_FOR_PURCHASE"
    assert execute[1]["advisory_only"] is True
    assert queue["groups"]["MONITOR"][0]["action"] == "ACOMPANHAR"


def test_write_decision_queue_is_atomic(tmp_path: Path) -> None:
    queue = build_decision_queue(priority=None)
    output = write_decision_queue(queue, tmp_path / "nested" / "decision_queue.json")

    assert output.exists()
    assert not output.with_suffix(".json.tmp").exists()
    assert json.loads(output.read_text(encoding="utf-8"))["items"] == []
