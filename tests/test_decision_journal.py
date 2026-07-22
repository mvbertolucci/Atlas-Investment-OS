from __future__ import annotations

import json
from pathlib import Path

import pytest

from decision.journal import journal_summary, load_journal, main, record_decision


def _decision() -> dict:
    return {
        "decision_id": "abc123",
        "symbol": "FMC",
        "action": "SELL",
        "engine": "portfolio.sell_rules",
    }


def test_records_append_only_auditable_events(tmp_path: Path) -> None:
    path = tmp_path / "journal.json"
    first = record_decision(
        _decision(),
        queue_generated_at="2026-07-22T10:00:00",
        status="accepted",
        reason="Evidência confirmada",
        journal_path=path,
        recorded_at="2026-07-22T11:00:00",
    )
    record_decision(
        _decision(),
        queue_generated_at="2026-07-22T10:00:00",
        status="deferred",
        reason="Aguardar abertura",
        journal_path=path,
        recorded_at="2026-07-22T12:00:00",
    )
    payload = load_journal(path)
    assert len(payload["events"]) == 2
    assert payload["events"][0]["event_id"] == first.event_id
    assert journal_summary(payload) == {
        "total_events": 2,
        "latest_decisions": 1,
        "accepted": 0,
        "rejected": 0,
        "deferred": 1,
    }


def test_rejects_invalid_or_duplicate_event(tmp_path: Path) -> None:
    path = tmp_path / "journal.json"
    kwargs = dict(
        queue_generated_at="x",
        status="ACCEPTED",
        reason="ok",
        journal_path=path,
        recorded_at="2026-07-22T12:00:00",
    )
    record_decision(_decision(), **kwargs)
    with pytest.raises(ValueError, match="já registrado"):
        record_decision(_decision(), **kwargs)
    with pytest.raises(ValueError, match="status"):
        record_decision(_decision(), queue_generated_at="x", status="MAYBE", reason="x")
    with pytest.raises(ValueError, match="reason"):
        record_decision(_decision(), queue_generated_at="x", status="ACCEPTED", reason=" ")


def test_cli_records_decision(tmp_path: Path, capsys) -> None:
    queue_path = tmp_path / "queue.json"
    journal_path = tmp_path / "journal.json"
    queue_path.write_text(
        json.dumps({"generated_at": "now", "items": [_decision()]}), encoding="utf-8"
    )
    main(["abc123", "ACCEPTED", "confirmado", "--queue", str(queue_path), "--journal", str(journal_path)])
    assert "ACCEPTED: FMC SELL" in capsys.readouterr().out
    assert load_journal(journal_path)["events"][0]["reason"] == "confirmado"


def test_missing_journal_is_valid_empty(tmp_path: Path) -> None:
    assert load_journal(tmp_path / "missing.json")["events"] == []
