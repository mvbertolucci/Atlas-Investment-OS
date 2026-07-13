"""
Tests for the watchlist-drift safeguard.

The safeguard quantifies the assumption behind cross-run score calibration:
that the analyzed symbol set is stable across decision dates. Atlas scores are
cross-sectional percentile ranks within each run's batch (see
docs/SCORING_MODEL.md), so calibration that pools buckets across dates is only
comparable when the watchlist does not drift.
"""
from __future__ import annotations

import pandas as pd

from outcomes.analytics import calculate_watchlist_drift


def _frame(pairs: list[tuple[str, str]]) -> pd.DataFrame:
    return pd.DataFrame(pairs, columns=["decision_date", "symbol"])


def test_empty_or_single_date_returns_no_transitions() -> None:
    assert calculate_watchlist_drift(pd.DataFrame()) == ()
    single = _frame([("2026-01-01", "AAA"), ("2026-01-01", "BBB")])
    assert calculate_watchlist_drift(single) == ()


def test_stable_watchlist_flags_stable() -> None:
    frame = _frame(
        [
            ("2026-01-01", "AAA"),
            ("2026-01-01", "BBB"),
            ("2026-02-01", "AAA"),
            ("2026-02-01", "BBB"),
        ]
    )
    drift = calculate_watchlist_drift(frame)
    assert len(drift) == 1
    row = drift[0]
    assert row["stable"] is True
    assert row["jaccard"] == 1.0
    assert row["added_count"] == 0
    assert row["removed_count"] == 0


def test_drifting_watchlist_is_quantified() -> None:
    frame = _frame(
        [
            ("2026-01-01", "AAA"),
            ("2026-01-01", "BBB"),
            # BBB drops out, CCC joins -> intersection {AAA}, union {AAA,BBB,CCC}
            ("2026-02-01", "AAA"),
            ("2026-02-01", "CCC"),
        ]
    )
    drift = calculate_watchlist_drift(frame)
    assert len(drift) == 1
    row = drift[0]
    assert row["stable"] is False
    assert row["added_count"] == 1
    assert row["removed_count"] == 1
    assert row["jaccard"] == round(1 / 3, 4)


def test_transitions_are_ordered_by_date() -> None:
    frame = _frame(
        [
            ("2026-03-01", "AAA"),
            ("2026-01-01", "AAA"),
            ("2026-02-01", "AAA"),
        ]
    )
    drift = calculate_watchlist_drift(frame)
    assert [row["from_date"] for row in drift] == [
        "2026-01-01",
        "2026-02-01",
    ]
    assert [row["to_date"] for row in drift] == [
        "2026-02-01",
        "2026-03-01",
    ]
