from __future__ import annotations

from pathlib import Path

import pandas as pd

from analytics.history import (
    build_period_trends,
    build_score_changes,
    classify_trend,
    earnings_between_runs,
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


def test_earnings_between_runs_is_a_transition() -> None:
    previous_run_at = pd.Timestamp("2026-07-01")
    current_run_at = pd.Timestamp("2026-07-14")

    inside_window = earnings_between_runs(
        "2026-07-10", previous_run_at, current_run_at
    )
    assert inside_window is True

    before_previous_run = earnings_between_runs(
        "2026-06-20", previous_run_at, current_run_at
    )
    assert before_previous_run is False

    after_current_run = earnings_between_runs(
        "2026-07-20", previous_run_at, current_run_at
    )
    assert after_current_run is False


def test_earnings_between_runs_none_without_data() -> None:
    current_run_at = pd.Timestamp("2026-07-14")
    assert earnings_between_runs(None, pd.Timestamp("2026-07-01"), current_run_at) is None
    assert earnings_between_runs("2026-07-10", None, current_run_at) is None
    assert earnings_between_runs(float("nan"), pd.Timestamp("2026-07-01"), current_run_at) is None


def test_watchlist_triggers_table_saves_and_upserts(tmp_path: Path) -> None:
    database_path = tmp_path / "atlas_history.db"

    with HistoryDatabase(database_path) as database:
        assert database.load_watchlist_triggers() == {}

        database.save_watchlist_trigger("AAA", "score > 75", "2026-07-14")
        stored = database.load_watchlist_triggers()
        assert stored["AAA"]["condition_text"] == "score > 75"
        assert stored["AAA"]["last_triggered_at"] == "2026-07-14"

        # Mesmo símbolo, condição/dado atualizados -- upsert, não duplica.
        database.save_watchlist_trigger("AAA", "score > 80", "2026-08-01")
        stored = database.load_watchlist_triggers()
        assert len(stored) == 1
        assert stored["AAA"]["condition_text"] == "score > 80"
        assert stored["AAA"]["last_triggered_at"] == "2026-08-01"


def test_is_candidate_migrates_and_persists(tmp_path: Path) -> None:
    database_path = tmp_path / "atlas_history.db"

    # Snapshot legado, sem is_candidate no df -- a coluna deve existir na
    # tabela (migração) e ficar NULL para essas linhas.
    with HistoryDatabase(database_path) as database:
        database.save_snapshot(
            _sample_snapshot(70.0, 50.0),
            "2026-06-01T09:00:00",
        )
        legacy_history = database.load_history()
    assert "is_candidate" in legacy_history.columns
    assert legacy_history["is_candidate"].isna().all()

    # Run novo, com is_candidate no df -- grava 1/0 corretamente.
    df = _sample_snapshot(80.0, 40.0)
    df["is_candidate"] = [True, False]
    with HistoryDatabase(database_path) as database:
        database.save_snapshot(df, "2026-07-01T09:00:00")
        history = database.load_history()

    new_rows = history.loc[history["snapshot_date"] == "2026-07-01T09:00:00"]
    aaa = new_rows.loc[new_rows["symbol"] == "AAA"].iloc[0]
    bbb = new_rows.loc[new_rows["symbol"] == "BBB"].iloc[0]
    assert aaa["is_candidate"] == 1
    assert bbb["is_candidate"] == 0
