from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from outcomes.models import OutcomeSnapshot
from storage.history_db import HistoryDatabase


def _snapshot(
    symbol: str,
    date: str,
    price: float,
    decision: str = "BUY",
) -> OutcomeSnapshot:
    return OutcomeSnapshot(
        decision_date=date,
        symbol=symbol,
        company_name=f"Company {symbol}",
        decision_price=price,
        decision=decision,
        decision_rating=decision,
        investment_score=75,
        opportunity_score=80,
        conviction_score=82,
        decision_confidence=85,
        risk_penalty=5,
    )


def test_outcome_repository_round_trip_and_filter(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "atlas_history.db"

    with HistoryDatabase(database_path) as database:
        database.save_outcome_snapshots(
            [
                _snapshot("AAA", "2026-07-01T09:00:00", 10),
                _snapshot("BBB", "2026-07-01T09:00:00", 20, "HOLD"),
            ]
        )

        all_rows = database.load_outcome_snapshots()
        aaa_rows = database.load_outcome_snapshots("aaa")

    assert list(all_rows["symbol"]) == ["AAA", "BBB"]
    assert len(aaa_rows) == 1
    assert aaa_rows.loc[0, "decision_price"] == 10.0
    assert bool(aaa_rows.loc[0, "has_deal_breaker"]) is False


def test_outcome_repository_upserts_same_decision(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "atlas_history.db"
    date = "2026-07-01T09:00:00"

    with HistoryDatabase(database_path) as database:
        database.save_outcome_snapshot(
            _snapshot("AAA", date, 10, "BUY")
        )
        database.save_outcome_snapshot(
            _snapshot("AAA", date, 12, "HOLD")
        )
        rows = database.load_outcome_snapshots("AAA")

    assert len(rows) == 1
    assert rows.loc[0, "decision_price"] == 12.0
    assert rows.loc[0, "decision"] == "HOLD"


def test_outcome_table_preserves_existing_history_contract(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "atlas_history.db"
    frame = pd.DataFrame(
        {
            "symbol": ["AAA"],
            "Investment Score": [70.0],
            "Opportunity Score": [75.0],
        }
    )

    with HistoryDatabase(database_path) as database:
        database.save_snapshot(
            frame,
            "2026-07-01T09:00:00",
        )
        database.save_outcome_snapshot(
            _snapshot("AAA", "2026-07-01T09:00:00", 10),
        )

        history = database.load_history("AAA")
        outcomes = database.load_outcome_snapshots("AAA")

    assert len(history) == 1
    assert len(outcomes) == 1
    assert history.loc[0, "opportunity_score"] == 75.0


def test_outcome_repository_validates_type(
    tmp_path: Path,
) -> None:
    with HistoryDatabase(tmp_path / "history.db") as database:
        with pytest.raises(TypeError):
            database.save_outcome_snapshot(object())
