from __future__ import annotations

import json
from pathlib import Path

import pytest

from portfolio.scenario import build_sell_scenario, write_portfolio_scenario


def _portfolio() -> dict:
    return {
        "summary": {"total_value": 1000.0, "cash": 100.0, "currency": "USD"},
        "holdings": [
            {"symbol": "AAA", "market_value": 300.0, "sector": "Technology"},
            {"symbol": "BBB", "market_value": 600.0, "sector": "Healthcare"},
        ],
        "rebalance": {
            "actions": [
                {"symbol": "AAA", "action": "SELL", "trade_value": -300.0},
                {"symbol": "BBB", "action": "HOLD", "trade_value": 0.0},
            ]
        },
    }


def test_simulates_only_official_sell_trim_and_preserves_total_value() -> None:
    scenario = build_sell_scenario(
        _portfolio(), transaction_cost_rate=0.01, generated_at="2026-07-22T00:00:00"
    ).to_dict()

    assert scenario["summary"]["released_cash"] == 300.0
    assert scenario["summary"]["estimated_cost"] == 3.0
    assert scenario["summary"]["cash_after"] == 397.0
    assert scenario["summary"]["cash_weight_after"] == 0.397
    assert scenario["summary"]["turnover"] == 0.3
    assert scenario["weights_after"] == {"BBB": 0.6}
    assert scenario["executed_actions"] == [
        {"symbol": "AAA", "action": "SELL", "sale_value": 300.0}
    ]
    assert scenario["advisory_only"] is True


def test_rejects_invalid_inputs_and_writes_atomically(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        build_sell_scenario({"summary": {"total_value": 0}})
    with pytest.raises(ValueError):
        build_sell_scenario(_portfolio(), transaction_cost_rate=-0.1)

    scenario = build_sell_scenario(_portfolio())
    output = write_portfolio_scenario(scenario, tmp_path / "scenario.json")
    assert json.loads(output.read_text(encoding="utf-8"))["contract_version"] == "1.0"
    assert not output.with_suffix(".json.tmp").exists()
