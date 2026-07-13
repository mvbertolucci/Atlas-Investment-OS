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

from backtesting.point_in_time_fundamentals import derive_point_in_time_ratios


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
