from __future__ import annotations

from pathlib import Path
import sqlite3

import pandas as pd
import pytest

from outcomes.models import OutcomeResult, OutcomeSnapshot
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
        business_score=78,
        valuation_score=72,
        financial_score=80,
        timing_score=75,
        risk_penalty=5,
        deal_breakers=("Liquidity",) if symbol == "BBB" else (),
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
    assert aaa_rows.loc[0, "business_score"] == 78.0
    assert aaa_rows.loc[0, "deal_breakers"] == ()


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


def test_outcome_result_repository_is_immutable_per_horizon(
    tmp_path: Path,
) -> None:
    first = OutcomeResult(
        decision_date="2026-01-01T10:00:00",
        symbol="AAA",
        company_name="Company AAA",
        horizon_days=30,
        evaluation_date="2026-01-31T10:00:00",
        decision_price=100,
        outcome_price=110,
    )
    duplicate = OutcomeResult(
        decision_date="2026-01-01T10:00:00",
        symbol="AAA",
        company_name="Company AAA",
        horizon_days=30,
        evaluation_date="2026-02-02T10:00:00",
        decision_price=100,
        outcome_price=120,
    )

    with HistoryDatabase(tmp_path / "history.db") as database:
        database.save_outcome_result(first)
        database.save_outcome_result(duplicate)
        rows = database.load_outcome_results("aaa")

    assert len(rows) == 1
    assert rows.loc[0, "outcome_price"] == 110.0
    assert rows.loc[0, "return_pct"] == 10.0


def test_outcome_result_repository_validates_type(
    tmp_path: Path,
) -> None:
    with HistoryDatabase(tmp_path / "history.db") as database:
        with pytest.raises(TypeError):
            database.save_outcome_result(object())


def test_outcome_snapshot_schema_migrates_existing_database(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "legacy.db"
    connection = sqlite3.connect(database_path)
    connection.execute(
        """
        CREATE TABLE outcome_snapshots
        (
            decision_date TEXT NOT NULL,
            symbol TEXT NOT NULL,
            company_name TEXT,
            decision_price REAL NOT NULL,
            decision TEXT NOT NULL,
            decision_rating TEXT,
            investment_score REAL,
            opportunity_score REAL,
            conviction_score REAL,
            decision_confidence REAL,
            risk_penalty REAL,
            has_deal_breaker INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (decision_date, symbol)
        )
        """
    )
    connection.execute(
        """
        INSERT INTO outcome_snapshots
        (decision_date, symbol, decision_price, decision)
        VALUES ('2026-01-01T10:00:00', 'AAA', 100, 'BUY')
        """
    )
    connection.commit()
    connection.close()

    with HistoryDatabase(database_path) as database:
        columns = {
            row[1]
            for row in database.connection.execute(
                "PRAGMA table_info(outcome_snapshots)"
            ).fetchall()
        }
        rows = database.load_outcome_snapshots("AAA")

    assert {
        "business_score",
        "valuation_score",
        "financial_score",
        "timing_score",
        "deal_breakers_json",
    }.issubset(columns)
    assert len(rows) == 1
    assert rows.loc[0, "deal_breakers"] == ()
