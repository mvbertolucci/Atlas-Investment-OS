from __future__ import annotations

from pathlib import Path

from portfolio.custody_history import (
    capture_custody_snapshot,
    custody_history_summary,
    load_custody_history,
)


def _portfolio(at: str, quantity: float) -> dict:
    return {"generated_at": at, "portfolio_name": "Main",
            "holdings": [{"symbol": "aaa", "quantity": quantity}]}


def test_captures_append_only_ordered_and_idempotent_snapshots(tmp_path: Path) -> None:
    path = tmp_path / "history.json"
    second = capture_custody_snapshot(_portfolio("2026-07-23T10:00:00", 5), history_path=path)
    capture_custody_snapshot(_portfolio("2026-07-22T10:00:00", 10), history_path=path)
    duplicate = capture_custody_snapshot(_portfolio("2026-07-23T10:00:00", 5), history_path=path)
    payload = load_custody_history(path)
    assert second["snapshot_id"] == duplicate["snapshot_id"]
    assert [item["snapshot_at"] for item in payload["snapshots"]] == [
        "2026-07-22T10:00:00", "2026-07-23T10:00:00"
    ]
    assert payload["snapshots"][0]["holdings"] == [{"symbol": "AAA", "quantity": 10.0}]
    assert custody_history_summary(payload)["reconciliation_ready"] is True


def test_missing_history_is_empty(tmp_path: Path) -> None:
    payload = load_custody_history(tmp_path / "missing.json")
    assert custody_history_summary(payload) == {
        "snapshots": 0, "latest_snapshot_at": None, "reconciliation_ready": False
    }
