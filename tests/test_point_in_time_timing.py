"""
Tests for deriving the `timing` factor family (rsi_14, momentum_3m/6m/12m,
distance_52w_high) from the point-in-time price series visible at each
cutoff.

Mirrors analytics/indicators.py's exact formulas and trading-day windows,
but replaces the as-traded `price` series with a continuous one: earlier
prices are divided by the cumulative split ratios effective after that
price and on or before the cutoff's latest visible price date, so a split
never creates artificial momentum.
"""
from __future__ import annotations

import math
from datetime import date, timedelta

import pandas as pd
import pytest

from analytics.indicators import momentum as raw_momentum
from backtesting.point_in_time import (
    HistoricalObservation,
    PointInTimeDataset,
    StockSplitRecord,
)
from backtesting.point_in_time_timing import derive_point_in_time_timing


def _price_observations(
    symbol: str,
    values: list[float],
    *,
    start: str = "2025-01-01",
    source: str = "test_price",
) -> tuple[HistoricalObservation, ...]:
    start_date = date.fromisoformat(start)
    observations = []
    for offset, value in enumerate(values):
        trade_date = start_date + timedelta(days=offset)
        observations.append(
            HistoricalObservation(
                symbol=symbol,
                field_name="price",
                value=value,
                observed_on=trade_date,
                available_at=f"{trade_date + timedelta(days=1)}T00:00:00Z",
                source=source,
                revision_id=trade_date.isoformat(),
            )
        )
    return tuple(observations)


def _split(
    symbol: str,
    *,
    effective_on: str,
    ratio: float,
    known_at: str | None = None,
) -> StockSplitRecord:
    return StockSplitRecord(
        symbol=symbol,
        effective_on=effective_on,
        ratio=ratio,
        known_at=known_at or f"{effective_on}T00:00:00Z",
        source="test_split",
    )


def _approx(value, expected, tol=1e-6) -> bool:
    return value is not None and not math.isnan(value) and abs(value - expected) < tol


def test_matches_analytics_indicators_semantics_without_splits() -> None:
    closes = list(range(1, 254))  # 253 trading days, mirrors test_indicators.py
    history = _price_observations("AAA", [float(v) for v in closes])
    frame = pd.DataFrame([{"symbol": "AAA"}])

    result = derive_point_in_time_timing(frame, history)
    row = result.iloc[0]

    assert row["rsi_14"] == 100.0
    assert _approx(row["momentum_12m"], (253 / 2 - 1) * 100)
    assert row["distance_52w_high"] == 0.0


def test_insufficient_history_leaves_only_the_affected_window_missing() -> None:
    closes = [float(v) for v in range(1, 71)]  # 70 trading days
    history = _price_observations("AAA", closes)
    frame = pd.DataFrame([{"symbol": "AAA"}])

    result = derive_point_in_time_timing(frame, history)
    row = result.iloc[0]

    assert not pd.isna(row["rsi_14"])
    assert not pd.isna(row["momentum_3m"])  # window 63 < 70
    assert pd.isna(row["momentum_6m"])  # window 126 >= 70
    assert pd.isna(row["momentum_12m"])  # window 252 >= 70
    assert not pd.isna(row["distance_52w_high"])


def test_symbol_with_no_price_history_leaves_all_timing_fields_missing() -> None:
    frame = pd.DataFrame([{"symbol": "ZZZ"}])
    result = derive_point_in_time_timing(frame, history=())
    row = result.iloc[0]

    for column in ("rsi_14", "momentum_3m", "momentum_6m", "momentum_12m", "distance_52w_high"):
        assert pd.isna(row[column])


def test_forward_split_does_not_create_artificial_momentum() -> None:
    """
    A 2-for-1 split at day 40 halves as-traded prices for later dates
    relative to what they would have been. Feeding the raw (discontinuous)
    series through analytics.indicators.momentum would show an artificial
    jump; the continuous, split-adjusted series must reproduce the exact
    momentum of the underlying, uninterrupted economic price path.
    """
    true_path = [100.0 + i for i in range(70)]  # continuous, no-split baseline
    split_day = 40
    ratio = 2.0
    raw_values = [
        true_path[i] * ratio if i < split_day else true_path[i]
        for i in range(70)
    ]
    history = _price_observations("AAA", raw_values)
    splits = (_split("AAA", effective_on="2025-02-10", ratio=ratio),)  # day 40 = 2025-02-10
    frame = pd.DataFrame([{"symbol": "AAA"}])

    result = derive_point_in_time_timing(frame, history, splits)
    adjusted_momentum_3m = result.iloc[0]["momentum_3m"]

    expected = raw_momentum(pd.Series(true_path), 63)
    assert _approx(adjusted_momentum_3m, expected)

    naive_momentum_3m = raw_momentum(pd.Series(raw_values), 63)
    assert not _approx(naive_momentum_3m, expected)


