"""
Tests for deriving Atlas's scored ratios from raw point-in-time SEC fields.

config/features.yaml reads ratios (gross_margin, net_margin, current_ratio,
roic, ...), not the raw dollar totals SEC EDGAR provides. These tests verify
the derivation formulas by hand-computed expected values, and that a missing
raw component leaves the derived ratio missing rather than inventing one.
"""
from __future__ import annotations

import math

import pandas as pd
import pytest

from backtesting.point_in_time import (
    HistoricalObservation,
    PointInTimeDataset,
    StockSplitRecord,
)
from backtesting.point_in_time_fundamentals import (
    derive_point_in_time_f_scores,
    derive_point_in_time_ratios,
)


def _row(**overrides) -> dict:
    base = {
        "symbol": "AAA",
        "total_revenue": 1000.0,
        "gross_profit": 400.0,
        "operating_income": 200.0,
        "net_income": 150.0,
        "current_assets": 500.0,
        "current_liabilities": 250.0,
        "total_assets": 2000.0,
        "total_liabilities": 800.0,
        "long_term_debt": 300.0,
        "interest_expense": 50.0,
        "pretax_income": 180.0,
        "tax_provision": 30.0,
        "cash_and_equivalents": 100.0,
    }
    base.update(overrides)
    return base


def _approx(value, expected, tol=1e-4) -> bool:
    return value is not None and not math.isnan(value) and abs(value - expected) < tol


def test_margins_and_current_ratio_match_hand_computed_values() -> None:
    frame = pd.DataFrame([_row()])
    result = derive_point_in_time_ratios(frame)
    row = result.iloc[0]

    assert _approx(row["gross_margin"], 0.4)
    assert _approx(row["operating_margin"], 0.2)
    assert _approx(row["net_margin"], 0.15)
    assert _approx(row["current_ratio"], 2.0)
    assert _approx(row["working_capital"], 250.0)


def test_equity_derived_ratios_match_hand_computed_values() -> None:
    frame = pd.DataFrame([_row()])
    result = derive_point_in_time_ratios(frame)
    row = result.iloc[0]

    # total_equity = 2000 - 800 = 1200
    assert _approx(row["total_equity"], 1200.0)
    assert _approx(row["debt_to_equity"], 300.0 / 1200.0)
    assert _approx(row["interest_coverage"], 200.0 / 50.0)
    assert _approx(row["roe"], 150.0 / 1200.0)


def test_roic_uses_effective_tax_rate_when_plausible() -> None:
    frame = pd.DataFrame([_row()])
    result = derive_point_in_time_ratios(frame)
    row = result.iloc[0]

    # tax_rate = 30/180 = 0.16667 (within [0,1], used as-is).
    # nopat = 200 * (1 - 0.16667) = 166.667
    # invested_capital = 300 + 1200 - 100 = 1400
    assert _approx(row["roic"], 166.6667 / 1400.0, tol=1e-3)


def test_roic_falls_back_to_statutory_rate_when_tax_data_missing() -> None:
    """Mirrors analytics/fundamentals.py::_compute_roic's own fallback."""
    frame = pd.DataFrame([_row(pretax_income=None, tax_provision=None)])
    result = derive_point_in_time_ratios(frame)
    row = result.iloc[0]

    # nopat = 200 * (1 - 0.21) = 158; invested_capital = 1400
    assert _approx(row["roic"], 158.0 / 1400.0)


def test_roic_falls_back_to_statutory_rate_when_implied_rate_out_of_bounds() -> None:
    frame = pd.DataFrame([_row(tax_provision=-50.0)])  # implies rate < 0
    result = derive_point_in_time_ratios(frame)
    row = result.iloc[0]

    assert _approx(row["roic"], 158.0 / 1400.0)


def test_missing_raw_component_leaves_ratio_missing_not_invented() -> None:
    frame = pd.DataFrame([_row(gross_profit=None)])
    result = derive_point_in_time_ratios(frame)
    row = result.iloc[0]

    assert pd.isna(row["gross_margin"])
    # Other ratios that do not depend on gross_profit are unaffected.
    assert _approx(row["net_margin"], 0.15)


def test_entirely_absent_column_leaves_ratio_missing() -> None:
    frame = pd.DataFrame(
        [{"symbol": "AAA", "total_revenue": 1000.0}]
    )  # no gross_profit column at all
    result = derive_point_in_time_ratios(frame)
    assert pd.isna(result.iloc[0]["gross_margin"])


