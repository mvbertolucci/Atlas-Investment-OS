from __future__ import annotations

from pathlib import Path

import pandas as pd

from analytics.history import (
    build_period_trends,
    build_score_changes,
    classify_trend,
    load_history,
)
from reports.history_report import (
    build_historical_trends,
    build_history_summary,
)
from storage.history_db import HistoryDatabase


def _sample_snapshot(
    opportunity_a: float,
    opportunity_b: float,
    business_a: float = 70.0,
    business_b: float = 60.0,
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": ["AAA", "BBB"],
            "Business Score": [business_a, business_b],
            "Valuation Score": [65.0, 55.0],
            "Financial Score": [75.0, 50.0],
            "Timing Score": [60.0, 45.0],
            "Investment Score": [68.0, 52.0],
            "Opportunity Score": [opportunity_a, opportunity_b],
            "Confidence Score": [90.0, 80.0],
            "Recommendation": ["★★★ Acumular", "★ Evitar"],
        }
    )


def test_history_database_saves_and_loads_snapshots(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "atlas_history.db"

    first_snapshot = _sample_snapshot(
        opportunity_a=70.0,
        opportunity_b=50.0,
    )

    second_snapshot = _sample_snapshot(
        opportunity_a=78.0,
        opportunity_b=45.0,
        business_a=76.0,
        business_b=57.0,
    )

    with HistoryDatabase(database_path) as database:
        database.save_snapshot(
            first_snapshot,
            "2026-07-01T09:00:00",
        )

        database.save_snapshot(
            second_snapshot,
            "2026-07-10T09:00:00",
        )

        history = database.load_history()

    assert len(history) == 4
    assert set(history["symbol"]) == {"AAA", "BBB"}
    assert "opportunity_score" in history.columns


def test_build_score_changes_compares_latest_snapshots(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "atlas_history.db"

    with HistoryDatabase(database_path) as database:
        database.save_snapshot(
            _sample_snapshot(70.0, 50.0),
            "2026-07-01T09:00:00",
        )

        database.save_snapshot(
            _sample_snapshot(
                78.0,
                45.0,
                business_a=76.0,
                business_b=57.0,
            ),
            "2026-07-10T09:00:00",
        )

    history = load_history(database_path)
    changes = build_score_changes(history)

    aaa = changes.loc[
        changes["symbol"] == "AAA"
    ].iloc[0]

    bbb = changes.loc[
        changes["symbol"] == "BBB"
    ].iloc[0]

    assert aaa["Opportunity Score Previous"] == 70.0
    assert aaa["Opportunity Score Current"] == 78.0
    assert aaa["Opportunity Score Delta"] == 8.0
    assert aaa["Opportunity Score Trend"] == "Melhora forte"

    assert bbb["Opportunity Score Delta"] == -5.0
    assert bbb["Opportunity Score Trend"] == "Piora forte"


def test_classify_trend() -> None:
    assert classify_trend(None) == "Sem histórico"
    assert classify_trend(6.0) == "Melhora forte"
    assert classify_trend(2.0) == "Melhorando"
    assert classify_trend(0.5) == "Estável"
    assert classify_trend(-2.0) == "Piorando"
    assert classify_trend(-6.0) == "Piora forte"


def test_period_trends_calculate_delta(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "atlas_history.db"

    with HistoryDatabase(database_path) as database:
        database.save_snapshot(
            _sample_snapshot(70.0, 50.0),
            "2026-06-01T09:00:00",
        )

        database.save_snapshot(
            _sample_snapshot(82.0, 43.0),
            "2026-07-10T09:00:00",
        )

    history = load_history(database_path)
    trends = build_period_trends(
        history,
        days=30,
    )

    aaa = trends.loc[
        trends["symbol"] == "AAA"
    ].iloc[0]

    bbb = trends.loc[
        trends["symbol"] == "BBB"
    ].iloc[0]

    assert aaa["Opportunity Score Δ30d"] == 12.0
    assert aaa["Opportunity Score Trend"] == "Melhora forte"

    assert bbb["Opportunity Score Δ30d"] == -7.0
    assert bbb["Opportunity Score Trend"] == "Piora forte"


def test_history_reports_are_generated(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "atlas_history.db"

    with HistoryDatabase(database_path) as database:
        database.save_snapshot(
            _sample_snapshot(70.0, 50.0),
            "2026-06-01T09:00:00",
        )

        database.save_snapshot(
            _sample_snapshot(82.0, 43.0),
            "2026-07-10T09:00:00",
        )

    historical_trends = build_historical_trends(
        database_path,
        period_days=30,
    )

    history_summary = build_history_summary(
        database_path,
    )

    assert not historical_trends.empty
    assert not history_summary.empty

    assert "Opportunity Score Current" in historical_trends.columns
    assert "Opportunity Score Delta" in historical_trends.columns

    assert "Snapshot Count" in history_summary.columns
    assert "Current Opportunity" in history_summary.columns

    aaa_summary = history_summary.loc[
        history_summary["symbol"] == "AAA"
    ].iloc[0]

    assert aaa_summary["Snapshot Count"] == 2
    assert aaa_summary["Current Opportunity"] == 82.0
    assert aaa_summary["Minimum Opportunity"] == 70.0
    assert aaa_summary["Maximum Opportunity"] == 82.0