def test_reverse_split_does_not_create_artificial_momentum() -> None:
    """Mirror of the forward-split proof for a 1-for-10 reverse split."""
    true_path = [100.0 + i for i in range(70)]
    split_day = 40
    ratio = 0.1  # reverse split: 10 old shares -> 1 new share
    raw_values = [
        true_path[i] * ratio if i < split_day else true_path[i]
        for i in range(70)
    ]
    history = _price_observations("AAA", raw_values)
    splits = (_split("AAA", effective_on="2025-02-10", ratio=ratio),)
    frame = pd.DataFrame([{"symbol": "AAA"}])

    result = derive_point_in_time_timing(frame, history, splits)
    adjusted_momentum_3m = result.iloc[0]["momentum_3m"]

    expected = raw_momentum(pd.Series(true_path), 63)
    assert _approx(adjusted_momentum_3m, expected)

    naive_momentum_3m = raw_momentum(pd.Series(raw_values), 63)
    assert not _approx(naive_momentum_3m, expected)


def test_a_split_not_yet_known_at_the_cutoff_does_not_leak_into_the_replay() -> None:
    """
    Only `snapshot.splits` (already filtered to known-and-effective at the
    cutoff) is ever consulted -- a split whose availability postdates the
    cutoff must never adjust an earlier replay's series.
    """
    true_path = [100.0 + i for i in range(70)]
    split_day = 40
    ratio = 2.0
    raw_values = [
        true_path[i] * ratio if i < split_day else true_path[i]
        for i in range(70)
    ]
    history = _price_observations("AAA", raw_values)
    frame = pd.DataFrame([{"symbol": "AAA"}])

    # The caller (walk_forward.replay_decision_batch) only ever passes
    # snapshot.splits -- simulate the "not yet known" case by passing no
    # splits at all, and prove the series is used exactly as raw.
    result = derive_point_in_time_timing(frame, history, splits=())
    naive_momentum_3m = raw_momentum(pd.Series(raw_values), 63)

    assert _approx(result.iloc[0]["momentum_3m"], naive_momentum_3m)


def test_a_future_price_does_not_leak_into_an_earlier_cutoffs_replay() -> None:
    """
    Integration proof through the real AsOfSnapshot boundary: a decision
    cutoff must only ever see price observations available at or before it.
    If a future close leaked in, momentum_12m (window 252) would be
    computable at the early cutoff too, since 300 closes are ultimately in
    the dataset -- but only ~73 are available by the cutoff, which is not
    enough for a 252-trading-day window.
    """
    closes = [float(v) for v in range(1, 301)]
    history = _price_observations("AAA", closes, start="2025-01-01")
    dataset = PointInTimeDataset(observations=history)
    frame = pd.DataFrame([{"symbol": "AAA"}])

    early_cutoff = "2025-03-15T00:00:00Z"  # ~day 73: only the first ~73 closes visible
    early_snapshot = dataset.as_of(early_cutoff)
    early_result = derive_point_in_time_timing(
        frame, early_snapshot.history, early_snapshot.splits
    )
    assert pd.isna(early_result.iloc[0]["momentum_12m"])

    late_cutoff = "2025-12-31T00:00:00Z"  # all 300 closes visible
    late_snapshot = dataset.as_of(late_cutoff)
    late_result = derive_point_in_time_timing(
        frame, late_snapshot.history, late_snapshot.splits
    )
    assert not pd.isna(late_result.iloc[0]["momentum_12m"])


def test_preexisting_timing_column_is_never_overwritten() -> None:
    closes = list(range(1, 254))
    history = _price_observations("AAA", [float(v) for v in closes])
    frame = pd.DataFrame([{"symbol": "AAA", "rsi_14": 42.0}])

    result = derive_point_in_time_timing(frame, history)

    assert result.iloc[0]["rsi_14"] == 42.0
    assert result.iloc[0]["momentum_12m"] is not None


def test_no_missing_timing_columns_short_circuits_without_touching_frame() -> None:
    frame = pd.DataFrame(
        [
            {
                "symbol": "AAA",
                "rsi_14": 1.0,
                "momentum_3m": 2.0,
                "momentum_6m": 3.0,
                "momentum_12m": 4.0,
                "distance_52w_high": 5.0,
            }
        ]
    )
    result = derive_point_in_time_timing(frame, history=())
    row = result.iloc[0]

    assert row["rsi_14"] == 1.0
    assert row["momentum_3m"] == 2.0
    assert row["momentum_6m"] == 3.0
    assert row["momentum_12m"] == 4.0
    assert row["distance_52w_high"] == 5.0
