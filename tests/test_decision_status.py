from __future__ import annotations

from decision.status import (
    STATUS_ANALYZING,
    STATUS_DECIDED,
    STATUS_DISCARDED,
    STATUS_EXECUTED,
    STATUS_NEW,
    derive_decision_statuses,
    status_for,
)


def _journal(*events):
    return {"contract_version": "1.0", "events": list(events)}


def _ledger(*events):
    return {"contract_version": "1.0", "events": list(events)}


def test_no_records_means_new_by_default() -> None:
    statuses = derive_decision_statuses(_journal(), _ledger())
    assert statuses == {}
    assert status_for(statuses, "anything") == STATUS_NEW


def test_latest_journal_status_wins() -> None:
    journal = _journal(
        {"decision_id": "d1", "status": "DEFERRED"},
        {"decision_id": "d1", "status": "ACCEPTED"},
        {"decision_id": "d2", "status": "REJECTED"},
        {"decision_id": "d3", "status": "DEFERRED"},
    )
    statuses = derive_decision_statuses(journal, _ledger())
    assert statuses["d1"] == STATUS_DECIDED
    assert statuses["d2"] == STATUS_DISCARDED
    assert statuses["d3"] == STATUS_ANALYZING


def test_fill_promotes_to_executed_over_accepted() -> None:
    journal = _journal({"decision_id": "d1", "status": "ACCEPTED"})
    ledger = _ledger({"decision_id": "d1", "execution_id": "e1"})
    statuses = derive_decision_statuses(journal, ledger)
    assert statuses["d1"] == STATUS_EXECUTED


def test_status_for_falls_back_to_new() -> None:
    journal = _journal({"decision_id": "d1", "status": "ACCEPTED"})
    statuses = derive_decision_statuses(journal, _ledger())
    assert status_for(statuses, "d1") == STATUS_DECIDED
    assert status_for(statuses, "d2") == STATUS_NEW
