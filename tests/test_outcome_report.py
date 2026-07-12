from __future__ import annotations

import json
from pathlib import Path

import pytest

from outcomes.analytics import (
    HitRateReport,
    OutcomeAnalyticsReport,
)
from outcomes.report import (
    outcome_attribution_dataframe,
    outcome_calibration_dataframe,
    outcome_summary_dataframe,
    write_outcome_report,
)


def build_report() -> OutcomeAnalyticsReport:
    calibration = (
        {
            "score": "opportunity_score",
            "horizon_days": 30,
            "bucket_min": 80,
            "bucket_max": 100,
            "count": 2,
            "average_score": 86.0,
            "average_return_pct": 8.0,
            "positive_return_rate": 100.0,
        },
    )
    attribution = (
        {
            "category": "decision",
            "value": "BUY",
            "horizon_days": 30,
            "count": 2,
            "average_return_pct": 8.0,
            "positive_return_rate": 100.0,
        },
    )
    return OutcomeAnalyticsReport(
        hit_rate=HitRateReport(
            eligible_count=2,
            hit_count=2,
            miss_count=0,
            excluded_count=1,
            hit_rate=100.0,
            threshold_pct=0.0,
            by_horizon=(
                {
                    "horizon_days": 30,
                    "eligible_count": 2,
                    "hit_count": 2,
                    "miss_count": 0,
                    "hit_rate": 100.0,
                    "average_directional_return_pct": 8.0,
                },
            ),
        ),
        opportunity_calibration=calibration,
        conviction_calibration=(),
        factor_attribution=(),
        decision_attribution=attribution,
        deal_breaker_attribution=(),
    )


def test_outcome_report_dataframes() -> None:
    report = build_report()

    summary = outcome_summary_dataframe(report)
    calibration = outcome_calibration_dataframe(report)
    attribution = outcome_attribution_dataframe(report)

    assert list(summary["Scope"]) == ["Overall", "Horizon"]
    assert summary.loc[0, "Hit Rate"] == 100.0
    assert calibration.loc[0, "score"] == "opportunity_score"
    assert attribution.loc[0, "Attribution Type"] == "Decision"


def test_write_outcome_report_creates_json(tmp_path: Path) -> None:
    output = write_outcome_report(
        build_report(),
        tmp_path / "output" / "outcome_report.json",
    )
    data = json.loads(output.read_text(encoding="utf-8"))

    assert data["hit_rate"]["hit_rate"] == 100.0
    assert data["opportunity_calibration"][0]["count"] == 2


def test_write_outcome_report_validates_type(tmp_path: Path) -> None:
    with pytest.raises(TypeError):
        write_outcome_report(
            object(),
            tmp_path / "outcome.json",
        )
