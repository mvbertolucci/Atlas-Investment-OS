from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from storage.history_db import HistoryDatabase


POSITIVE_DECISIONS = frozenset(
    {"STRONG_BUY", "BUY", "ACCUMULATE"}
)
NEGATIVE_DECISIONS = frozenset({"AVOID"})
CALIBRATION_SCORES = frozenset(
    {"opportunity_score", "conviction_score"}
)


@dataclass(frozen=True)
class HitRateReport:
    eligible_count: int
    hit_count: int
    miss_count: int
    excluded_count: int
    hit_rate: float | None
    threshold_pct: float
    by_horizon: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "eligible_count": self.eligible_count,
            "hit_count": self.hit_count,
            "miss_count": self.miss_count,
            "excluded_count": self.excluded_count,
            "hit_rate": self.hit_rate,
            "threshold_pct": self.threshold_pct,
            "by_horizon": [dict(row) for row in self.by_horizon],
        }


@dataclass(frozen=True)
class OutcomeAnalyticsReport:
    hit_rate: HitRateReport
    opportunity_calibration: tuple[dict[str, Any], ...]
    conviction_calibration: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "hit_rate": self.hit_rate.to_dict(),
            "opportunity_calibration": [
                dict(row)
                for row in self.opportunity_calibration
            ],
            "conviction_calibration": [
                dict(row)
                for row in self.conviction_calibration
            ],
        }


def build_outcome_dataset(
    database: HistoryDatabase,
) -> pd.DataFrame:
    if not isinstance(database, HistoryDatabase):
        raise TypeError(
            "database deve ser HistoryDatabase."
        )

    snapshots = database.load_outcome_snapshots()
    results = database.load_outcome_results()

    if snapshots.empty or results.empty:
        return pd.DataFrame()

    return results.merge(
        snapshots,
        on=["decision_date", "symbol"],
        how="inner",
        suffixes=("", "_snapshot"),
        validate="many_to_one",
    )


def _expected_direction(decision: Any) -> int | None:
    normalized = str(decision).strip().upper()
    if normalized in POSITIVE_DECISIONS:
        return 1
    if normalized in NEGATIVE_DECISIONS:
        return -1
    return None


def calculate_hit_rate(
    dataset: pd.DataFrame,
    *,
    threshold_pct: float = 0.0,
) -> HitRateReport:
    try:
        threshold = float(threshold_pct)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "threshold_pct deve ser numérico e não negativo."
        ) from exc

    if threshold != threshold or threshold < 0:
        raise ValueError(
            "threshold_pct deve ser numérico e não negativo."
        )

    if dataset.empty:
        return HitRateReport(
            eligible_count=0,
            hit_count=0,
            miss_count=0,
            excluded_count=0,
            hit_rate=None,
            threshold_pct=threshold,
            by_horizon=(),
        )

    required = {"decision", "return_pct", "horizon_days"}
    missing = required.difference(dataset.columns)
    if missing:
        raise ValueError(
            "Dataset sem colunas obrigatórias: "
            + ", ".join(sorted(missing))
        )

    frame = dataset.copy()
    frame["expected_direction"] = frame["decision"].map(
        _expected_direction
    )
    frame["return_pct"] = pd.to_numeric(
        frame["return_pct"],
        errors="coerce",
    )
    eligible = frame.loc[
        frame["expected_direction"].notna()
        & frame["return_pct"].notna()
    ].copy()
    eligible["directional_return_pct"] = (
        eligible["return_pct"]
        * eligible["expected_direction"].astype(float)
    )
    eligible["is_hit"] = (
        eligible["directional_return_pct"] > threshold
    )

    hit_count = int(eligible["is_hit"].sum())
    eligible_count = len(eligible)
    by_horizon: list[dict[str, Any]] = []

    for horizon, group in eligible.groupby(
        "horizon_days",
        sort=True,
    ):
        group_hits = int(group["is_hit"].sum())
        count = len(group)
        by_horizon.append(
            {
                "horizon_days": int(horizon),
                "eligible_count": count,
                "hit_count": group_hits,
                "miss_count": count - group_hits,
                "hit_rate": round(
                    group_hits / count * 100,
                    2,
                ),
                "average_directional_return_pct": round(
                    float(
                        group["directional_return_pct"].mean()
                    ),
                    4,
                ),
            }
        )

    return HitRateReport(
        eligible_count=eligible_count,
        hit_count=hit_count,
        miss_count=eligible_count - hit_count,
        excluded_count=len(frame) - eligible_count,
        hit_rate=(
            round(hit_count / eligible_count * 100, 2)
            if eligible_count
            else None
        ),
        threshold_pct=threshold,
        by_horizon=tuple(by_horizon),
    )