def test_zero_denominator_yields_missing_not_infinite() -> None:
    frame = pd.DataFrame([_row(current_liabilities=0.0)])
    result = derive_point_in_time_ratios(frame)
    assert pd.isna(result.iloc[0]["current_ratio"])


def test_preexisting_ratio_column_is_never_overwritten() -> None:
    """
    A frame that already supplies a ratio directly (e.g. fabricated in a
    test fixture, or sourced from a provider that gives ratios natively)
    must keep that value untouched, even if the raw components needed to
    RECOMPUTE it are absent -- this function only fills genuine gaps, it
    never recalculates and clobbers an already-provided value.
    """
    frame = pd.DataFrame(
        [
            {
                "symbol": "AAA",
                "roic": 15.0,
                "roe": 18.0,
                # No total_revenue/gross_profit/... raw components at all.
            }
        ]
    )
    result = derive_point_in_time_ratios(frame)

    assert result.iloc[0]["roic"] == 15.0
    assert result.iloc[0]["roe"] == 18.0


def test_does_not_mutate_or_drop_raw_input_columns() -> None:
    frame = pd.DataFrame([_row()])
    result = derive_point_in_time_ratios(frame)

    assert result.iloc[0]["total_revenue"] == 1000.0
    assert result.iloc[0]["gross_profit"] == 400.0
    assert "symbol" in result.columns


def _filing_observations(
    *,
    period_end: str,
    filed_at: str,
    accession: str,
    values: dict[str, float],
    form: str = "10-K",
    shares_observed_on: str | None = None,
) -> tuple[HistoricalObservation, ...]:
    return tuple(
        HistoricalObservation(
            symbol="AAA",
            field_name=field_name,
            value=value,
            observed_on=(
                shares_observed_on
                if field_name == "shares_outstanding" and shares_observed_on
                else period_end
            ),
            available_at=filed_at,
            source=f"SEC EDGAR ({form}, us-gaap:Test)",
            revision_id=accession,
        )
        for field_name, value in values.items()
    )


def _prior_year(**overrides) -> dict[str, float]:
    values = {
        "net_income": 50.0,
        "total_assets": 1000.0,
        "operating_cash_flow": 60.0,
        "current_assets": 300.0,
        "current_liabilities": 200.0,
        "shares_outstanding": 100.0,
        "gross_profit": 300.0,
        "total_revenue": 1000.0,
        "long_term_debt": 300.0,
    }
    values.update(overrides)
    return values


def _current_year(**overrides) -> dict[str, float]:
    values = {
        "net_income": 100.0,
        "total_assets": 1100.0,
        "operating_cash_flow": 120.0,
        "current_assets": 400.0,
        "current_liabilities": 200.0,
        "shares_outstanding": 100.0,
        "gross_profit": 484.0,
        "total_revenue": 1210.0,
        "long_term_debt": 200.0,
    }
    values.update(overrides)
    return values


def _two_year_history(
    *,
    prior_values: dict[str, float] | None = None,
    current_values: dict[str, float] | None = None,
) -> tuple[HistoricalObservation, ...]:
    return (
        *_filing_observations(
            period_end="2024-12-31",
            filed_at="2025-02-02T00:00:00Z",
            accession="annual-2024",
            values=prior_values or _prior_year(),
        ),
        *_filing_observations(
            period_end="2025-12-31",
            filed_at="2026-02-02T00:00:00Z",
            accession="annual-2025",
            values=current_values or _current_year(),
        ),
    )


def test_point_in_time_f_score_matches_all_nine_piotroski_signals() -> None:
    result = derive_point_in_time_f_scores(
        pd.DataFrame([{"symbol": "AAA"}]),
        _two_year_history(),
    )

    assert result.iloc[0]["f_score_annual"] == 9.0


def test_f_score_requires_two_complete_consecutive_annual_filings() -> None:
    one_year = _filing_observations(
        period_end="2025-12-31",
        filed_at="2026-02-02T00:00:00Z",
        accession="annual-2025",
        values=_current_year(),
    )
    missing_prior_field = _two_year_history(
        prior_values={
            key: value
            for key, value in _prior_year().items()
            if key != "gross_profit"
        }
    )
    non_consecutive = (
        *_filing_observations(
            period_end="2023-12-31",
            filed_at="2024-02-02T00:00:00Z",
            accession="annual-2023",
            values=_prior_year(),
        ),
        *_filing_observations(
            period_end="2025-12-31",
            filed_at="2026-02-02T00:00:00Z",
            accession="annual-2025",
            values=_current_year(),
        ),
    )

    for history in (one_year, missing_prior_field, non_consecutive):
        result = derive_point_in_time_f_scores(
            pd.DataFrame([{"symbol": "AAA"}]), history
        )
        assert pd.isna(result.iloc[0]["f_score_annual"])


