from __future__ import annotations

import json
from pathlib import Path

from decision.delta import (
    build_decision_delta,
    find_previous_snapshot,
    write_decision_delta,
)


def _item(decision_id, symbol, action, engine, group, **extra):
    return {
        "decision_id": decision_id,
        "symbol": symbol,
        "action": action,
        "engine": engine,
        "group": group,
        "company_name": f"{symbol} Inc.",
        "reason": "motivo",
        **extra,
    }


def _queue(generated_at, items):
    return {"contract_version": "1.1", "generated_at": generated_at, "items": items}


def test_first_run_has_no_baseline() -> None:
    current = _queue("2026-07-22T10:00:00", [_item("a", "FMC", "SELL", "e", "EXECUTE")])
    delta = build_decision_delta(current, None).to_dict()

    assert delta["baseline_generated_at"] is None
    assert delta["summary"] == {
        "entered": 0,
        "exited": 0,
        "changed": 0,
        "action_transitions": 0,
        "unchanged": 0,
    }


def test_detects_entered_and_exited() -> None:
    previous = _queue(
        "2026-07-21T10:00:00",
        [_item("a", "FMC", "SELL", "e", "EXECUTE")],
    )
    current = _queue(
        "2026-07-22T10:00:00",
        [_item("b", "KGC", "REVIEW", "w", "INVESTIGATE")],
    )
    delta = build_decision_delta(current, previous).to_dict()

    assert delta["baseline_generated_at"] == "2026-07-21T10:00:00"
    assert [i["symbol"] for i in delta["entered"]] == ["KGC"]
    assert [i["symbol"] for i in delta["exited"]] == ["FMC"]
    assert delta["summary"]["action_transitions"] == 0


def test_action_escalation_is_a_transition_not_enter_plus_exit() -> None:
    previous = _queue(
        "2026-07-21T10:00:00",
        [_item("old", "FMC", "REVISAR", "portfolio.sell_rules", "INVESTIGATE")],
    )
    current = _queue(
        "2026-07-22T10:00:00",
        [_item("new", "FMC", "SELL", "portfolio.sell_rules", "EXECUTE")],
    )
    delta = build_decision_delta(current, previous).to_dict()

    assert delta["summary"] == {
        "entered": 0,
        "exited": 0,
        "changed": 0,
        "action_transitions": 1,
        "unchanged": 0,
    }
    transition = delta["action_transitions"][0]
    assert transition["symbol"] == "FMC"
    assert transition["from_action"] == "REVISAR"
    assert transition["action"] == "SELL"
    assert transition["from_group"] == "INVESTIGATE"
    assert transition["group"] == "EXECUTE"


def test_score_change_respects_threshold() -> None:
    previous = _queue(
        "2026-07-21T10:00:00",
        [_item("a", "FMC", "SELL", "e", "EXECUTE", opportunity_score=50.0, risk_penalty=10.0)],
    )
    current = _queue(
        "2026-07-22T10:00:00",
        [_item("a", "FMC", "SELL", "e", "EXECUTE", opportunity_score=42.0, risk_penalty=12.0)],
    )
    delta = build_decision_delta(current, previous, score_threshold=5.0).to_dict()

    assert delta["summary"]["changed"] == 1
    assert delta["summary"]["unchanged"] == 0
    changes = {c["field"]: c for c in delta["changed"][0]["changes"]}
    assert "opportunity_score" in changes
    assert changes["opportunity_score"]["delta"] == -8.0
    # risk_penalty moveu só 2.0 (< limiar) -> não reportado
    assert "risk_penalty" not in changes


def test_appearing_evidence_is_always_material() -> None:
    previous = _queue(
        "2026-07-21T10:00:00",
        [_item("a", "FMC", "SELL", "e", "EXECUTE", decision_confidence=None)],
    )
    current = _queue(
        "2026-07-22T10:00:00",
        [_item("a", "FMC", "SELL", "e", "EXECUTE", decision_confidence=61.0)],
    )
    delta = build_decision_delta(current, previous, score_threshold=99.0).to_dict()

    assert delta["summary"]["changed"] == 1
    change = delta["changed"][0]["changes"][0]
    assert change["field"] == "decision_confidence"
    assert change["from"] is None
    assert change["to"] == 61.0


def test_group_move_is_reported() -> None:
    previous = _queue(
        "2026-07-21T10:00:00",
        [_item("a", "FMC", "SELL", "e", "MONITOR")],
    )
    current = _queue(
        "2026-07-22T10:00:00",
        [_item("a", "FMC", "SELL", "e", "EXECUTE")],
    )
    delta = build_decision_delta(current, previous).to_dict()

    change = delta["changed"][0]["changes"][0]
    assert change == {"field": "group", "from": "MONITOR", "to": "EXECUTE"}


def test_unchanged_items_are_counted_not_listed() -> None:
    item = _item("a", "FMC", "SELL", "e", "EXECUTE", opportunity_score=50.0)
    previous = _queue("2026-07-21T10:00:00", [dict(item)])
    current = _queue("2026-07-22T10:00:00", [dict(item)])
    delta = build_decision_delta(current, previous).to_dict()

    assert delta["summary"]["unchanged"] == 1
    assert delta["changed"] == []


def test_find_previous_snapshot_picks_latest_before_current(tmp_path: Path) -> None:
    directory = tmp_path / "decision_queue"
    directory.mkdir()
    for iso in ("2026-07-20T10:00:00", "2026-07-21T10:00:00", "2026-07-22T10:00:00"):
        stamp = iso.replace(":", "-")
        (directory / f"decision_queue_{stamp}.json").write_text(
            json.dumps(_queue(iso, [])), encoding="utf-8"
        )

    previous = find_previous_snapshot(
        directory, before_generated_at="2026-07-22T10:00:00"
    )
    assert previous is not None
    assert previous["generated_at"].startswith("2026-07-21")


def test_find_previous_snapshot_returns_none_when_no_earlier(tmp_path: Path) -> None:
    directory = tmp_path / "decision_queue"
    directory.mkdir()
    (directory / "decision_queue_2026-07-22T10-00-00.json").write_text(
        json.dumps(_queue("2026-07-22T10:00:00", [])), encoding="utf-8"
    )
    assert (
        find_previous_snapshot(directory, before_generated_at="2026-07-22T10:00:00")
        is None
    )
    assert find_previous_snapshot(tmp_path / "missing", before_generated_at="x") is None


def test_write_decision_delta_is_atomic(tmp_path: Path) -> None:
    current = _queue("2026-07-22T10:00:00", [_item("a", "FMC", "SELL", "e", "EXECUTE")])
    delta = build_decision_delta(current, None)
    output = write_decision_delta(delta, tmp_path / "nested" / "decision_delta.json")

    assert output.exists()
    assert not output.with_suffix(".json.tmp").exists()
    assert json.loads(output.read_text(encoding="utf-8"))["contract_version"] == "1.0"
