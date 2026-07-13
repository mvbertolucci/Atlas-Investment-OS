"""
Tests for the Yahoo daily-close -> HistoricalObservation converter.

Only the pure conversion function is tested with a small, synthetic,
offline fixture shaped like `yfinance.Ticker.history()`'s DataFrame --
mirroring the project's existing convention for external fetch wrappers
(e.g. backtesting.sec_edgar.extract_observations is likewise tested without
a live network call). `fetch_price_history` itself is not exercised here.
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from backtesting.point_in_time import PointInTimeDataset, UniverseMembership
from backtesting.price_history import (
    available_at_from_trade_date,
    extract_price_observations,
)


def _history(rows: dict[str, float | None]) -> pd.DataFrame:
    index = pd.to_datetime(list(rows.keys()))
    return pd.DataFrame({"Close": list(rows.values())}, index=index)


# ---------------------------------------------------------------------------
# available_at_from_trade_date
# ---------------------------------------------------------------------------


def test_available_at_is_midnight_utc_the_day_after_the_trade() -> None:
    assert available_at_from_trade_date("2026-02-01") == "2026-02-02T00:00:00+00:00"


def test_available_at_accepts_a_real_date_object() -> None:
    assert available_at_from_trade_date(date(2026, 2, 1)) == "2026-02-02T00:00:00+00:00"


# ---------------------------------------------------------------------------
# extract_price_observations
# ---------------------------------------------------------------------------


def test_extracts_one_observation_per_trading_day() -> None:
    history = _history({"2026-01-02": 100.0, "2026-01-03": 101.5, "2026-01-04": 99.0})

    observations = extract_price_observations("AAPL", history)

    assert len(observations) == 3
    assert {o.field_name for o in observations} == {"price"}
    assert {o.symbol for o in observations} == {"AAPL"}


def test_observed_on_and_available_at_track_the_trade_date() -> None:
    history = _history({"2026-01-02": 100.0})

    [observation] = extract_price_observations("AAPL", history)

    assert observation.observed_on == date(2026, 1, 2)
    assert observation.available_at.isoformat() == "2026-01-03T00:00:00+00:00"


def test_value_matches_the_close_column() -> None:
    history = _history({"2026-01-02": 123.45})

    [observation] = extract_price_observations("AAPL", history)

    assert observation.value == pytest.approx(123.45)


def test_rows_with_missing_close_are_skipped_not_invented() -> None:
    history = _history({"2026-01-02": 100.0, "2026-01-03": None})

    observations = extract_price_observations("AAPL", history)

    assert len(observations) == 1
    assert observations[0].observed_on == date(2026, 1, 2)


def test_missing_close_column_yields_no_observations() -> None:
    history = pd.DataFrame({"Volume": [1000]}, index=pd.to_datetime(["2026-01-02"]))

    assert extract_price_observations("AAPL", history) == ()


def test_source_defaults_to_yahoo_daily_close_and_is_overridable() -> None:
    history = _history({"2026-01-02": 100.0})

    [default_source] = extract_price_observations("AAPL", history)
    [custom_source] = extract_price_observations("AAPL", history, source="custom")

    assert default_source.source == "yahoo_daily_close"
    assert custom_source.source == "custom"


def test_observations_feed_a_valid_point_in_time_dataset_and_as_of_picks_latest() -> None:
    history = _history(
        {"2026-01-02": 100.0, "2026-01-05": 105.0, "2026-01-06": 110.0}
    )
    observations = extract_price_observations("AAPL", history)
    dataset = PointInTimeDataset(
        observations=observations,
        memberships=(
            UniverseMembership("AAPL", "2026-01-01", "2026-01-01T00:00:00Z", "manual"),
        ),
    )

    # O fechamento de 01-05 só fica "disponível" à meia-noite UTC de 01-06
    # (available_at_from_trade_date) -- o de 01-06 ainda não, neste corte.
    snapshot = dataset.as_of("2026-01-06T12:00:00Z")

    assert snapshot.value("AAPL", "price") == pytest.approx(105.0)