def test_f_score_ignores_quarterly_filings() -> None:
    quarterly = _filing_observations(
        period_end="2025-09-30",
        filed_at="2025-11-02T00:00:00Z",
        accession="quarter-2025",
        values=_current_year(),
        form="10-Q",
    )
    result = derive_point_in_time_f_scores(
        pd.DataFrame([{"symbol": "AAA"}]),
        (*_two_year_history()[:9], *quarterly),
    )

    assert pd.isna(result.iloc[0]["f_score_annual"])


def test_f_score_does_not_leak_second_year_before_filing_availability() -> None:
    dataset = PointInTimeDataset(observations=_two_year_history())

    before = derive_point_in_time_f_scores(
        pd.DataFrame([{"symbol": "AAA"}]),
        dataset.as_of("2026-02-01T23:59:59Z").history,
    )
    after = derive_point_in_time_f_scores(
        pd.DataFrame([{"symbol": "AAA"}]),
        dataset.as_of("2026-02-02T00:00:00Z").history,
    )

    assert pd.isna(before.iloc[0]["f_score_annual"])
    assert after.iloc[0]["f_score_annual"] == 9.0


def test_f_score_uses_latest_available_amendment_for_same_period() -> None:
    amendment = _filing_observations(
        period_end="2025-12-31",
        filed_at="2026-03-01T00:00:00Z",
        accession="annual-2025-amended",
        values=_current_year(net_income=-100.0, operating_cash_flow=50.0),
        form="10-K/A",
    )
    dataset = PointInTimeDataset(
        observations=(*_two_year_history(), *amendment)
    )

    before = derive_point_in_time_f_scores(
        pd.DataFrame([{"symbol": "AAA"}]),
        dataset.as_of("2026-02-15T00:00:00Z").history,
    )
    after = derive_point_in_time_f_scores(
        pd.DataFrame([{"symbol": "AAA"}]),
        dataset.as_of("2026-03-02T00:00:00Z").history,
    )

    assert before.iloc[0]["f_score_annual"] == 9.0
    assert after.iloc[0]["f_score_annual"] < 9.0


def test_partial_amendment_updates_only_its_field_without_erasing_year() -> None:
    amendment = _filing_observations(
        period_end="2025-12-31",
        filed_at="2026-03-01T00:00:00Z",
        accession="annual-2025-partial-amendment",
        values={"net_income": -100.0},
        form="10-K/A",
    )
    dataset = PointInTimeDataset(
        observations=(*_two_year_history(), *amendment)
    )

    result = derive_point_in_time_f_scores(
        pd.DataFrame([{"symbol": "AAA"}]),
        dataset.as_of("2026-03-02T00:00:00Z").history,
    )

    assert not pd.isna(result.iloc[0]["f_score_annual"])
    assert result.iloc[0]["f_score_annual"] < 9.0


def test_f_score_normalizes_prior_shares_for_split_before_dilution_test() -> None:
    history = _two_year_history(
        current_values=_current_year(shares_outstanding=400.0)
    )
    split = StockSplitRecord(
        "AAA", "2025-06-01", 4,
        "2025-06-02T00:00:00Z", "exchange",
    )

    without_split = derive_point_in_time_f_scores(
        pd.DataFrame([{"symbol": "AAA"}]), history
    )
    with_split = derive_point_in_time_f_scores(
        pd.DataFrame([{"symbol": "AAA"}]), history, (split,)
    )

    assert without_split.iloc[0]["f_score_annual"] == 8.0
    assert with_split.iloc[0]["f_score_annual"] == 9.0


def test_preexisting_f_score_is_never_overwritten() -> None:
    frame = pd.DataFrame([{"symbol": "AAA", "f_score_annual": 3.0}])

    result = derive_point_in_time_f_scores(frame, _two_year_history())

    assert result.iloc[0]["f_score_annual"] == 3.0
