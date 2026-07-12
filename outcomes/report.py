from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from outcomes.analytics import OutcomeAnalyticsReport


def outcome_summary_dataframe(
    report: OutcomeAnalyticsReport,
) -> pd.DataFrame:
    hit_rate = report.hit_rate
    rows = [
        {
            "Scope": "Overall",
            "Horizon Days": None,
            "Eligible": hit_rate.eligible_count,
            "Hits": hit_rate.hit_count,
            "Misses": hit_rate.miss_count,
            "Excluded": hit_rate.excluded_count,
            "Hit Rate": hit_rate.hit_rate,
            "Threshold": hit_rate.threshold_pct,
            "Average Directional Return": None,
        }
    ]
    for row in hit_rate.by_horizon:
        rows.append(
            {
                "Scope": "Horizon",
                "Horizon Days": row["horizon_days"],
                "Eligible": row["eligible_count"],
                "Hits": row["hit_count"],
                "Misses": row["miss_count"],
                "Excluded": None,
                "Hit Rate": row["hit_rate"],
                "Threshold": hit_rate.threshold_pct,
                "Average Directional Return": row[
                    "average_directional_return_pct"
                ],
            }
        )
    return pd.DataFrame(rows)


def outcome_calibration_dataframe(
    report: OutcomeAnalyticsReport,
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            *report.opportunity_calibration,
            *report.conviction_calibration,
        ]
    )


def outcome_attribution_dataframe(
    report: OutcomeAnalyticsReport,
) -> pd.DataFrame:
    rows: list[dict] = []
    for row in report.factor_attribution:
        rows.append({"Attribution Type": "Factor", **row})
    for row in report.decision_attribution:
        rows.append({"Attribution Type": "Decision", **row})
    for row in report.deal_breaker_attribution:
        rows.append(
            {"Attribution Type": "Deal Breaker", **row}
        )
    return pd.DataFrame(rows)


def write_outcome_report(
    report: OutcomeAnalyticsReport,
    output_path: Path,
) -> Path:
    if not isinstance(report, OutcomeAnalyticsReport):
        raise TypeError(
            "report deve ser OutcomeAnalyticsReport."
        )

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            report.to_dict(),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return path
