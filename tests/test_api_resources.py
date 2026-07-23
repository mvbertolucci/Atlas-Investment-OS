"""
Tests for the read-only dashboard API resource layer.

The API serves the already-produced dashboard contract over HTTP GET. These
tests exercise the pure routing/dispatch (no socket, no network), including the
read-only guarantees: non-GET is rejected and a missing artifact yields 503.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from api.resources import dispatch, load_dashboard, route, write_journal_event


def _contract() -> dict:
    return {
        "contract_version": "1.0",
        "generated_at": "2026-07-13T00:00:00",
        "market": None,
        "companies": [
            {"symbol": "AAA", "decision": "BUY", "investment_score": 80.0},
            {"symbol": "BBB", "decision": "AVOID", "investment_score": 40.0},
        ],
        "portfolio": {"portfolio_name": "Main"},
        "outcomes": {"hit_rate": {"hit_rate": 100.0}},
        "priority": {
            "sell": {"items": [{"symbol": "BBB", "action": "SELL"}]},
            "buy": {"items": [{"symbol": "CCC", "candidate_rank": 1}]},
        },
        "decision_queue": {"summary": {"execute": 1}},
    }


def _write(tmp_path: Path) -> Path:
    path = tmp_path / "dashboard.json"
    path.write_text(json.dumps(_contract()), encoding="utf-8")
    return path


def test_index_lists_resources() -> None:
    status, payload = route("/", _contract())
    assert status == 200
    assert payload["service"] == "atlas-dashboard-api"
    assert payload["contract_version"] == "1.0"
    assert "/companies/{symbol}" in payload["resources"]


def test_dashboard_returns_full_contract() -> None:
    status, payload = route("/dashboard", _contract())
    assert status == 200
    assert payload == _contract()


def test_companies_collection_has_count() -> None:
    status, payload = route("/companies", _contract())
    assert status == 200
    assert payload["count"] == 2
    assert [c["symbol"] for c in payload["companies"]] == ["AAA", "BBB"]


def test_single_company_is_case_insensitive() -> None:
    status, payload = route("/companies/aaa", _contract())
    assert status == 200
    assert payload["symbol"] == "AAA"


def test_unknown_company_is_404() -> None:
    status, payload = route("/companies/ZZZ", _contract())
    assert status == 404
    assert payload["symbol"] == "ZZZ"


def test_sub_resources_are_wrapped() -> None:
    assert route("/market", _contract()) == (200, {"market": None})
    assert route("/portfolio", _contract())[1]["portfolio"] == {
        "portfolio_name": "Main"
    }
    assert route("/outcomes", _contract())[1]["outcomes"] == {
        "hit_rate": {"hit_rate": 100.0}
    }


def test_priority_full_and_sub_resources() -> None:
    status, payload = route("/priority", _contract())
    assert status == 200
    assert payload["priority"]["sell"]["items"][0]["symbol"] == "BBB"

    status, payload = route("/priority/sell", _contract())
    assert status == 200
    assert payload["sell"]["items"][0]["action"] == "SELL"

    status, payload = route("/priority/buy", _contract())
    assert status == 200
    assert payload["buy"]["items"][0]["symbol"] == "CCC"


def test_priority_sub_resources_when_priority_absent() -> None:
    data = {**_contract(), "priority": None}
    status, payload = route("/priority/sell", data)
    assert status == 200
    assert payload["sell"] is None


def test_decision_queue_resource() -> None:
    status, payload = route("/decision-queue", _contract())
    assert status == 200
    assert payload["decision_queue"]["summary"]["execute"] == 1


def test_trailing_slash_and_query_are_normalized() -> None:
    assert route("/companies/", _contract())[0] == 200
    assert route("/dashboard?x=1", _contract())[0] == 200


def test_unknown_resource_is_404() -> None:
    status, payload = route("/nope", _contract())
    assert status == 404
    assert payload["path"] == "/nope"


def test_dispatch_rejects_put_and_delete(tmp_path: Path) -> None:
    path = _write(tmp_path)
    for method in ("PUT", "DELETE"):
        status, _ = dispatch(method, "/dashboard", dashboard_path=path)
        assert status == 405


def test_dispatch_post_only_on_journal(tmp_path: Path) -> None:
    path = _write(tmp_path)
    status, payload = dispatch("POST", "/dashboard", dashboard_path=path, body={})
    assert status == 404
    assert payload["path"] == "/dashboard"


def test_dispatch_reads_from_file(tmp_path: Path) -> None:
    path = _write(tmp_path)
    status, payload = dispatch("GET", "/companies/BBB", dashboard_path=path)
    assert status == 200
    assert payload["decision"] == "AVOID"


def test_missing_artifact_is_503(tmp_path: Path) -> None:
    status, payload = dispatch(
        "GET", "/dashboard", dashboard_path=tmp_path / "nope.json"
    )
    assert status == 503
    assert "run_all" in payload["error"]


def test_load_dashboard_missing_raises(tmp_path: Path) -> None:
    from api.resources import ResourceError

    with pytest.raises(ResourceError) as exc:
        load_dashboard(tmp_path / "absent.json")
    assert exc.value.status == 503


def _queue_file(tmp_path: Path) -> Path:
    path = tmp_path / "decision_queue.json"
    path.write_text(
        json.dumps(
            {
                "contract_version": "1.1",
                "generated_at": "2026-07-22T10:00:00",
                "items": [
                    {
                        "decision_id": "d1",
                        "symbol": "FMC",
                        "action": "SELL",
                        "engine": "portfolio.sell_rules",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_write_journal_event_records_decision(tmp_path: Path) -> None:
    journal = tmp_path / "journal.json"
    status, payload = write_journal_event(
        {"decision_id": "d1", "status": "ACCEPTED", "reason": "Evidência confirmada"},
        queue_path=_queue_file(tmp_path),
        journal_path=journal,
    )
    assert status == 201
    assert payload["symbol"] == "FMC"
    assert payload["status"] == "ACCEPTED"
    stored = json.loads(journal.read_text(encoding="utf-8"))
    assert len(stored["events"]) == 1


def test_write_journal_event_validates_body(tmp_path: Path) -> None:
    queue = _queue_file(tmp_path)
    journal = tmp_path / "journal.json"
    assert write_journal_event("nope", queue_path=queue, journal_path=journal)[0] == 400
    assert write_journal_event(
        {"decision_id": "", "status": "ACCEPTED", "reason": "x"},
        queue_path=queue, journal_path=journal,
    )[0] == 400
    assert write_journal_event(
        {"decision_id": "d1", "status": "MAYBE", "reason": "x"},
        queue_path=queue, journal_path=journal,
    )[0] == 400
    assert write_journal_event(
        {"decision_id": "d1", "status": "ACCEPTED", "reason": "  "},
        queue_path=queue, journal_path=journal,
    )[0] == 400


def test_write_journal_event_unknown_decision_is_404(tmp_path: Path) -> None:
    status, _ = write_journal_event(
        {"decision_id": "zz", "status": "ACCEPTED", "reason": "x"},
        queue_path=_queue_file(tmp_path),
        journal_path=tmp_path / "journal.json",
    )
    assert status == 404


def test_write_journal_event_missing_queue_is_503(tmp_path: Path) -> None:
    status, _ = write_journal_event(
        {"decision_id": "d1", "status": "ACCEPTED", "reason": "x"},
        queue_path=tmp_path / "absent.json",
        journal_path=tmp_path / "journal.json",
    )
    assert status == 503
