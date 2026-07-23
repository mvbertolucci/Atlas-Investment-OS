from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from outcomes.analytics import (
    build_outcome_analytics_report,
    build_outcome_dataset,
    calculate_deal_breaker_attribution,
    calculate_decision_attribution,
    calculate_factor_attribution,
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
            "business_score": [88.0, 40.0, 72.0, 62.0],
            "valuation_score": [82.0, 55.0, 68.0, 64.0],
            "financial_score": [90.0, 35.0, 75.0, 60.0],
            "timing_score": [80.0, 50.0, 65.0, 58.0],
            "deal_breakers": [
                (),
                ("Leverage",),
                (),
                ("Liquidity", "Leverage"),
            ],
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


def test_factor_and_rule_attribution() -> None:
    factor_rows = calculate_factor_attribution(_dataset())
    decision_rows = calculate_decision_attribution(_dataset())
    deal_breaker_rows = calculate_deal_breaker_attribution(
        _dataset()
    )

    assert {row["score"] for row in factor_rows} == {
        "business_score",
        "valuation_score",
        "financial_score",
        "timing_score",
    }
    buy_30 = next(
        row
        for row in decision_rows
        if row["value"] == "BUY"
        and row["horizon_days"] == 30
    )
    assert buy_30["average_return_pct"] == 10.0
    leverage_30 = next(
        row
        for row in deal_breaker_rows
        if row["value"] == "Leverage"
        and row["horizon_days"] == 30
    )
    assert leverage_30["average_return_pct"] == -5.0
    assert any(
        row["value"] == "NO_DEAL_BREAKER"
        for row in deal_breaker_rows
    )


def test_outcome_analytics_report_joins_persisted_data(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "history.db"
    snapshot = OutcomeSnapshot(
        decision_date="2026-01-01T10:00:00",
        symbol="AAA",
        company_name="Alpha",
        decision_price=100,
        decision="BUY",
        opportunity_score=85,
        conviction_score=90,
        business_score=88,
        valuation_score=82,
        financial_score=90,
        timing_score=80,
    )
    result = OutcomeResult(
        decision_date=snapshot.decision_date,
        symbol="AAA",
        company_name="Alpha",
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
    assert report.evaluated_outcomes == (
        {
            "decision_date": "2026-01-01T10:00:00",
            "symbol": "AAA",
            "company_name": "Alpha",
            "horizon_days": 30,
            "due_date": "2026-01-31T10:00:00",
            "evaluation_date": "2026-01-31T10:00:00",
            "return_pct": 10.0,
            "decision": "BUY",
        },
    )
    assert report.opportunity_calibration[0]["count"] == 1
    assert report.factor_attribution
    assert report.decision_attribution[0]["value"] == "BUY"
    assert report.deal_breaker_attribution[0]["value"] == (
        "NO_DEAL_BREAKER"
    )
    assert report.to_dict()["hit_rate"]["eligible_count"] == 1


def test_outcome_dataset_requires_history_database() -> None:
    with pytest.raises(TypeError):
        build_outcome_dataset(object())
