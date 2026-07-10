from __future__ import annotations

from pathlib import Path

import pandas as pd

from analytics.alerts import (
    ALERT_COLUMNS,
    build_alerts,
    build_alerts_from_trends,
)
from storage.history_db import HistoryDatabase


def test_empty_trends_return_empty_alerts() -> None:
    result = build_alerts_from_trends(pd.DataFrame())

    assert result.empty
    assert list(result.columns) == ALERT_COLUMNS


def test_strong_opportunity_generates_high_alert() -> None:
    trends = pd.DataFrame(
        {
            "symbol": ["AAA"],
            "Opportunity Score Current": [85.0],
            "Opportunity Score Previous": [82.0],
            "Opportunity Score Delta": [3.0],
            "Business Score Delta": [0.0],
            "Valuation Score Delta": [0.0],
            "Financial Score Delta": [0.0],
            "Timing Score Delta": [0.0],
        }
    )

    result = build_alerts_from_trends(trends)

    assert not result.empty
    assert "Strong Opportunity" in result["Alert Type"].tolist()

    alert = result.loc[
        result["Alert Type"] == "Strong Opportunity"
    ].iloc[0]

    assert alert["Alert Level"] == "HIGH"
    assert alert["symbol"] == "AAA"
    assert "85.0" in alert["Alert Message"]


def test_new_opportunity_crossing_threshold_generates_alert() -> None:
    trends = pd.DataFrame(
        {
            "symbol": ["AAA"],
            "Opportunity Score Current": [74.0],
            "Opportunity Score Previous": [68.0],
            "Opportunity Score Delta": [6.0],
            "Business Score Delta": [1.0],
            "Valuation Score Delta": [4.0],
            "Financial Score Delta": [0.0],
            "Timing Score Delta": [1.0],
        }
    )

    result = build_alerts_from_trends(trends)

    alert_types = result["Alert Type"].tolist()

    assert "New Opportunity" in alert_types
    assert "Opportunity Improving" in alert_types


def test_opportunity_weakening_generates_high_alert() -> None:
    trends = pd.DataFrame(
        {
            "symbol": ["AAA"],
            "Opportunity Score Current": [55.0],
            "Opportunity Score Previous": [64.0],
            "Opportunity Score Delta": [-9.0],
            "Business Score Delta": [-2.0],
            "Valuation Score Delta": [-3.0],
            "Financial Score Delta": [-1.0],
            "Timing Score Delta": [-4.0],
        }
    )

    result = build_alerts_from_trends(trends)

    alert = result.loc[
        result["Alert Type"] == "Opportunity Weakening"
    ].iloc[0]

    assert alert["Alert Level"] == "HIGH"
    assert alert["Opportunity Score Delta"] == -9.0


def test_business_deterioration_generates_high_alert() -> None:
    trends = pd.DataFrame(
        {
            "symbol": ["AAA"],
            "Opportunity Score Current": [60.0],
            "Opportunity Score Previous": [62.0],
            "Opportunity Score Delta": [-2.0],
            "Business Score Delta": [-7.0],
            "Valuation Score Delta": [1.0],
            "Financial Score Delta": [0.0],
            "Timing Score Delta": [0.0],
        }
    )

    result = build_alerts_from_trends(trends)

    alert = result.loc[
        result["Alert Type"] == "Business Deterioration"
    ].iloc[0]

    assert alert["Alert Level"] == "HIGH"
    assert "Business Score" in alert["Alert Message"]


def test_financial_deterioration_generates_high_alert() -> None:
    trends = pd.DataFrame(
        {
            "symbol": ["AAA"],
            "Opportunity Score Current": [62.0],
            "Opportunity Score Previous": [62.0],
            "Opportunity Score Delta": [0.0],
            "Business Score Delta": [0.0],
            "Valuation Score Delta": [0.0],
            "Financial Score Delta": [-6.0],
            "Timing Score Delta": [0.0],
        }
    )

    result = build_alerts_from_trends(trends)

    alert_types = result["Alert Type"].tolist()

    assert "Financial Deterioration" in alert_types


def test_alerts_are_sorted_by_level() -> None:
    trends = pd.DataFrame(
        {
            "symbol": ["AAA", "BBB"],
            "Opportunity Score Current": [75.0, 55.0],
            "Opportunity Score Previous": [68.0, 65.0],
            "Opportunity Score Delta": [7.0, -10.0],
            "Business Score Delta": [1.0, -6.0],
            "Valuation Score Delta": [6.0, 0.0],
            "Financial Score Delta": [0.0, -7.0],
            "Timing Score Delta": [0.0, 0.0],
        }
    )

    result = build_alerts_from_trends(trends)

    assert not result.empty
    assert result.iloc[0]["Alert Level"] == "HIGH"


def test_build_alerts_from_database(tmp_path: Path) -> None:
    database_path = tmp_path / "atlas_history.db"

    first_snapshot = pd.DataFrame(
        {
            "symbol": ["AAA"],
            "Business Score": [60.0],
            "Valuation Score": [55.0],
            "Financial Score": [65.0],
            "Timing Score": [50.0],
            "Investment Score": [58.0],
            "Opportunity Score": [64.0],
            "Confidence Score": [80.0],
            "Recommendation": ["★★ Manter"],
        }
    )

    second_snapshot = pd.DataFrame(
        {
            "symbol": ["AAA"],
            "Business Score": [67.0],
            "Valuation Score": [62.0],
            "Financial Score": [65.0],
            "Timing Score": [54.0],
            "Investment Score": [64.0],
            "Opportunity Score": [74.0],
            "Confidence Score": [82.0],
            "Recommendation": ["★★★ Acumular"],
        }
    )

    with HistoryDatabase(database_path) as database:
        database.save_snapshot(
            first_snapshot,
            "2026-06-01T09:00:00",
        )
        database.save_snapshot(
            second_snapshot,
            "2026-07-10T09:00:00",
        )

    result = build_alerts(
        database_path=database_path,
        period_days=30,
    )

    assert not result.empty
    assert "New Opportunity" in result["Alert Type"].tolist()
    assert "Opportunity Improving" in result["Alert Type"].tolist()