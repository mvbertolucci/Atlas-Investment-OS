from __future__ import annotations

import json
from pathlib import Path

from decision.reconciliation import main, reconcile_executions


def _ledger(*events: tuple[str, float]) -> dict:
    return {"events": [
        {"execution_id": f"e{i}", "decision_id": f"d{i}", "symbol": symbol,
         "action": "SELL", "quantity": quantity, "executed_at": "2026-07-22T10:00:00"}
        for i, (symbol, quantity) in enumerate(events)
    ]}


def _portfolio(**quantities: float) -> dict:
    return {"holdings": [{"symbol": symbol, "quantity": quantity} for symbol, quantity in quantities.items()]}


def test_classifies_confirmed_partial_not_reflected_variance_and_unverifiable() -> None:
    report = reconcile_executions(
        _ledger(("AAA", 5), ("BBB", 5), ("CCC", 5), ("DDD", 5), ("EEE", 5)),
        baseline_portfolio=_portfolio(AAA=10, BBB=10, CCC=10, DDD=10),
        current_portfolio=_portfolio(AAA=5, BBB=8, CCC=10, DDD=2, EEE=0),
        baseline_snapshot_at="before", current_snapshot_at="2026-07-23T10:00:00",
        generated_at="now",
    ).to_dict()
    assert [item["status"] for item in report["items"]] == [
        "CONFIRMED", "PARTIAL", "NOT_REFLECTED", "VARIANCE", "UNVERIFIABLE"
    ]
    assert report["summary"] == {
        "symbols": 5, "confirmed": 1, "partial": 1, "not_reflected": 1,
        "variance": 1, "unverifiable": 1,
    }


def test_groups_partial_fills_and_ignores_future_execution() -> None:
    ledger = _ledger(("AAA", 2), ("AAA", 3), ("AAA", 9))
    ledger["events"][-1]["executed_at"] = "2026-08-01T10:00:00"
    item = reconcile_executions(
        ledger, baseline_portfolio=_portfolio(AAA=10), current_portfolio=_portfolio(AAA=5),
        baseline_snapshot_at="before", current_snapshot_at="2026-07-23T10:00:00",
    ).items[0]
    assert item["expected_reduction"] == 5
    assert item["status"] == "CONFIRMED"
    assert len(item["execution_ids"]) == 2


def test_cli_writes_report(tmp_path: Path, capsys) -> None:
    baseline, current, ledger, output = [tmp_path / name for name in ("before.json", "after.json", "ledger.json", "out.json")]
    baseline.write_text(json.dumps(_portfolio(AAA=10)), encoding="utf-8")
    current.write_text(json.dumps(_portfolio(AAA=5)), encoding="utf-8")
    ledger.write_text(json.dumps({"contract_version": "1.0", **_ledger(("AAA", 5))}), encoding="utf-8")
    main([str(baseline), str(current), "--baseline-at", "before", "--current-at",
          "2026-07-23T10:00:00", "--ledger", str(ledger), "--output", str(output)])
    assert "1 confirmados" in capsys.readouterr().out
    assert json.loads(output.read_text(encoding="utf-8"))["items"][0]["status"] == "CONFIRMED"
