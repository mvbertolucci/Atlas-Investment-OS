from __future__ import annotations

import json
from pathlib import Path

import pytest

from decision.execution import execution_summary, load_execution_ledger, main, record_execution


def _decision(action: str = "SELL") -> dict:
    return {"decision_id": "d1", "symbol": "FMC", "action": action}


def _journal(status: str = "ACCEPTED") -> dict:
    return {"contract_version": "1.0", "events": [{"decision_id": "d1", "status": status}]}


def test_records_real_fill_and_summary(tmp_path: Path) -> None:
    path = tmp_path / "ledger.json"
    event = record_execution(
        _decision(), journal=_journal(), quantity="10", price="25.50", fees="1",
        currency="usd", executed_at="2026-07-22T14:00:00", ledger_path=path,
        recorded_at="2026-07-22T14:01:00",
    )
    assert event.gross_value == 255.0
    assert event.net_cash_delta == 254.0
    assert execution_summary(load_execution_ledger(path)) == {
        "fills": 1, "decisions_executed": 1, "gross_sell_value": 255.0,
        "fees": 1.0, "net_cash_delta": 254.0,
    }


def test_allows_separate_partial_fills_but_rejects_exact_duplicate(tmp_path: Path) -> None:
    path = tmp_path / "ledger.json"
    kwargs = dict(journal=_journal(), quantity=5, price=20, fees=0,
                  executed_at="2026-07-22T14:00:00", ledger_path=path)
    record_execution(_decision(), **kwargs)
    with pytest.raises(ValueError, match="já registrada"):
        record_execution(_decision(), **kwargs)
    record_execution(_decision(), **{**kwargs, "executed_at": "2026-07-22T14:05:00"})
    assert len(load_execution_ledger(path)["events"]) == 2


@pytest.mark.parametrize("status", ["REJECTED", "DEFERRED"])
def test_requires_latest_accepted_status(tmp_path: Path, status: str) -> None:
    journal = _journal()
    journal["events"].append({"decision_id": "d1", "status": status})
    with pytest.raises(ValueError, match="ACCEPTED"):
        record_execution(_decision(), journal=journal, quantity=1, price=1,
                         executed_at="now", ledger_path=tmp_path / "x.json")


def test_rejects_unsupported_action_and_invalid_numbers(tmp_path: Path) -> None:
    base = dict(journal=_journal(), quantity=1, price=1, executed_at="now",
                ledger_path=tmp_path / "x.json")
    with pytest.raises(ValueError, match="action"):
        record_execution(_decision("REVIEW_FOR_PURCHASE"), **base)
    for field, value in (("quantity", 0), ("price", -1), ("fees", -1)):
        args = {**base, field: value}
        with pytest.raises(ValueError, match=field):
            record_execution(_decision(), **args)
    with pytest.raises(ValueError, match="valor bruto"):
        record_execution(_decision(), **{**base, "fees": 2})


def test_cli_records_fill(tmp_path: Path, capsys) -> None:
    queue = tmp_path / "queue.json"
    journal = tmp_path / "journal.json"
    ledger = tmp_path / "ledger.json"
    queue.write_text(json.dumps({"items": [_decision()]}), encoding="utf-8")
    journal.write_text(json.dumps(_journal()), encoding="utf-8")
    main(["d1", "2", "30", "2026-07-22T15:00:00", "--fees", "0.5",
          "--queue", str(queue), "--journal", str(journal), "--ledger", str(ledger)])
    assert "EXECUTED: FMC SELL" in capsys.readouterr().out
    assert load_execution_ledger(ledger)["events"][0]["net_cash_delta"] == 59.5


def test_missing_ledger_is_valid_empty(tmp_path: Path) -> None:
    assert load_execution_ledger(tmp_path / "missing.json")["events"] == []
