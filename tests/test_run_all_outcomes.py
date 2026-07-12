from __future__ import annotations

from pathlib import Path

import pandas as pd

import run_all
from outcomes.models import OutcomeResult, OutcomeSnapshot
from storage.history_db import HistoryDatabase


def _analysis_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": ["AAA"],
            "name": ["Alpha"],
            "price": [25.0],
            "Decision": ["BUY"],
            "Decision Rating": ["Comprar"],
            "Investment Score": [80],
            "Opportunity Score": [85],
            "Conviction Score": [88],
            "Decision Confidence": [90],
            "Risk Penalty": [5],
        }
    )


def test_save_outcome_decisions_integrates_with_history_database(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "atlas_history.db"
    monkeypatch.setattr(
        run_all,
        "HISTORY_DATABASE",
        database_path,
    )

    result = run_all.save_outcome_decisions(
        _analysis_frame(),
        "2026-07-12T10:00:00",
        {
            "outcome_analytics_enabled": True,
            "outcome_horizons_days": [30, 90],
        },
    )

    with HistoryDatabase(database_path) as database:
        saved = database.load_outcome_snapshots("AAA")

    assert result is not None
    assert result.saved_count == 1
    assert result.horizons_days == (30, 90)
    assert len(saved) == 1


def test_save_outcome_decisions_can_be_disabled(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "disabled.db"
    monkeypatch.setattr(
        run_all,
        "HISTORY_DATABASE",
        database_path,
    )

    result = run_all.save_outcome_decisions(
        _analysis_frame(),
        "2026-07-12T10:00:00",
        {"outcome_analytics_enabled": False},
    )

    assert result is None
    assert not database_path.exists()


def test_evaluate_outcome_decisions_integrates_with_pipeline(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "evaluation.db"
    monkeypatch.setattr(
        run_all,
        "HISTORY_DATABASE",
        database_path,
    )
    settings = {
        "outcome_analytics_enabled": True,
        "outcome_horizons_days": [30],
    }

    run_all.save_outcome_decisions(
        _analysis_frame(),
        "2026-01-01T10:00:00",
        settings,
    )
    current = _analysis_frame()
    current["price"] = [30.0]
    result = run_all.evaluate_outcome_decisions(
        current,
        "2026-02-02T10:00:00",
        settings,
    )

    assert result is not None
    assert result.evaluated_count == 1
    assert result.results[0].return_pct == 20.0


def test_evaluate_outcome_decisions_can_be_disabled() -> None:
    result = run_all.evaluate_outcome_decisions(
        _analysis_frame(),
        "2026-02-02T10:00:00",
        {"outcome_analytics_enabled": False},
    )

    assert result is None


def test_generate_outcome_analytics_reads_persisted_results(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "analytics.db"
    monkeypatch.setattr(
        run_all,
        "HISTORY_DATABASE",
        database_path,
    )
    output_path = tmp_path / "outcome_report.json"
    monkeypatch.setattr(
        run_all,
        "OUTCOME_REPORT_FILE",
        output_path,
    )
    snapshot = OutcomeSnapshot(
        decision_date="2026-01-01T10:00:00",
        symbol="AAA",
        decision_price=100,
        decision="BUY",
        opportunity_score=85,
        conviction_score=90,
    )
    result = OutcomeResult(
        decision_date=snapshot.decision_date,
        symbol="AAA",
        horizon_days=30,
        evaluation_date="2026-01-31T10:00:00",
        decision_price=100,
        outcome_price=110,
    )
    with HistoryDatabase(database_path) as database:
        database.save_outcome_snapshot(snapshot)
        database.save_outcome_result(result)

    report = run_all.generate_outcome_analytics(
        {
            "outcome_analytics_enabled": True,
            "outcome_hit_threshold_pct": 0,
            "outcome_calibration_bucket_size": 20,
        }
    )

    assert report is not None
    assert report.hit_rate.hit_rate == 100.0
    assert output_path.exists()


def test_generate_outcome_analytics_can_be_disabled() -> None:
    assert run_all.generate_outcome_analytics(
        {"outcome_analytics_enabled": False}
    ) is None