def calculate_score_calibration(
    dataset: pd.DataFrame,
    score_column: str,
    *,
    bucket_size: int = 20,
) -> tuple[dict[str, Any], ...]:
    if score_column not in CALIBRATION_SCORES:
        raise ValueError(
            "score_column deve ser opportunity_score ou conviction_score."
        )

    if isinstance(bucket_size, bool):
        raise ValueError(
            "bucket_size deve ser inteiro entre 1 e 100."
        )

    try:
        size = int(bucket_size)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "bucket_size deve ser inteiro entre 1 e 100."
        ) from exc

    if size <= 0 or size > 100 or float(bucket_size) != size:
        raise ValueError(
            "bucket_size deve ser inteiro entre 1 e 100."
        )

    if dataset.empty:
        return ()

    required = {score_column, "return_pct", "horizon_days"}
    missing = required.difference(dataset.columns)
    if missing:
        raise ValueError(
            "Dataset sem colunas obrigatórias: "
            + ", ".join(sorted(missing))
        )

    frame = dataset.copy()
    frame[score_column] = pd.to_numeric(
        frame[score_column],
        errors="coerce",
    )
    frame["return_pct"] = pd.to_numeric(
        frame["return_pct"],
        errors="coerce",
    )
    frame = frame.dropna(
        subset=[score_column, "return_pct", "horizon_days"]
    )
    frame = frame.loc[
        frame[score_column].between(0, 100)
    ].copy()

    if frame.empty:
        return ()

    frame["bucket_min"] = (
        (frame[score_column] // size) * size
    ).clip(upper=max(0, 100 - size))
    frame["bucket_max"] = (
        frame["bucket_min"] + size
    ).clip(upper=100)
    rows: list[dict[str, Any]] = []

    for (horizon, lower, upper), group in frame.groupby(
        ["horizon_days", "bucket_min", "bucket_max"],
        sort=True,
    ):
        rows.append(
            {
                "score": score_column,
                "horizon_days": int(horizon),
                "bucket_min": int(lower),
                "bucket_max": int(upper),
                "count": len(group),
                "average_score": round(
                    float(group[score_column].mean()),
                    2,
                ),
                "average_return_pct": round(
                    float(group["return_pct"].mean()),
                    4,
                ),
                "positive_return_rate": round(
                    float((group["return_pct"] > 0).mean())
                    * 100,
                    2,
                ),
            }
        )

    return tuple(rows)


def build_outcome_analytics_report(
    database: HistoryDatabase,
    *,
    threshold_pct: float = 0.0,
    bucket_size: int = 20,
) -> OutcomeAnalyticsReport:
    dataset = build_outcome_dataset(database)
    return OutcomeAnalyticsReport(
        hit_rate=calculate_hit_rate(
            dataset,
            threshold_pct=threshold_pct,
        ),
        opportunity_calibration=calculate_score_calibration(
            dataset,
            "opportunity_score",
            bucket_size=bucket_size,
        ),
        conviction_calibration=calculate_score_calibration(
            dataset,
            "conviction_score",
            bucket_size=bucket_size,
        ),
    )
