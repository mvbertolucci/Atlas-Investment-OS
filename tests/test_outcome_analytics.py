from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from outcomes.analytics import (
    build_outcome_analytics_report,
    build_outcome_dataset,
    calculate_hit_rate,
    calculate_score_calibration,
)
from outcomes.models import OutcomeResult, OutcomeSnapshot
from storage.history_db import HistoryDatabase


def _dataset() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "decision": ["BUY", "AVOID", "BUY", "HOLD"],
            "return_pct": [10.0, -5.0, -2.0, 3.0],
            "horizon_days": [30, 30, 90, 90],
            "opportunity_score": [85.0, 55.0, 75.0, 65.0],
            "conviction_score": [90.0, 45.0, 70.0, 60.0],
        }
    )


def test_hit_rate_uses_directional_decision_contract() -> None:
    report = calculate_hit_rate(_dataset())

    assert report.eligible_count == 3
    assert report.hit_count == 2
    assert report.miss_count == 1
    assert report.excluded_count == 1
    assert report.hit_rate == 66.67
    assert report.by_horizon[0]["horizon_days"] == 30
    assert report.by_horizon[0]["hit_rate"] == 100.0
    assert report.to_dict()["hit_count"] == 2


def test_hit_rate_applies_strict_configurable_threshold() -> None:
    report = calculate_hit_rate(
        _dataset(),
        threshold_pct=5,
    )

    assert report.hit_count == 1
    assert report.hit_rate == 33.33


def test_hit_rate_handles_empty_and_invalid_inputs() -> None:
    assert calculate_hit_rate(pd.DataFrame()).hit_rate is None

    with pytest.raises(ValueError):
        calculate_hit_rate(_dataset(), threshold_pct=-1)
    with pytest.raises(ValueError):
        calculate_hit_rate(pd.DataFrame({"decision": ["BUY"]}))


def test_score_calibration_groups_by_horizon_and_bucket() -> None:
    rows = calculate_score_calibration(
        _dataset(),
        "opportunity_score",
        bucket_size=20,
    )

    lookup = {
        (
            row["horizon_days"],
            row["bucket_min"],
        ): row
        for row in rows
    }
    assert lookup[(30, 80)]["average_return_pct"] == 10.0
    assert lookup[(30, 40)]["positive_return_rate"] == 0.0
    assert lookup[(90, 60)]["count"] == 2
    assert lookup[(90, 60)]["positive_return_rate"] == 50.0


def test_score_calibration_validates_contract() -> None:
    assert calculate_score_calibration(
        pd.DataFrame(),
        "conviction_score",
    ) == ()

    with pytest.raises(ValueError):
        calculate_score_calibration(_dataset(), "investment_score")
    with pytest.raises(ValueError):
        calculate_score_calibration(
            _dataset(),
            "opportunity_score",
            bucket_size=0,
        )
    with pytest.raises(ValueError):
        calculate_score_calibration(
            pd.DataFrame({"return_pct": [1]}),
            "opportunity_score",
        )


def test_outcome_analytics_report_joins_persisted_data(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "history.db"
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
        dataset = build_outcome_dataset(database)
        report = build_outcome_analytics_report(database)

    assert len(dataset) == 1
    assert dataset.loc[0, "decision"] == "BUY"
    assert report.hit_rate.hit_rate == 100.0
    assert report.opportunity_calibration[0]["count"] == 1
    assert report.to_dict()["hit_rate"]["eligible_count"] == 1


def test_outcome_dataset_requires_history_database() -> None:
    with pytest.raises(TypeError):
        build_outcome_dataset(object())
